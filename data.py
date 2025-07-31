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
    color = Fore.GREEN
    answer: Any

    def __repr__(self):
        return f"{Accepted.color}<AC> Accepted{Fore.RESET}: choice = answer = {self.answer}"


@dataclass
class WrongAnswer(Result):
    color = Fore.RED
    choice: Any
    answer: Any

    def __repr__(self):
        return f"{WrongAnswer.color}<WA> Wrong answer{Fore.RESET}: choice/answer = {self.choice}/{self.answer}"


@dataclass
class RuntimeError(Result):
    color = Fore.LIGHTMAGENTA_EX
    error: str

    def __repr__(self):
        return f"{RuntimeError.color}<RE> Runtime error{Fore.RESET}: {self.error}"


@dataclass
class TimeLimitExceeded(Result):
    color = Fore.YELLOW

    def __repr__(self):
        return f"{TimeLimitExceeded.color}<TLE> Time Limit Exceeded{Fore.RESET}"


@dataclass
class LLMUsageLimitExceeded(Result):
    color = Fore.LIGHTYELLOW_EX

    def __repr__(self):
        return (
            f"{LLMUsageLimitExceeded.color}<LULE> LLM Usage Limit Exceeded{Fore.RESET}"
        )
