import trio
import logging
import warnings
import time
from dataclasses import dataclass
from functools import partial, singledispatch
from typing import Callable, Any
import common

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")
import_error = None

try:
    import answer as ans
except Exception as e:
    logger.error(f"import ans raised an exception: {e}")
    ans = None
    import_error = e

running = {}
time_left = {}
executor = None


def timed(func: Callable[[], Any]):
    now = time.time()
    result = func()
    return result, time.time() - now


@dataclass
class Ok:
    value: Any | None


async def run_task(
    id: str, func: Callable[[], Any]
) -> Ok | common.ErrRes | common.DoneRes:
    def done(e: StopIteration):
        logger.info(f"Task {id} completed successfully")
        return common.DoneRes(question_id=id, value=e.value)

    def error(e: Exception):
        logger.error(f"Task {id} raised an exception: {e}")
        return common.ErrRes(question_id=id, exception=repr(e))

    result = None
    elapsed = time_left[id] + 1
    with trio.move_on_after(time_left[id] + 0.5) as cancel_scope:
        # add 0.5 seconds to allow for spawning and processing
        try:
            logger.info(f"Running task {id} with {time_left[id]} seconds left")
            result, elapsed = await trio.to_thread.run_sync(
                partial(timed, func), abandon_on_cancel=True
            )
        except RuntimeError as e:
            # A StopIteration exception should be converted to a RuntimeError when caught.
            if isinstance(e.__cause__, StopIteration):
                return done(e.__cause__)
            else:
                return error(e)
        except StopIteration as e:
            return done(e)
        except Exception as e:
            return error(e)

    if cancel_scope.cancelled_caught or elapsed > time_left[id]:
        logger.info(f"Task {id} time limit exceeded")
        return common.ErrRes(question_id=id, exception="Time Limit Exceeded")

    logger.info(f"Task {id} yielded.")
    time_left[id] -= elapsed
    return Ok(value=result)


@singledispatch
async def process(data: common.Request) -> common.Response:
    raise ValueError(f"Unknown request type: {data}")


@process.register
async def _(data: common.StartReq) -> common.Response:
    id = data.question_id
    logger.info(f"Starting task {id} with timeout {data.timeout} seconds")
    if id in running:
        raise ValueError(f"Task {id} is already running")

    running[id] = None
    time_left[id] = data.timeout
    if ans is None:
        logger.info(f"Cannot start task {id} because an error occurred during import.")
        result = common.ErrRes(question_id=id, exception=repr(import_error))
    else:
        result = await run_task(id, partial(ans.query, **data.kwargs))
    if isinstance(result, Ok):
        running[id] = result.value
        return common.OkRes(question_id=id, value=None)
    else:
        del running[id]
        del time_left[id]
        return result


@process.register
async def _(data: common.ContinueReq) -> common.Response:
    id = data.question_id
    logger.info(f"Resuming task {id}")
    if id not in running:
        raise ValueError(f"Task {id} is not running")

    process = running[id]
    result = await run_task(id, partial(process.send, data.value))
    if isinstance(result, Ok):
        if isinstance(result.value, common.Action):
            return common.OkRes(question_id=id, value=result.value)
        else:
            result = common.ErrRes(
                question_id=id,
                exception=f"Task yielded non-action value {repr(result.value)}",
            )
    del running[id]
    del time_left[id]
    return result


async def eval_server(server_stream: trio.SocketStream):
    logger.info("eval: started")
    while True:
        b = await common.read_bytes(server_stream)
        if b is None:
            logger.info(f"eval: eval complete! exiting...")
            await server_stream.aclose()
            return

        result = await process(common.Request.load(b))
        await common.write_bytes(result.dump(), server_stream)


async def main():
    # ensure only one thread runs at a time, to make timing fair
    trio.to_thread.current_default_thread_limiter().total_tokens = 1
    listeners = await trio.open_tcp_listeners(common.PORT)
    await trio.serve_listeners(eval_server, listeners)


trio.run(main)
