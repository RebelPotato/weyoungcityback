import json
from eztable import Table
import os
import cv2
import base64
import warnings
import logging
import time
import openai
import trio
from typing import Tuple

import answer as ans

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


BATCH_SIZE = 12
def batched(iterable, n):
    """
    Collect data into fixed-length chunks or blocks.
    """
    for i in range(0, len(iterable), n):
        yield iterable[i : i + n]


async def judge(
    client: openai.AsyncOpenAI,
    question_id: int,
    video_path: str,
    question: str,
    answer: str,
    results: Table
):
    """
    Asynchronously judge a video question using the provided model and OpenAI API.
    """
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
    logger.info(f"[{question_id}]{len(base64_frames)} frames read.")

    judged = ans.query(question, base64_frames)
    response = None
    for _ in range(10):
        try:
            action = judged.send(response)
            match action["action"]:
                case "complete":
                    response = await client.chat.completions.create(
                        model=action["model"],
                        **action["kwargs"],
                    )
                case _:
                    raise ValueError(f"Unknown action: {action['action']}")
        except StopIteration as e:
            choice = e.value
            verdict = "AC" if choice == answer else "WA"
            logger.info(f"[{question_id}]<{verdict}> Output/Answer: {choice}/{answer}")
            results.append((question_id, choice, verdict))
            return
        except Exception as e:
            logger.info(f"[{question_id}]<RE> {e}")
            results.append((question_id, "", "RE"))
            return
    logger.info(f"[{question_id}]<RE> Timeout")
    results.append((question_id, "", "RE"))
    return


async def main():
    video_folder = r"./videos"
    res_folder = r"./results"
    qa_file = r"./MVBench_qa.json"
    key_file = r"./key.json"

    # Read API key from key.json
    with open(key_file, "r") as f:
        api_key = json.load(f).get("key")

    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

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
    start_time = time.time()
    results = Table([("question_id", int), ("output", str), ("verdict", str)])
    for batch in batched(questions, BATCH_SIZE):
        async with trio.open_nursery() as nursery:
            for question_id, video_file, question, answer in batch:
                logger.info(f"Question [{question_id}]")
                nursery.start_soon(
                    judge,
                    client,
                    question_id,
                    os.path.join(video_folder, video_file),
                    question,
                    answer,
                    results
                )

    end_time = time.time()
    logger.info(f"Total time: {end_time - start_time:.2f} seconds")
    info = questions.inner_join(keys=("question_id",), other=results)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(res_folder, exist_ok=True)
    with open(
        os.path.join(res_folder, f"{timestamp}.csv"),
        "w",
        encoding="utf-8",
    ) as f:
        info.to_csv(f, dialect="unix")

    question_count = len(info)
    correct_count = len(info.restrict(["verdict"], lambda v: v == "AC"))
    accuracy = correct_count / question_count * 100
    logger.info(f"Accuracy: {accuracy:.2f}% [{correct_count}/{question_count}]")


if __name__ == "__main__":
    trio.run(main)
