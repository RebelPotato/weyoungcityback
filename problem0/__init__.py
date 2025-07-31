import base64
import warnings
import logging
import cv2
from typing import List
from dataclasses import dataclass
import json
import os
import data
import common

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


def read_image(image_path: str) -> str:
    image = cv2.imread(image_path)
    assert image is not None, f"Cannot read image at {image_path}."
    _, buffer = cv2.imencode(".png", image)
    return base64.b64encode(buffer).decode("utf-8")  # type: ignore


@dataclass
class Question(data.Question):
    """
    A Single question for problem 0.
    """

    id: int
    image_path: str
    question: str
    choices: List[str]
    answer: str

    def start(self) -> common.StartReq:
        base64_image = read_image(self.image_path)
        logger.info(f"[{self.id}] read image.")
        return common.StartReq(
            timeout=1.0,
            question_id=self.id,
            kwargs={
                "question": self.question,
                "choices": self.choices,
                "base64_image": base64_image,
            },
        )

    def judge(self, choice: str) -> data.Result:
        return (
            data.Accepted(self.answer)
            if choice == self.answer
            else data.WrongAnswer(choice=choice, answer=self.answer)
        )


path = os.path.dirname(os.path.abspath(__file__))


def load() -> List[Question]:
    acc = []
    with open(os.path.join(path, "qa_final.json"), "r", encoding="utf-8") as f:
        for item in json.load(f):
            if "image_id" not in item:
                continue
            acc.append(
                Question(
                    id=item["question_id"],
                    image_path=os.path.join("./problem0/imgs", item["image_id"]),
                    question=item["question"],
                    choices=item["choices"],
                    answer=item["answer"],
                )
            )
            if len(acc) >= 200:
                break
    return acc
