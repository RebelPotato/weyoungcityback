from typing import List
from dataclasses import dataclass
import json
import os
import data
import common


@dataclass
class Question(data.Question):
    """
    A Single question for problem 0.
    """

    id: str
    image_path: str
    question: str
    choices: List[str]
    answer: str

    def start(self) -> common.StartReq:
        return common.StartReq(
            timeout=4.0,
            question_id=self.id,
            kwargs={
                "question": self.question,
                "choices": self.choices,
                "path": self.image_path,
            },
        )

    async def judge(self, choice: str, client) -> data.Result:
        return (
            data.Accepted(self.answer)
            if choice == self.answer
            else data.WrongAnswer(choice=choice, answer=self.answer)
        )


path = os.path.dirname(os.path.abspath(__file__))


def load(root: str) -> List[Question]:
    acc = []
    with open(os.path.join(path, "qa_final.json"), "r", encoding="utf-8") as f:
        for item in json.load(f)[0:1000]:
            if "image_id" not in item:
                continue
            acc.append(
                Question(
                    id=str(item["question_id"]),
                    image_path=os.path.join(root, "imgs", item["image_id"]),
                    question=item["question"],
                    choices=item["choices"],
                    answer=item["answer"],
                )
            )
    return acc
