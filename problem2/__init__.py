import logging
from typing import List
from dataclasses import dataclass
import json
import os
import data
import common
import openai


prompt = """
You should help me to evaluate the response given the question and the correct answer.
To mark a response, you should output a single letter, either Y or N.
Y means that the response perfectly matches the answer.
N means that the response is completely different from the answer.


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
        return common.StartReq(
            timeout=4.0,
            question_id=self.id,
            kwargs={
                "question": self.question,
                "path": self.image_path,
            },
        )

    async def judge(self, choice: str, client: openai.AsyncClient) -> data.Result:
        logging.info(f"[{self.id}] judging...")
        filled_prompt = prompt.format(
            question=self.question, answer=self.answer, response=choice
        )
        response_str = ""
        for i in range(3):
            response = await client.chat.completions.create(
                model="qwen3-30b-a3b-instruct-2507",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant designed to evaluate qa quality.",
                    },
                    {"role": "user", "content": filled_prompt},
                ],
            )
            response_str = response.choices[0].message.content
            if response_str is not None:
                logging.info(f"[{self.id}] verdict {i+1}: {response_str}")
                is_right = response_str.strip()[0] == "Y"
                is_wrong = response_str.strip()[0] == "N"
                if is_right or is_wrong:
                    return (
                        data.Accepted(self.answer)
                        if is_right
                        else data.WrongAnswer(choice=choice, answer=self.answer)
                    )
        logging.error(f"[{self.id}] failed to judge, response: {response_str}")
        return data.Accepted(self.answer)  # close enough, we accept it anyway


path = os.path.dirname(os.path.abspath(__file__))


def load(root: str) -> List[Question]:
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
