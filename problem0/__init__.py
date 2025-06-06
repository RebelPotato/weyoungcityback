import base64
import warnings
import logging
import cv2
from typing import List
import json
import os
import data

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


def read_image(image_path: str) -> str:
    image = cv2.imread(image_path)
    assert image is not None, f"Cannot read image at {image_path}."
    _, buffer = cv2.imencode('.png', image)
    return base64.b64encode(buffer).decode('utf-8')


class Question(data.Question):
    """
    A Single question for problem 0.
    """

    def __init__(self, id: int, image_path: str, question: str, choices: List[str], answer: str):
        self.id = id
        self.image_path = image_path
        self.question = question
        self.choices = choices
        self.answer = answer

    def start(self) -> dict:
        base64_frame = read_image(self.image_path)
        logger.info(f"[{self.id}] read image.")
        return {
            "question_id": self.id,
            "question": self.question,
            "choices": self.choices,
            "base64_frame": base64_frame,
        }

    def judge(self, choice: str) -> data.Result:
        verdict = data.Accepted() if choice == self.answer else data.WrongAnswer(choice)
        logger.info(
            f"[{self.id}]<{str(verdict)}> Output/Answer: {choice}/{self.answer}"
        )
        return verdict


class Loader(data.Loader):
    """
    Loader for problem 0.
    """
    def path(self) -> str:
        return os.path.abspath("./problem0")
    
    def load(self) -> List[Question]:
        qa_file = r"./problem0/qa_final.json"
        acc = []
        with open(qa_file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if "image_id" not in item:
                    continue
                acc.append(Question(
                    id=item["question_id"],
                    image_path=os.path.join("./problem0/imgs", item["image_id"]),
                    question=item["question"],
                    choices=item["choices"],
                    answer=item["answer"],
                ))
                if len(acc) >= 200:
                    break
        logger.info(f"Loaded {len(acc)} questions from {qa_file}.")
        return acc
