import trio
import logging
import warnings
import time
from functools import partial, singledispatch
import common

try:
    import answer as ans
except ImportError:
    import answer_zero as ans

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")

running = {}
time_left = {}
executor = None


def timed(func: callable):
    now = time.time()
    result = func()
    return result, time.time() - now


async def run_task(id: int, func: callable) -> common.Response:
    def done(e: StopIteration):
        logger.info(f"Task {id} completed successfully")
        return common.DoneRes(value=e.value)

    def error(e: Exception):
        logger.error(f"Task {id} raised an exception: {e}")
        return common.ErrRes(exception=repr(e))

    with trio.move_on_after(time_left[id] + 0.5) as cancel_scope:
        # add 0.5 seconds to allow for spawning and processings
        try:
            logger.info(f"Task {id} started with {time_left[id]} seconds left")
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
        return common.ErrRes(exception="Time Limit Exceeded")

    logger.info(f"Task {id} yielded.")
    time_left[id] -= elapsed
    return common.OkRes(value=result)


@singledispatch
async def process(data: common.Request) -> common.Response:
    raise ValueError(f"Unknown request type: {data}")


@process.register
async def _(data: common.StartReq) -> common.Response:
    id = data.question_id
    if id in running:
        raise ValueError(f"Task {id} is already running")

    running[id] = None
    time_left[id] = data.timeout
    result = await run_task(id, partial(ans.query, **data.kwargs))
    if isinstance(result, common.OkRes):
        running[id] = result.value
        return common.OkRes(value=None)
    else:
        del running[id]
        del time_left[id]
        return (
            result
            if isinstance(result, common.ErrRes)
            else common.ErrRes(exception="Task completed unexpectedly")
        )


@process.register
async def _(data: common.ContinueReq) -> common.Response:
    id = data.question_id
    if not (id in running):
        raise ValueError(f"Task {id} is not running")

    process = running[id]
    result = await run_task(id, partial(process.send, data.value))
    if isinstance(result, common.OkRes):
        return result
    else:
        del running[id]
        del time_left[id]
        return result


async def eval_server(server_stream: trio.SocketStream):
    while True:
        b = await common.read_bytes(server_stream)
        if b is None:
            logger.info(f"eval: eval complete! exiting...")
            await server_stream.aclose()
            return

        result = await process(common.Request.load(b))
        await common.write_bytes(result.dump(), server_stream)


async def main():
    await trio.serve_tcp(eval_server, common.PORT, host="0.0.0.0")


trio.run(main)
