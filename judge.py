import math
import json
import docker.models
import docker.models.containers
from eztable import Table
import os
import cv2
import base64
import warnings
import logging
import time
import openai
import trio
import docker
import pickle
from typing import TypedDict, List
from contextlib import contextmanager
import sshtunnel
import psycopg

import snoop

HEADER_SIZE = 16
PORT = 4001
BATCH_SIZE = 12

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


async def receive_exactly(length: int, stream: trio.SocketStream) -> bytes | None:
    received = []
    while length > 0:
        part = await stream.receive_some(length)
        if part == b"":
            return None
        received.append(part)
        length -= len(part)
    return b"".join(received)


async def write_data(data: dict, stream: trio.SocketStream):
    msg = pickle.dumps(data)
    length = len(msg).to_bytes(HEADER_SIZE, "big")
    await stream.send_all(length + msg)


async def read_data(stream: trio.SocketStream) -> dict | None:
    try:
        length_msg = await receive_exactly(HEADER_SIZE, stream)
        if length_msg is None:
            return None
        length = int.from_bytes(length_msg, "big")
        msg = await receive_exactly(length, stream)
        if msg is None:
            return None
        return pickle.loads(msg)
    except trio.ClosedResourceError:
        logger.info("stream closed, nothing to read...")
        return None


def batched(iterable, n):
    """
    Collect data into fixed-length chunks or blocks.
    """
    for i in range(0, len(iterable), n):
        yield iterable[i : i + n]


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


class DataProblemTwo(TypedDict):
    question_id: int
    video_path: str
    question: str
    answer: str


async def judge_problem_two(
    client: openai.AsyncOpenAI,
    data: DataProblemTwo,
    collect_send_chan: trio.MemorySendChannel,
    eval_send_chan: trio.MemorySendChannel,
    response_recv_chan: trio.MemoryReceiveChannel,
):
    """
    Asynchronously judge a video question using the provided model and OpenAI API.
    """
    question_id = data["question_id"]
    video_path = data["video_path"]
    question = data["question"]
    answer = data["answer"]

    async def send_RE(e: str):
        logger.info(f"[{question_id}]<RE> {e}")
        await collect_send_chan.send((question_id, "", "RE"))

    async def send_receive(data: dict):
        await eval_send_chan.send(data)
        status = await response_recv_chan.receive()
        if status["status"] == "error":
            await send_RE(status["exception"])
            return None
        return status

    base64_frames = read_video(video_path)
    logger.info(f"[{question_id}]{len(base64_frames)} frames read.")

    async with collect_send_chan, eval_send_chan, response_recv_chan:
        response = None
        llm_calls = 0
        status = await send_receive(
            {
                "type": "start",
                "question_id": question_id,
                "question": question,
                "base64_frames": base64_frames,
            }
        )
        if status is None:
            return
        while llm_calls < 10:
            status = await send_receive(
                {
                    "type": "continue",
                    "question_id": question_id,
                    "response": response,
                }
            )
            if status is None:
                return
            if status["status"] == "ok":
                action = status["value"]
                match action["action"]:
                    case "complete":
                        response = await client.chat.completions.create(
                            model=action["model"],
                            messages=action["messages"],
                            **action["kwargs"],
                        )
                        llm_calls += 1
                    case _:
                        await send_RE(f"Unknown action: {action}")
                        return
            elif status["status"] == "done":
                choice = status["value"]
                verdict = "AC" if choice == answer else "WA"
                logger.info(
                    f"[{question_id}]<{verdict}> Output/Answer: {choice}/{answer}"
                )
                await collect_send_chan.send((question_id, choice, verdict))
                return
            else:
                # Unknown status, bug in the server. The only valid option is to crash.
                raise ValueError(f"Unknown status: {status['status']}")
        logger.info(f"[{question_id}]<LULE> LLM Use Limit Exceeded")
        await collect_send_chan.send((question_id, "", "LULE"))


async def socket_sender(
    client_stream: trio.SocketStream, eval_recv_chan: trio.MemoryReceiveChannel
):
    """Adapter from ReceiveChannel to SocketStream."""
    logger.info("sender: started")
    async with eval_recv_chan:
        async for data in eval_recv_chan:
            await write_data(data, client_stream)
    logger.info("sender: no data left to send, exiting...")


async def socket_receiver(
    client_stream: trio.SocketStream, response_send_chan: trio.MemorySendChannel
):
    """Adapter from SocketStream to SendChannel."""
    logger.info("receiver: started")
    async with response_send_chan:
        while True:
            data = await read_data(client_stream)
            if data is None:
                logger.info("receiver: received None, exiting...")
                return
            await response_send_chan.send(data)


async def collector(results: Table, results_recv_chan: trio.MemoryReceiveChannel):
    """Collect results from the results channel."""
    logger.info("collector: started")
    async with results_recv_chan:
        async for data in results_recv_chan:
            results.append(data)
    logger.info("collecter: no result left to collect, exiting...")


class Keys(TypedDict):
    api_key: str
    base_url: str
    ssh_username: str
    ssh_password: str
    pg_user: str
    pg_password: str
    pg_database: str


