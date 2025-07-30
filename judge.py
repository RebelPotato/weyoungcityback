import math
import json
import os
import warnings
import logging
import time
import openai
import trio
import docker
from typing import TypedDict, Dict
from functools import singledispatch
from contextlib import asynccontextmanager
import sshtunnel
import psycopg

import data
import common
import problem0
import problem1


WORKER_COUNT = 12
WORKER_LIMITER = trio.CapacityLimiter(WORKER_COUNT)

LOADERS: Dict[str, data.Loader] = {
    "0": problem0.Loader(),
    "1": problem1.Loader(),
}

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


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

    async def send_result(result: data.Result):
        logger.info(f"[{question.id}]{repr(result)}")
        await collect_send_chan.send(result)

    def result_err(e: str) -> data.Result:
        return (
            data.TimeLimitExceeded()
            if e == "Time Limit Exceeded"
            else data.RuntimeError(e)
        )

    value = None
    llm_calls = 0

    @singledispatch
    async def perform(action: common.Action | None) -> data.Result | None:
        raise ValueError(f"Unknown action: {type(action)}")

    @perform.register
    async def _(action: None):
        return None

    @perform.register
    async def _(action: common.CompleteAction):
        nonlocal llm_calls
        nonlocal client
        nonlocal value
        try:
            value = await client.chat.completions.create(
                model=action.model,
                messages=action.messages,
                **action.kwargs,
            )
            llm_calls += 1
        except Exception as e:
            return result_err(repr(e))

    @singledispatch
    async def handle_response(response: common.Response) -> data.Result | None:
        raise ValueError(f"Unknown response: {type(response)}")

    @handle_response.register
    async def _(response: common.OkRes):
        return await perform(response.value)

    @handle_response.register
    async def _(response: common.ErrRes):
        return result_err(response.exception)

    @handle_response.register
    async def _(response: common.DoneRes):
        return question.judge(response.value)

    async def send_receive(data: common.Request) -> common.Response:
        await eval_send_chan.send(data.dump())
        b = await response_recv_chan.receive()
        return common.Response.load(b)

    async with WORKER_LIMITER, collect_send_chan, eval_send_chan, response_recv_chan:
        response = await send_receive(question.start())
        if isinstance(response, common.ErrRes):
            await send_result(result_err(response.exception))
            return
        while llm_calls < 10:
            response = await send_receive(
                common.ContinueReq(question_id=question.id, value=value)
            )
            result = await handle_response(response)
            if result != None:
                await send_result(result)
                return
        await send_result(data.LLMUseLimitExceeded())


async def socket_sender(
    client_stream: trio.SocketStream, eval_recv_chan: trio.MemoryReceiveChannel
):
    """Adapter from ReceiveChannel to SocketStream."""
    logger.info("sender: started")
    async with eval_recv_chan:
        async for data in eval_recv_chan:
            await common.write_bytes(data, client_stream)
    logger.info("sender: no data left to send, exiting...")


async def socket_receiver(
    client_stream: trio.SocketStream, response_send_chan: trio.MemorySendChannel
):
    """Adapter from SocketStream to SendChannel."""
    logger.info("receiver: started")
    async with response_send_chan:
        while True:
            data = await common.read_bytes(client_stream)
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
        options: dict = json.load(f)
        return Keys(
            api_key=options.get("api_key"),
            base_url=options.get("base_url"),
            ssh_username=options.get("ssh_username"),
            ssh_password=options.get("ssh_password"),
            pg_user=options.get("pg_user"),
            pg_password=options.get("pg_password"),
            pg_database=options.get("pg_database"),
        )


@asynccontextmanager
async def task_container(docker_client: docker.DockerClient, loader: data.Loader):
    try:
        logger.info("docker: eval spawned")
        container = docker_client.containers.run(
            "judged",
            detach=True,
            read_only=True,
            remove=True,
            ports={f"{common.PORT}/tcp": common.PORT},
            tmpfs={"/tmp": "rw"},
            volumes={
                os.path.abspath("eval.py"): {
                    "bind": "/app/eval.py",
                    "mode": "ro",
                },
                os.path.abspath("common.py"): {
                    "bind": "/app/common.py",
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
        await trio.sleep(3)  # wait for the container to be ready
        yield container
    finally:
        container.stop()
        logger.info("docker: eval stopped")


async def judge(
    docker_client: docker.DockerClient,
    openai_client: openai.AsyncOpenAI,
    problem_id: str,
) -> int:
    """Judge one submission."""
    if not problem_id in LOADERS:
        logger.info(f"Problem ID {problem_id} not supported. Check LOADERS!")
        return 1
    results = Results()
    loader = LOADERS[problem_id]
    async with (
        task_container(docker_client, loader),
        trio.open_nursery() as task_nursery,
    ):
        judged_stream = await trio.open_tcp_stream("127.0.0.1", common.PORT)
        eval_send_chan, eval_recv_chan = trio.open_memory_channel(0)
        response_send_chan, response_recv_chan = trio.open_memory_channel(0)
        collect_send_chan, collect_recv_chan = trio.open_memory_channel(0)
        start_time = time.time()
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
            async with trio.open_nursery() as judges_nursery:
                for question in loader.load():
                    logger.info(f"Question [{question.id}]")
                    judges_nursery.start_soon(
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
