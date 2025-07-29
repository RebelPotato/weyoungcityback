from abc import ABC, abstractmethod
from typing import Generator, Iterable, TypedDict, Any


class Result(ABC):
    @abstractmethod
    def accepted(self) -> bool:
        pass


class QuestionStart(TypedDict):
    question_id: int
    timeout: float
    kwargs: dict[str, Any]


class Question(ABC):
    """
    A Question is a single test case for the judge to evaluate.
    """

    id: int

    @abstractmethod
    def start(self) -> QuestionStart:
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
    def load(self) -> Iterable[Question]:
        pass


class Accepted(Result):
    def accepted(self) -> bool:
        return True

    def __str__(self):
        return "AC"


class WrongAnswer(Result):
    def __init__(self, answer: any):
        self.answer = answer

    def accepted(self) -> bool:
        return False

    def __str__(self):
        return f"WA: {str(self.answer)}"


class RuntimeError(Result):
    def __init__(self, error: str):
        self.error = error

    def accepted(self) -> bool:
        return False

    def __str__(self):
        return f"RE: {self.error}"


class TimeLimitExceeded(Result):
    def accepted(self) -> bool:
        return False

    def __str__(self):
        return "TLE"


class LLMUseLimitExceeded(Result):
    def accepted(self) -> bool:
        return False

    def __str__(self):
        return f"LULE"
