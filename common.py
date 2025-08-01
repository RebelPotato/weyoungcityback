import pickle
import trio
import abc
import math
from dataclasses import dataclass
from typing import Any, Union, Tuple, Dict

PORT = 4001
HEADER_SIZE = 16


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


CHARS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]


def bar(progress: float, full_width: int) -> str:
    """Make a bar with max width `full_width` with a given progress."""
    n = len(CHARS)
    progress = max(0, min(progress, 1))
    length = math.floor(progress * full_width * n)
    return CHARS[-1] * (length // n) + CHARS[length % n]


class Request(abc.ABC):
    name = "REQ"

    @abc.abstractmethod
    def dump(self) -> bytes:
        pass

    @staticmethod
    def load(b: bytes) -> "Request":
        """Load a Request from bytes."""
        name, type, kwargs = pickle.loads(b)
        assert name == Request.name
        match type:
            case "start":
                return StartReq(**kwargs)
            case "continue":
                return ContinueReq(**kwargs)
            case _:
                raise ValueError(f"Unknown request type: {type}")


@dataclass
class StartReq(Request):
    question_id: str
    timeout: float
    kwargs: dict[str, Any]

    def dump(self) -> bytes:
        return pickle.dumps(
            (
                Request.name,
                "start",
                {
                    "question_id": self.question_id,
                    "timeout": self.timeout,
                    "kwargs": self.kwargs,
                },
            )
        )


@dataclass
class ContinueReq(Request):
    question_id: str
    value: Any

    def dump(self) -> bytes:
        return pickle.dumps(
            (
                Request.name,
                "continue",
                {
                    "question_id": self.question_id,
                    "value": self.value,
                },
            )
        )


class Response(abc.ABC):
    name = "RES"
    question_id: str

    @abc.abstractmethod
    def dump(self) -> bytes:
        pass

    @staticmethod
    def load(b: bytes) -> "Response":
        """Load a Response from bytes."""
        name, status, question_id, value = pickle.loads(b)
        assert name == Response.name
        match status:
            case "ok":
                value = Action.load(value) if value is not None else None
                return OkRes(question_id=question_id, value=value)
            case "error":
                return ErrRes(question_id=question_id, exception=value)
            case "done":
                return DoneRes(question_id=question_id, value=value)
            case _:
                raise ValueError(f"Unknown request type: {status}")


@dataclass
class OkRes(Response):
    question_id: str
    value: Union["Action", None]

    def dump(self) -> bytes:
        return pickle.dumps(
            (
                Response.name,
                "ok",
                self.question_id,
                self.value.dump() if self.value is not None else None,
            )
        )


@dataclass
class ErrRes(Response):
    question_id: str
    exception: str

    def dump(self) -> bytes:
        return pickle.dumps((Response.name, "error", self.question_id, self.exception))


@dataclass
class DoneRes(Response):
    question_id: str
    value: Any

    def dump(self) -> bytes:
        return pickle.dumps((Response.name, "done", self.question_id, self.value))


class Action(abc.ABC):
    name = "ACT"

    @abc.abstractmethod
    def dump(self) -> Tuple[str, str, Dict[str, Any]]:
        pass

    @staticmethod
    def load(t: Tuple[str, str, Dict[str, Any]]) -> "Action":
        """Load an Action from a dict."""
        name, type, kwargs = t
        assert name == Action.name
        match type:
            case "complete":
                return CompleteAction(**kwargs)
            case _:
                raise ValueError(f"Unknown action type: {type}")


@dataclass
class CompleteAction(Action):
    model: str
    messages: list[dict[str, Any]]
    kwargs: dict[str, Any]

    def dump(self) -> Tuple[str, str, Dict[str, Any]]:
        return (
            Action.name,
            "complete",
            {
                "model": self.model,
                "messages": self.messages,
                "kwargs": self.kwargs,
            },
        )
