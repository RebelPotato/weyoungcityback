import base64
import logging
import cv2
from typing import List
from dataclasses import dataclass
import json
import os
import data
import common


def read_video(video_path: str) -> List[str]:
    video = cv2.VideoCapture(video_path)

    base64_frames: List[str] = []
    while video.isOpened():
        success, frame = video.read()
        if not success:
            break
        _, buffer = cv2.imencode(".jpg", frame)
        base64_frames.append(
            f"data:image/jpg;base64,{base64.b64encode(buffer).decode('utf-8')}"  # type: ignore
        )

    video.release()
    return base64_frames


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
        base64_frames = read_video(self.video_path)
        logging.info(f"[{self.id}]{len(base64_frames)} frames read.")
        return common.StartReq(
            timeout=1.0,
            question_id=self.id,
            kwargs={
                "question": self.question,
                "base64_frames": base64_frames,
            },
        )

    async def judge(self, choice: str, client) -> data.Result:
        return (
            data.Accepted(self.answer)
            if choice == self.answer
            else data.WrongAnswer(choice=choice, answer=self.answer)
        )


path = os.path.dirname(os.path.abspath(__file__))


def load() -> List[Question]:
    acc = []
    with open(r"./problem1/MVBench_qa.json", "r") as f:
        for item in json.load(f):
            acc.append(
                Question(
                    id=str(item["Question_id"]),
                    video_path=os.path.join("./problem1/videos", item["video_id"]),
                    question=item["question"],
                    answer=item["answer"],
                )
            )
    return acc
