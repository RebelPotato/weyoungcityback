import trio
import logging
import time
import collections.abc
from dataclasses import dataclass
from functools import partial, singledispatch
from typing import Callable, Any
import common


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
        logging.info(f"Task {id} completed successfully")
        return common.DoneRes(question_id=id, value=e.value)

    def error(e: Exception):
        logging.error(f"Task {id} raised an exception: {e}")
        return common.ErrRes(question_id=id, exception=repr(e))

    result = None
    elapsed = time_left[id] + 1
    with trio.move_on_after(time_left[id] + 0.5) as cancel_scope:
        # add 0.5 seconds to allow for spawning and processing
        try:
            logging.info(f"Running task {id} with {time_left[id]} seconds left")
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
        logging.info(f"Task {id} time limit exceeded")
        return common.ErrRes(question_id=id, exception="Time Limit Exceeded")

    logging.info(f"Task {id} yielded.")
    time_left[id] -= elapsed
    return Ok(value=result)


@singledispatch
async def process(data: common.Request) -> common.Response:
    raise ValueError(f"Unknown request type: {data}")


@process.register
async def _(data: common.StartReq) -> common.Response:
    id = data.question_id
    logging.info(f"Starting task {id} with timeout {data.timeout} seconds")
    if id in running:
        raise ValueError(f"Task {id} is already running")

    running[id] = None
    time_left[id] = data.timeout
    if ans is None:
        logging.info(f"Cannot start task {id} because an error occurred during import.")
        result = common.ErrRes(question_id=id, exception=repr(import_error))
    elif not hasattr(ans, "query"):
        logging.info(f"Cannot start task {id} because ans has no query function.")
        result = common.ErrRes(question_id=id, exception="ans has no query function")
    else:
        result = await run_task(id, partial(ans.query, **data.kwargs))
    if isinstance(result, Ok):
        if isinstance(result.value, collections.abc.Generator):
            running[id] = result.value
            return common.OkRes(question_id=id, value=None)
        else:
            result = common.DoneRes(question_id=id, value=result.value)
    del running[id]
    del time_left[id]
    return result


@process.register
async def _(data: common.ContinueReq) -> common.Response:
    id = data.question_id
    logging.info(f"Resuming task {id}")
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
    logging.info("eval: started")
    while True:
        b = await common.read_bytes(server_stream)
        if b is None:
            logging.info(f"eval: eval complete! exiting...")
            await server_stream.aclose()
            return

        result = await process(common.Request.load(b))
        await common.write_bytes(result.dump(), server_stream)


def import_answer():
    import answer

    return answer


async def import_answer_in(seconds: float):
    try:
        with trio.move_on_after(seconds) as cancel_scope:
            answer = await trio.to_thread.run_sync(import_answer)
        if cancel_scope.cancelled_caught:
            raise TimeoutError(f"Import timeout exceeded {seconds} seconds")
        return answer, None
    except Exception as e:
        logging.error(f"import ans raised an exception: {e}")
        return None, e


async def main():
    global ans, import_error
    ans, import_error = await import_answer_in(0.5)
    common.config_logging()
    # ensure only one thread runs at a time, to make timing fair
    trio.to_thread.current_default_thread_limiter().total_tokens = 1
    listeners = await trio.open_tcp_listeners(common.PORT)
    logging.info("eval: tcp listeners opened, starting server...")
    await trio.serve_listeners(eval_server, listeners)


trio.run(main)
