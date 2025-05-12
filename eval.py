import trio
import pickle
import logging
import warnings
import sys
from typing import List
import snoop

import answer as ans

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")

HEADER_SIZE = 16
PORT = 4001
running = {}


async def receive_exactly(length: int, stream: trio.SocketStream) -> bytes | None:
    received = []
    while length > 0:
        part = await stream.receive_some(length)
        if part == b"":
            return None
        received.append(part)
        length -= len(part)
    return b"".join(received)


async def write_data(data: dict, stream: trio.SocketStream):
    msg = pickle.dumps(data)
    length = len(msg).to_bytes(HEADER_SIZE, "big")
    await stream.send_all(length + msg)


async def read_data(stream: trio.SocketStream) -> dict | None:
    try:
        length_msg = await receive_exactly(HEADER_SIZE, stream)
        if length_msg is None:
            return None
        length = int.from_bytes(length_msg, "big")
        msg = await receive_exactly(length, stream)
        if msg is None:
            return None
        return pickle.loads(msg)
    except trio.ClosedResourceError:
        logger.info("stream closed, nothing to read...")
        return None


def start_task(question: str, base64_frames: List[str]):
    try:
        process = ans.query(question, base64_frames)
        return {
            "status": "ok",
            "process": process,
        }
    except Exception as e:
        return {
            "status": "error",
            "exception": e,
        }


def process(data: dict) -> dict:
    def send_error(exception: str):
        return {"status": "error", "exception": exception}

    match data["type"]:
        case "start":
            if data["question_id"] not in running:
                result = start_task(data["question"], data["base64_frames"])
                match result["status"]:
                    case "ok":
                        process = result["process"]
                        running[data["question_id"]] = process
                        return {"status": "ok"}
                    case "error":
                        return send_error(str(result["exception"]))
            else:
                return send_error("Task already running")
        case "continue":
            if data["question_id"] in running:
                process = running[data["question_id"]]
                try:
                    action = process.send(data["response"])
                except StopIteration as e:
                    del running[data["question_id"]]
                    return {"status": "done", "value": e.value}
                except Exception as e:
                    del running[data["question_id"]]
                    return send_error(str(e))
                return {"status": "ok", "value": action}
            else:
                return send_error("Task not found")
        case _:
            # Unknown data, bug in the client. The only valid option is to crash.
            raise ValueError(f"Unknown data type: {data}")


async def eval_server(server_stream: trio.SocketStream):
    while True:
        data = await read_data(server_stream)
        if data is None:
            logger.info(f"eval: stream ends, closing...")
            await server_stream.aclose()
            return
        if data["type"] == "done":
            logger.info(f"eval: eval complete! exiting...")
            await server_stream.aclose()
            sys.exit(0)

        result = process(data)
        await write_data(result, server_stream)


async def main():
    try:
        async with trio.open_nursery() as nursery:
            listeners = await trio.open_tcp_listeners(PORT, host="127.0.0.1")
            await trio.serve_listeners(eval_server, listeners, handler_nursery=nursery)
    except* SystemExit as group:
        for e in group.exceptions:
            raise e


trio.run(main)
