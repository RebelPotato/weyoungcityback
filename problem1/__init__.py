import base64
import warnings
import logging
import openai
import trio
import cv2
from typing import TypedDict, List
import json
import os
from eztable import Table
import data

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


def get_questions():
    qa_file = r"./MVBench_qa.json"
    questions = Table(
        [("question_id", int), ("video_file", str), ("question", str), ("answer", str)]
    )
    with open(qa_file, "r") as f:
        for item in json.load(f):
            questions.append(
                (
                    item["Question_id"],
                    item["video_id"],
                    item["question"],
                    item["answer"],
                )
            )
    return questions


def read_video(video_path: str) -> List[str]:
    video = cv2.VideoCapture(video_path)

    base64_frames = []
    while video.isOpened():
        success, frame = video.read()
        if not success:
            break
        _, buffer = cv2.imencode(".jpg", frame)
        base64_frames.append(
            f"data:image/jpg;base64,{base64.b64encode(buffer).decode('utf-8')}"
        )

    video.release()
    return base64_frames


class Question(data.Question):
    """
    A Single question for problem 1.
    """

    def __init__(self, id: int, video_path: str, question: str, answer: str):
        self.id = id
        self.video_path = video_path
        self.question = question
        self.answer = answer

    def start(self) -> dict:
        base64_frames = read_video(self.video_path)
        logger.info(f"[{self.id}]{len(base64_frames)} frames read.")
        return {
            "question_id": self.id,
            "question": self.question,
            "base64_frames": base64_frames,
        }

    def judge(self, choice: str) -> data.Result:
        verdict = data.Accepted() if choice == self.answer else data.WrongAnswer(choice)
        logger.info(
            f"[{self.id}]<{str(verdict)}> Output/Answer: {choice}/{self.answer}"
        )
        return verdict


class Loader(data.Loader):
    """
    Loader for problem 1.
    """
    def path(self) -> str:
        return os.path.abspath("./problem1")
    
    def load(self) -> List[Question]:
        qa_file = r"./problem1/MVBench_qa.json"
        acc = []
        with open(qa_file, "r") as f:
            for item in json.load(f):
                acc.append(Question(
                    id=item["Question_id"],
                    video_path=os.path.join("./problem1/videos", item["video_id"]),
                    question=item["question"],
                    answer=item["answer"],
                ))
        return acc
