import trio
import logging
import warnings
from functools import partial
from typing import Dict, Any
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


async def run_task(id: int, func: callable) -> Dict[str, Any]:
    def done(e: StopIteration):
        logger.info(f"Task {id} completed successfully.")
        time_left[id] -= trio.current_time() - now
        return {"status": "done", "value": e.value}

    def error(e: Exception):
        logger.error(f"Task {id} raised an exception: {e}")
        return {
            "status": "error",
            "exception": str(e),
        }

    now = trio.current_time()
    with trio.move_on_after(time_left[id]) as cancel_scope:
        try:
            logger.info(f"Task {id} run with time limit {time_left[id]} seconds.")
            result = await trio.to_thread.run_sync(func, abandon_on_cancel=True)
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
    if cancel_scope.cancelled_caught:
        logger.info(f"Task {id} time limit exceeded.")
        return {
            "status": "error",
            "exception": "Time Limit Exceeded",
        }
    time_left[id] -= trio.current_time() - now
    return {
        "status": "ok",
        "value": result,
    }


async def process(data: dict) -> dict:
    def send_error(exception: str):
        return {"status": "error", "exception": exception}

    id = data["question_id"]
    match data["type"]:
        case "start":
            if not (id in running):
                running[id] = None
                time_left[id] = data["timeout"]
                result = await run_task(id, partial(ans.query, **data["kwargs"]))
                match result["status"]:
                    case "ok":
                        running[id] = result["value"]
                        return {"status": "ok"}
                    case "error":
                        del running[id]
                        del time_left[id]
                        return send_error(result["exception"])
                    case "done":
                        del running[id]
                        del time_left[id]
                        return send_error("Task completed unexpectedly")
            else:
                # protocol error
                raise ValueError(f"Task {id} is already running")

        case "continue":
            if id in running:
                process = running[id]
                result = await run_task(id, partial(process.send, data["response"]))
                match result["status"]:
                    case "ok":
                        return {"status": "ok", "value": result["value"]}
                    case "error":
                        del running[id]
                        del time_left[id]
                        return send_error(result["exception"])
                    case "done":
                        del running[id]
                        del time_left[id]
                        return {"status": "done", "value": result["value"]}
            else:
                # protocol error
                raise ValueError(f"Task {id} is not running")
        case _:
            # protocol error
            raise ValueError(f"Unknown data type: {data}")


async def eval_server(server_stream: trio.SocketStream):
    while True:
        data = await common.read_data(server_stream)
        if data is None:
            logger.info(f"eval: eval complete! exiting...")
            await server_stream.aclose()
            return

        result = await process(data)
        await common.write_data(result, server_stream)


async def main():
    await trio.serve_tcp(eval_server, common.PORT, host="0.0.0.0")


trio.run(main)
