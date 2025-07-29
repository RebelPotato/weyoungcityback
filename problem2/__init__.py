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


class Question(data.Question):
    """
    A Single question for problem 2.
    """

    def __init__(self):
        pass

    def start(self) -> data.QuestionStart:
        pass

    def judge(self, choice: str) -> data.Result:
        pass


class Loader(data.Loader):
    """
    Loader for problem 2.
    """

    def path(self) -> str:
        return os.path.abspath("./problem2")

    def load(self) -> List[Question]:
        acc = []
        # with open(r"./problem1/MVBench_qa.json", "r") as f:
        #     for item in json.load(f):
        #         acc.append(
        #             Question(
        #                 id=item["Question_id"],
        #                 video_path=os.path.join("./problem1/videos", item["video_id"]),
        #                 question=item["question"],
        #                 answer=item["answer"],
        #             )
        #         )
        return acc
