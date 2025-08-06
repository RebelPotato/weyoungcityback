import base64
import logging
import cv2
from typing import List
from dataclasses import dataclass
import json
import os
import data
import common
import openai


def read_image(image_path: str) -> str:
    image = cv2.imread(image_path)
    assert image is not None, f"Cannot read image at {image_path}."
    _, buffer = cv2.imencode(".png", image)
    return base64.b64encode(buffer).decode("utf-8")  # type: ignore


prompt = """
You should help me to evaluate the response given the question and the correct answer.
To mark a response, you should output a single integer between 0 and 1.
1 means that the response perfectly matches the answer.
0 means that the response is completely different from the answer.


Question: {question}
Answer: {answer}
Response: {response}
"""


@dataclass
class Question(data.Question):
    """
    A Single question for problem 2.
    """

    id: str
    image_path: str
    question: str
    answer: str

    def start(self) -> common.StartReq:
        base64_image = read_image(self.image_path)
        logging.info(f"[{self.id}] read image.")
        return common.StartReq(
            timeout=4.0,
            question_id=self.id,
            kwargs={
                "question": self.question,
                "base64_image": base64_image,
            },
        )

    async def judge(self, choice: str, client: openai.AsyncClient) -> data.Result:
        logging.info(f"[{self.id}] judging...")
        filled_prompt = prompt.format(
            question=self.question, answer=self.answer, response=choice
        )
        response = await client.chat.completions.create(
            model="qwen3-235b-a22b-instruct-2507",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant designed to evaluate qa quality.",
                },
                {"role": "user", "content": filled_prompt},
            ],
        )
        response_str = response.choices[0].message.content
        assert response_str is not None
        is_correct = response_str.strip()[0] == "1"
        return (
            data.Accepted(self.answer)
            if is_correct
            else data.WrongAnswer(choice=choice, answer=self.answer)
        )


path = os.path.dirname(os.path.abspath(__file__))


def load() -> List[Question]:
    acc = []
    with open(
        os.path.join(path, "qwen2-vl-7b-fine-tune.jsonl"), "r", encoding="utf-8"
    ) as f:
        for line in f.readlines():
            item = json.loads(line)
            if "question_id" not in item:
                continue
            acc.append(
                Question(
                    id=str(item["question_id"]),
                    image_path=os.path.join(path, item["image"]),
                    question=item["question"],
                    answer=item["pred"],
                )
            )
            if len(acc) >= 1000:
                break
    return acc
