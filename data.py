from abc import ABC, abstractmethod
from typing import Sequence, Any
import common
from dataclasses import dataclass
from colorama import Fore, Back, Style


class Result(ABC):
    @abstractmethod
    def __repr__(self) -> str:
        pass


class Question(ABC):
    """
    A Question is a single test case for the judge to evaluate.
    """

    id: int

    @abstractmethod
    def start(self) -> common.StartReq:
        pass

    @abstractmethod
    def judge(self, choice: Any) -> Result:
        pass


class Loader(ABC):
    """
    A Loader creates Questions from a source.
    """

    @abstractmethod
    def path(self) -> str:
        """
        Returns the path to the files in sandbox.
        """
        pass

    @abstractmethod
    def load(self) -> Sequence[Question]:
        pass


@dataclass
class Accepted(Result):
    def __repr__(self):
        return "<AC> Accepted"


@dataclass
class WrongAnswer(Result):
    answer: Any
    # TODO: add correct answer to result, remove logging statements in problems

    def __repr__(self):
        return f"<WA> Wrong answer: got {str(self.answer)}"


@dataclass
class RuntimeError(Result):
    error: str

    def __repr__(self):
        return f"<RE> Runtime error: {self.error}"


@dataclass
class TimeLimitExceeded(Result):
    def __repr__(self):
        return "<TLE> Time Limit Exceeded"


@dataclass
class LLMUsageLimitExceeded(Result):
    def __repr__(self):
        return "<LULE> LLM Usage Limit Exceeded"