def get_keys() -> Keys:
    key_file = r"./key.json"
    with open(key_file, "r") as f:
        options = json.load(f)
        return Keys(
            api_key=options.get("api_key"),
            base_url=options.get("base_url"),
            ssh_username=options.get("ssh_username"),
            ssh_password=options.get("ssh_password"),
            pg_user=options.get("pg_user"),
            pg_password=options.get("pg_password"),
            pg_database=options.get("pg_database"),
        )


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


@contextmanager
def container_manager(container: docker.models.containers.Container):
    try:
        logger.info("docker: eval spawned")
        yield container
    finally:
        container.stop()
        logger.info("docker: eval stopped")


# judge one submission
async def judge(
    docker_client: docker.DockerClient, openai_client: openai.AsyncOpenAI, problem_id: str
) -> int:
    if not problem_id == "1":
        logger.info(f"Problem ID {problem_id} not supported")
        return 1
    video_folder = r"./videos"
    questions = get_questions()
    results = Table([("question_id", int), ("output", str), ("verdict", str)])

    with container_manager(
        docker_client.containers.run(
            "judged",
            detach=True,
            read_only=True,
            # remove=True,
            ports={f"{PORT}/tcp": PORT},
            tmpfs={"/tmp": "rw"},
            volumes={
                os.path.abspath("eval.py"): {
                    "bind": "/app/eval.py",
                    "mode": "ro",
                },
                os.path.abspath("answer.py"): {
                    "bind": "/app/answer.py",
                    "mode": "ro",
                },
                os.path.abspath("answer_zero.py"): {
                    "bind": "/app/answer_zero.py",
                    "mode": "ro",
                },
            },
        )
    ):
        await trio.sleep(3)
        async with trio.open_nursery() as task_nursery:
            judged_stream = await trio.open_tcp_stream("127.0.0.1", PORT)
            eval_send_chan, eval_recv_chan = trio.open_memory_channel(0)
            response_send_chan, response_recv_chan = trio.open_memory_channel(0)
            collect_send_chan, collect_recv_chan = trio.open_memory_channel(0)
            async with (
                judged_stream,
                eval_send_chan,
                eval_recv_chan,
                response_send_chan,
                response_recv_chan,
                collect_send_chan,
                collect_recv_chan,
            ):
                task_nursery.start_soon(
                    socket_sender, judged_stream, eval_recv_chan.clone()
                )
                task_nursery.start_soon(
                    socket_receiver, judged_stream, response_send_chan.clone()
                )
                task_nursery.start_soon(collector, results, collect_recv_chan.clone())
                start_time = time.time()
                for batch in batched(questions, BATCH_SIZE):
                    async with trio.open_nursery() as batch_nursery:
                        for question_id, video_file, question, answer in batch:
                            logger.info(f"Question [{question_id}]")
                            batch_nursery.start_soon(
                                judge_problem_two,
                                openai_client,
                                {
                                    "question_id": question_id,
                                    "video_path": os.path.join(
                                        video_folder, video_file
                                    ),
                                    "question": question,
                                    "answer": answer,
                                },
                                collect_send_chan.clone(),
                                eval_send_chan.clone(),
                                response_recv_chan.clone(),
                            )
                end_time = time.time()

    logger.info(f"Total time: {end_time - start_time:.2f} seconds")
    info = questions.inner_join(keys=("question_id",), other=results).copy()
    question_count = len(info)
    correct_count = len(info.restrict(["verdict"], lambda v: v == "AC"))
    accuracy = correct_count / question_count * 100
    logger.info(f"Accuracy: {accuracy:.2f}% [{correct_count}/{question_count}]")
    return max(1, math.floor(accuracy))


async def main():
    keys = get_keys()
    openai_client = openai.AsyncOpenAI(
        api_key=keys["api_key"],
        base_url=keys["base_url"],
    )
    docker_client = docker.from_env()

    with sshtunnel.SSHTunnelForwarder(
        "81.70.133.142",
        ssh_username=keys["ssh_username"],
        ssh_password=keys["ssh_password"],
        remote_bind_address=("localhost", 5432),
    ) as tunnel:
        tunnel.start()
        logger.info("SSH tunnel started")
        with (
            psycopg.connect(
                f"host=localhost hostaddr=127.0.0.1 "
                f"dbname={keys['pg_database']} "
                f"user={keys['pg_user']} "
                f"password={keys['pg_password']} "
                f"port={tunnel.local_bind_port}"
            ) as conn,
            conn.cursor() as cur,
        ):
            logger.info("PostgreSQL connection established")
            while True:
                cur.execute(
                    "SELECT id, problemID, code FROM submissions WHERE score = 0 ORDER BY submitted_at LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    logger.info("No submissions to judge, sleeping ...")
                    await trio.sleep(60)
                    continue
                submission_id, problem_id, code = row
                code = code.replace('\r\n', '\n')
                async with await trio.open_file("answer.py", "w") as f:
                    await f.write(code)
                logger.info(f"Submission {submission_id} loaded")
                accuracy = await judge(docker_client, openai_client, problem_id)
                logger.info(f"Writing {submission_id} to database ...")
                cur.execute(
                    "UPDATE submissions SET score = %s WHERE id = %s",
                    (accuracy, submission_id),
                )
                conn.commit()
                logger.info(f"Submission {submission_id} updated with score {accuracy}")


if __name__ == "__main__":
    trio.run(main)
