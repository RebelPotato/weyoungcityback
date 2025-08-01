from abc import ABC, abstractmethod
from typing import Any
import common
from dataclasses import dataclass
from colorama import Fore


class Question(ABC):
    """
    A Question is a single test case for the judge to evaluate.
    """

    id: str

    @abstractmethod
    def start(self) -> common.StartReq:
        pass

    @abstractmethod
    def judge(self, choice: Any) -> "Result":
        pass


class Result(ABC):
    @abstractmethod
    def __repr__(self) -> str:
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
