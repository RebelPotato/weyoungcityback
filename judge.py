import math
import json
import docker.models
import docker.models.containers
import os
import warnings
import logging
import time
import openai
import trio
import docker
import pickle
from typing import TypedDict, List, Iterable, TypeVar
from contextlib import contextmanager
import sshtunnel
import psycopg

import data
import problem0
import problem1

import snoop

HEADER_SIZE = 16
PORT = 4001
BATCH_SIZE = 12

LOADERS = {
    "0": problem0.Loader(),
    "1": problem1.Loader(),
}

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


A = TypeVar("A")


def batched(iterable: List[A], n: int) -> Iterable[List[A]]:
    """
    Collect data into fixed-length chunks or blocks.
    """
    for i in range(0, len(iterable), n):
        yield iterable[i : i + n]


class Data(TypedDict):
    question_id: int
    video_path: str
    question: str
    answer: str


async def judge_question(
    question: data.Question,
    client: openai.AsyncOpenAI,
    collect_send_chan: trio.MemorySendChannel,
    eval_send_chan: trio.MemorySendChannel,
    response_recv_chan: trio.MemoryReceiveChannel,
):
    """
    Asynchronously judge a question.
    """

    async def send_RE(e: str):
        logger.info(f"[{question.id}]<RE> {e}")
        await collect_send_chan.send(data.RuntimeError(e))

    async def send_receive(data: dict):
        await eval_send_chan.send(data)
        status = await response_recv_chan.receive()
        if status["status"] == "error":
            await send_RE(status["exception"])
            return None
        return status

    async with collect_send_chan, eval_send_chan, response_recv_chan:
        response = None
        llm_calls = 0
        start_dict = question.start()
        start_dict["type"] = "start"
        status = await send_receive(start_dict)
        if status is None:
            return
        while llm_calls < 10:
            status = await send_receive(
                {
                    "type": "continue",
                    "question_id": question.id,
                    "response": response,
                }
            )
            if status is None:
                return
            if status["status"] == "ok":
                action = status["value"]
                match action["action"]:
                    case "complete":
                        try:
                            response = await client.chat.completions.create(
                                model=action["model"],
                                messages=action["messages"],
                                **action["kwargs"],
                            )
                            llm_calls += 1
                        except Exception as e:
                            logger.error(f"[{question.id}]<RE> LLM Error: {e}")
                            await send_RE(str(e))
                            return
                    case _:
                        await send_RE(ValueError(f"Unknown action: {action}"))
                        return
            elif status["status"] == "done":
                await collect_send_chan.send(question.judge(status["value"]))
                return
            else:
                # Unknown status, bug in the server. The only valid option is to crash.
                raise ValueError(f"Unknown status: {status['status']}")
        logger.info(f"[{question.id}]<LULE> LLM Use Limit Exceeded")
        await collect_send_chan.send(data.LLMUseLimitExceeded())


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


class Results:
    def __init__(self):
        self.total = 0
        self.correct = 0

    def add(self, result: data.Result):
        self.total += 1
        if result.accepted():
            self.correct += 1

    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return self.correct / self.total

    def score(self) -> int:
        return max(1, math.floor(self.accuracy() * 100))

    def log(self):
        logger.info(f"Accuracy: {self.accuracy():.2f}% [{self.correct}/{self.total}]")


async def collector(results: Results, results_recv_chan: trio.MemoryReceiveChannel):
    """Collect results from the results channel."""
    logger.info("collector: started")
    async with results_recv_chan:
        async for data in results_recv_chan:
            results.add(data)
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
    docker_client: docker.DockerClient,
    openai_client: openai.AsyncOpenAI,
    problem_id: str,
) -> int:
    if not problem_id in LOADERS:
        logger.info(f"Problem ID {problem_id} not supported")
        return 1
    loader = LOADERS[problem_id]
    results = Results()

    with container_manager(
        docker_client.containers.run(
            "judged",
            detach=True,
            read_only=True,
            remove=True,
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
                os.path.join(loader.path(), "answer_zero.py"): {
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
                for batch in batched(loader.load(), BATCH_SIZE):
                    async with trio.open_nursery() as batch_nursery:
                        for question in batch:
                            logger.info(f"Question [{question.id}]")
                            batch_nursery.start_soon(
                                judge_question,
                                question,
                                openai_client,
                                collect_send_chan.clone(),
                                eval_send_chan.clone(),
                                response_recv_chan.clone(),
                            )
                end_time = time.time()

    logger.info(f"Total time: {end_time - start_time:.2f} seconds")
    results.log()
    return results.score()


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
                    await trio.sleep(5)
                    continue
                submission_id, problem_id, code = row
                code = code.replace("\r\n", "\n")  # Normalize line endings
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
