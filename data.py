from abc import ABC, abstractmethod
from typing import List
import common


class Result(ABC):
    @abstractmethod
    def accepted(self) -> bool:
        pass

    @abstractmethod
    def __str__(self) -> str:
        pass

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
    def judge(self, value: any) -> Result:
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
    def load(self) -> List[Question]:
        pass


class Accepted(Result):
    def accepted(self) -> bool:
        return True

    def __str__(self):
        return "AC"

    def __repr__(self):
        return "<AC> Accepted"


class WrongAnswer(Result):
    def __init__(self, answer: any):
        self.answer = answer

    def accepted(self) -> bool:
        return False

    def __str__(self):
        return "WA"

    def __repr__(self):
        return f"<WA> Wrong answer: got {str(self.answer)}"


class RuntimeError(Result):
    def __init__(self, error: str):
        self.error = error

    def accepted(self) -> bool:
        return False

    def __str__(self):
        return "RE"

    def __repr__(self):
        return f"<RE> Runtime error: {self.error}"


class TimeLimitExceeded(Result):
    def accepted(self) -> bool:
        return False

    def __str__(self):
        return "TLE"

    def __repr__(self):
        return "<TLE> Time Limit Exceeded"


class LLMUseLimitExceeded(Result):
    def accepted(self) -> bool:
        return False

    def __str__(self):
        return f"LULE"

    def __repr__(self):
        return "<LULE> LLM Use Limit Exceeded"
