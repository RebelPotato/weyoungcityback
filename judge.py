import math
import json
import os
import warnings
import logging
import time
import openai
import trio
from typing import Dict, Callable, Sequence, List
from dataclasses import dataclass
from functools import singledispatch
from contextlib import asynccontextmanager
from colorama import just_fix_windows_console
import httpx

import data
import common
import problem0
import problem1


WORKER_COUNT = 24
WORKER_LIMITER = trio.CapacityLimiter(WORKER_COUNT)

PROBLEM_IDS = {
    "0": 0,
    "1": 1,
}
LOADS: List[Callable[[], Sequence[data.Question]]] = [problem0.load, problem1.load]
PATHS: List[str] = [problem0.path, problem1.path]

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")


async def judge_question(
    question: data.Question,
    client: openai.AsyncOpenAI,
    collect_send_chan: trio.MemorySendChannel[data.Result],
    eval_send_chan: trio.MemorySendChannel[bytes],
    response_recv_chan: trio.MemoryReceiveChannel[bytes],
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
                messages=action.messages,  # type: ignore
                **action.kwargs,
            )  # type: ignore
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
        logger.info(f"Question [{question.id}]")
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
        await send_result(data.LLMUsageLimitExceeded())


async def socket_sender(
    client_stream: trio.SocketStream, eval_recv_chan: trio.MemoryReceiveChannel[bytes]
):
    """Adapter from ReceiveChannel to SocketStream."""
    logger.info("sender: started")
    async with eval_recv_chan:
        async for data in eval_recv_chan:
            await common.write_bytes(data, client_stream)
    logger.info("sender: no data left to send, exiting...")


async def socket_receiver(
    client_stream: trio.SocketStream,
    response_send_chan: trio.MemorySendChannel[bytes],
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
        self.count = {}

    def add(self, result: data.Result):
        self.total += 1
        c = result.__class__
        self.count[c] = self.count.get(c, 0) + 1

    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return self.count.get(data.Accepted, 0) / self.total

    def score(self) -> int:
        return max(1, math.floor(self.accuracy() * 100))

    def log(self):
        logger.info(
            f"Accuracy: {self.accuracy():.2%} [{self.count.get(data.Accepted, 0)}/{self.total}]"
        )


async def collector(
    results: Results, collect_recv_chan: trio.MemoryReceiveChannel[data.Result]
):
    """Collect results from the results channel."""
    logger.info("collector: started")
    # TODO add a progress bar or something to show progress
    async with collect_recv_chan:
        async for data in collect_recv_chan:
            results.add(data)
    logger.info("collecter: no result left to collect, exiting...")


async def judge_problem(
    openai_client: openai.AsyncOpenAI,
    questions: Sequence[data.Question],
    results: Results,
):
    async with trio.open_nursery() as task_nursery:
        judged_stream = await trio.open_tcp_stream("127.0.0.1", common.PORT)
        eval_send_chan, eval_recv_chan = trio.open_memory_channel[bytes](0)
        response_send_chan, response_recv_chan = trio.open_memory_channel[bytes](0)
        collect_send_chan, collect_recv_chan = trio.open_memory_channel[data.Result](0)
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
                for question in questions:
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


@dataclass
class Keys:
    api_key: str
    base_url: str
    ssh_username: str
    ssh_password: str
    pg_user: str
    pg_password: str
    pg_database: str


async def main():
    import docker
    import docker.errors
    import sshtunnel
    import psycopg

    @asynccontextmanager
    async def task_container(
        docker_client: docker.DockerClient,
        path: str,
    ):
        container = docker_client.containers.run(
            "judged",
            detach=True,
            read_only=True,
            remove=os.environ.get("WYCB_DEBUG", "false").lower() != "true",
            # network="TODO",
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
                os.path.join(path, "answer_zero.py"): {
                    "bind": "/app/answer_zero.py",
                    "mode": "ro",
                },
            },
        )
        logger.info("docker: container for eval.py spawned")
        try:
            await trio.sleep(3)  # wait for the container to be ready
            yield container
        finally:
            try:
                container.stop()
            except docker.errors.NotFound:
                pass
            logger.info("docker: eval stopped")

    just_fix_windows_console()
    with open("key.json", "r") as f:
        keys = Keys(**json.load(f))
    docker_client = docker.from_env()

    async with httpx.AsyncClient() as client:
        openai_client = openai.AsyncOpenAI(
            api_key=keys.api_key,
            base_url=keys.base_url,
            http_client=client,
        )
        with sshtunnel.SSHTunnelForwarder(
            "81.70.133.142",
            ssh_username=keys.ssh_username,
            ssh_password=keys.ssh_password,
            remote_bind_address=("localhost", 5432),
        ) as tunnel:
            assert tunnel is not None, "Failed to start SSH tunnel"
            tunnel.start()
            with (
                psycopg.connect(
                    f"host=localhost hostaddr=127.0.0.1 "
                    f"dbname={keys.pg_database} "
                    f"user={keys.pg_user} "
                    f"password={keys.pg_password} "
                    f"port={tunnel.local_bind_port}"
                ) as conn,
                conn.cursor() as cur,
            ):
                while True:
                    cur.execute(
                        "SELECT id, problemID, code FROM submissions WHERE score = 0 ORDER BY submitted_at LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row is None:
                        await trio.sleep(5)
                        continue
                    submission_id, problem_id, code = row
                    async with await trio.open_file("answer.py", "wb") as f:
                        await f.write(code.encode("utf-8"))
                    logger.info(f"Submission {submission_id} loaded")

                    problem_id = PROBLEM_IDS[problem_id]
                    questions = LOADS[problem_id]()
                    results = Results()
                    async with task_container(docker_client, PATHS[problem_id]):
                        await judge_problem(openai_client, questions, results)
                    score = results.score()

                    logger.info(f"Writing {submission_id} to database ...")
                    cur.execute(
                        "UPDATE submissions SET score = %s WHERE id = %s",
                        (score, submission_id),
                    )
                    conn.commit()
                    logger.info(
                        f"Submission {submission_id} updated with score {score}"
                    )


if __name__ == "__main__":
    trio.run(main)
