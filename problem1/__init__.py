from typing import List
from dataclasses import dataclass
import json
import os
import data
import common


@dataclass
class Question(data.Question):
    """
    A Single question for problem 1.
    """

    id: str
    video_path: str
    question: str
    answer: str

    def start(self) -> common.StartReq:
        return common.StartReq(
            timeout=4.0,
            question_id=self.id,
            kwargs={
                "question": self.question,
                "path": self.video_path,
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
    with open(os.path.join(path, "MVBench_qa.json"), "r") as f:
        for item in json.load(f):
            acc.append(
                Question(
                    id=str(item["Question_id"]),
                    video_path=os.path.join(root, "videos", item["video_id"]),
                    question=item["question"],
                    answer=item["answer"],
                )
            )
    return acc
