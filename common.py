import pickle
import trio
import abc
from dataclasses import dataclass
from typing import Any, Union, TypeVar

PORT = 4001
HEADER_SIZE = 16
A = TypeVar("A")


async def receive_exactly(length: int, stream: trio.SocketStream) -> bytes | None:
    received = []
    while length > 0:
        part = await stream.receive_some(length)
        if part == b"":
            return None
        received.append(part)
        length -= len(part)
    return b"".join(received)


async def write_bytes(msg: bytes, stream: trio.SocketStream):
    length = len(msg).to_bytes(HEADER_SIZE, "big")
    await stream.send_all(length + msg)


async def read_bytes(stream: trio.SocketStream) -> bytes | None:
    try:
        length_msg = await receive_exactly(HEADER_SIZE, stream)
        if length_msg is None:
            return None
        length = int.from_bytes(length_msg, "big")
        return await receive_exactly(length, stream)
    except trio.ClosedResourceError:
        return None


class Request(abc.ABC):
    @abc.abstractmethod
    def dump(self) -> bytes:
        pass

    @staticmethod
    def load(b: bytes) -> "Request":
        """Load a Request from bytes."""
        d = pickle.loads(b)
        type = d["type"]
        del d["type"]
        match type:
            case "start":
                return StartReq(**d)
            case "continue":
                return ContinueReq(**d)
            case _:
                raise ValueError(f"Unknown request type: {type}")


@dataclass
class StartReq(Request):
    question_id: int
    timeout: float
    kwargs: dict[str, Any]

    def dump(self) -> bytes:
        return pickle.dumps(
            {
                "type": "start",
                "question_id": self.question_id,
                "timeout": self.timeout,
                "kwargs": self.kwargs,
            }
        )


@dataclass
class ContinueReq(Request):
    question_id: int
    value: Any

    def dump(self) -> bytes:
        return pickle.dumps(
            {
                "type": "continue",
                "question_id": self.question_id,
                "value": self.value,
            }
        )


class Response(abc.ABC):
    @abc.abstractmethod
    def dump(self) -> bytes:
        pass

    @staticmethod
    def load(b: bytes) -> "Response":
        """Load a Response from bytes."""
        d = pickle.loads(b)
        status = d["status"]
        del d["status"]
        match status:
            case "ok":
                value = d["value"]
                if value is not None:
                    d["value"] = Action.load(value)
                return OkRes(**d)
            case "error":
                return ErrRes(**d)
            case "done":
                return DoneRes(**d)
            case _:
                raise ValueError(f"Unknown request type: {status}")


@dataclass
class OkRes(Response):
    value: Union["Action", None]

    def dump(self) -> bytes:
        return pickle.dumps(
            {"status": "ok", "value": self.value.dump() if self.value != None else None}
        )


@dataclass
class ErrRes(Response):
    exception: str

    def dump(self) -> bytes:
        return pickle.dumps({"status": "error", "exception": self.exception})


@dataclass
class DoneRes(Response):
    value: Any

    def dump(self) -> bytes:
        return pickle.dumps({"status": "done", "value": self.value})


class Action(abc.ABC):
    @abc.abstractmethod
    def dump(self) -> dict:
        pass

    @staticmethod
    def load(d: dict) -> "Action":
        """Load an Action from a dict."""
        type = d["type"]
        del d["type"]
        match type:
            case "complete":
                return CompleteAction(**d)
            case _:
                raise ValueError(f"Unknown action type: {type}")


@dataclass
class CompleteAction(Action):
    model: str
    messages: list[dict[str, Any]]
    kwargs: dict[str, Any]

    def dump(self) -> dict:
        return {
            "type": "complete",
            "model": self.model,
            "messages": self.messages,
            "kwargs": self.kwargs,
        }
