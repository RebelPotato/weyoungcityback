import math
import json
import os
import warnings
import logging
from datetime import datetime, timezone
import openai
import trio
from typing import Callable, Sequence, List
from dataclasses import dataclass
from functools import singledispatch
from contextlib import asynccontextmanager, AsyncExitStack
from colorama import just_fix_windows_console
import httpx

import data
import common
import problem0
import problem1
import problem2


WORKER_LIMITER = trio.CapacityLimiter(48)

PROBLEM_IDS = {
    "1": 0,
    "2": 1,
    "3": 2,
}
LOADS: List[Callable[[str], Sequence[data.Question]]] = [
    problem0.load,
    problem1.load,
    problem2.load,
]
PATHS: List[str] = [problem0.path, problem1.path, problem2.path]


async def judge_question(
    question: data.Question,
    client: openai.AsyncOpenAI,
    collect_send_chan: trio.MemorySendChannel[data.Result],
    eval_send_chan: trio.MemorySendChannel[bytes],
    response_recv_chan: trio.MemoryReceiveChannel[common.Response],
):
    """
    Asynchronously judge a question.
    """

    async def collect(result: data.Result):
        logging.info(f"[{question.id}]{repr(result)}")
        await collect_send_chan.send(result)

    def result_err(e: str) -> data.Result:
        if e == "Time Limit Exceeded":
            return data.TimeLimitExceeded()
        return data.RuntimeError(e)

    value = None
    llm_calls = 0

    @singledispatch
    async def perform(action: common.Action | None) -> data.Result | None:
        return data.RuntimeError(f"Unknown action: {repr(action)}")

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
                model="Qwen2.5-VL-72B-Instruct",
                messages=action.messages,  # type: ignore
                **action.kwargs,
            )  # type: ignore
            llm_calls += 1
        except Exception as e:
            return result_err(repr(e))

    @singledispatch
    async def handle_response(response: common.Response) -> data.Result | None:
        return data.RuntimeError(f"Unknown response: {repr(response)}")

    @handle_response.register
    async def _(response: common.OkRes):
        return await perform(response.value)

    @handle_response.register
    async def _(response: common.ErrRes):
        return result_err(response.exception)

    @handle_response.register
    async def _(response: common.DoneRes):
        return await question.judge(response.value, client)

    async def send_receive(data: common.Request) -> common.Response:
        await eval_send_chan.send(data.dump())
        return await response_recv_chan.receive()

    async with WORKER_LIMITER, collect_send_chan, eval_send_chan, response_recv_chan:
        logging.info(f"Question [{question.id}]")
        response = await send_receive(question.start())
        if isinstance(response, common.ErrRes):
            await collect(result_err(response.exception))
            return
        if isinstance(response, common.DoneRes):
            await collect(await question.judge(response.value, client))
            return
        while llm_calls < 10:
            response = await send_receive(
                common.ContinueReq(question_id=question.id, value=value)
            )
            result = await handle_response(response)
            if result != None:
                await collect(result)
                return
        await collect(data.LLMUsageLimitExceeded())


async def socket_sender(
    client_stream: trio.SocketStream, eval_recv_chan: trio.MemoryReceiveChannel[bytes]
):
    """Adapter from ReceiveChannel to SocketStream."""
    logging.info("sender: started")
    async with eval_recv_chan:
        async for data in eval_recv_chan:
            await common.write_bytes(data, client_stream)
    logging.info("sender: no data left to send, exiting...")


async def socket_receiver(
    client_stream: trio.SocketStream,
    response_send_chan: List[trio.MemorySendChannel[common.Response]],
    question_ids: List[str],
):
    """Adapter from SocketStream to SendChannel."""
    logging.info("receiver: started")
    chans = {}
    for id, chan in zip(question_ids, response_send_chan):
        chans[id] = chan
    async with AsyncExitStack() as stk:
        for chan in response_send_chan:
            await stk.enter_async_context(chan)
        while True:
            bytes = await common.read_bytes(client_stream)
            if bytes is None:
                logging.info("receiver: received None, exiting...")
                return
            res = common.Response.load(bytes)
            await chans[res.question_id].send(res)


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
        return math.floor(self.accuracy() * 100)

    def log(self):
        logging.info(
            f"Accuracy: {self.accuracy():.2%} [{self.count.get(data.Accepted, 0)}/{self.total}]"
        )


async def collector(
    results: Results,
    count: int,
    collect_recv_chan: trio.MemoryReceiveChannel[data.Result],
):
    """Collect results from the results channel."""
    logging.info("collector: started")
    i = 0
    width = 50
    async with collect_recv_chan:
        async for data in collect_recv_chan:
            results.add(data)
            i += 1
            logging.info(
                f"collector: [{i:03}/{count}|{common.bar(i/count, width).ljust(width)}]"
            )
    logging.info("collecter: no result left to collect, exiting...")


async def judge_problem(
    openai_client: openai.AsyncOpenAI,
    questions: Sequence[data.Question],
    results: Results,
):
    async with trio.open_nursery() as task_nursery:
        judged_stream = await trio.open_tcp_stream("127.0.0.1", common.PORT)
        eval_send_chan, eval_recv_chan = trio.open_memory_channel[bytes](0)
        collect_send_chan, collect_recv_chan = trio.open_memory_channel[data.Result](0)
        async with (
            judged_stream,
            eval_send_chan,
            eval_recv_chan,
            collect_send_chan,
            collect_recv_chan,
            AsyncExitStack() as stk,
        ):
            response_chans = [
                trio.open_memory_channel[common.Response](0) for _ in questions
            ]
            response_send_chans = [
                await stk.enter_async_context(sc) for (sc, _) in response_chans
            ]
            response_recv_chans = [
                await stk.enter_async_context(rc) for (_, rc) in response_chans
            ]
            task_nursery.start_soon(
                socket_sender, judged_stream, eval_recv_chan.clone()
            )
            task_nursery.start_soon(
                socket_receiver,
                judged_stream,
                [c.clone() for c in response_send_chans],
                [q.id for q in questions],
            )
            task_nursery.start_soon(
                collector, results, len(questions), collect_recv_chan.clone()
            )
            async with trio.open_nursery() as judges_nursery:
                for question, rc in zip(questions, response_recv_chans):
                    judges_nursery.start_soon(
                        judge_question,
                        question,
                        openai_client,
                        collect_send_chan.clone(),
                        eval_send_chan.clone(),
                        rc.clone(),
                    )


@dataclass
class Keys:
    api_key: str
    base_url: str
    ssh_username: str
    ssh_password: str
    pg_user: str
    pg_password: str
    pg_database: str


@dataclass
class SubmissionIn:
    id: int
    user_id: int
    problem_id: str
    code: str
    submitted_at: datetime


async def main():
    import podman
    import podman.client
    import podman.domain.containers
    import podman.errors
    import sshtunnel
    import psycopg
    import argparse

    @asynccontextmanager
    async def task_container(
        podman_client: podman.client.PodmanClient,
        path: str,
    ):
        container = podman_client.containers.run(
            "judged",
            detach=True,
            read_only=True,
            remove=os.environ.get("WYCB_DEBUG", "false").lower() != "true",
            # network="TODO",
            ports={f"{common.PORT}/tcp": common.PORT},
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
                path: {
                    "bind": os.path.join("/app", path),
                    "mode": "ro",
                },
            },
        )
        assert isinstance(container, podman.domain.containers.Container)
        try:
            await trio.sleep(10)  # wait for the container to be ready
            logging.info("podman: container for eval.py spawned")
            yield container
        finally:
            try:
                container.stop()
            except podman.errors.NotFound:
                pass
            logging.info("podman: eval stopped")

    parser = argparse.ArgumentParser(
        description="Judge submissions within a time range"
    )
    parser.add_argument(
        "-s",
        "--start",
        required=True,
        help="Start time in ISO format (e.g., 2025-09-25T00:00:00)",
    )
    parser.add_argument(
        "-e", "--end", help="End time in ISO format (e.g., 2025-09-28T23:59:59)"
    )
    args = parser.parse_args()

    start_time = datetime.fromisoformat(args.start).astimezone()
    end_time = datetime.fromisoformat(args.end).astimezone() if args.end else datetime.now().astimezone()

    just_fix_windows_console()
    warnings.filterwarnings("error")
    logging.basicConfig(
        filename="judge.log",
        format="%(asctime)s|%(name)s [%(levelname)s] %(message)s",
        encoding="utf-8",
        level=logging.INFO,
    )

    with open("key.json", "r") as f:
        keys = Keys(**json.load(f))
    if os.name == "nt":
        # make a best-effort attempt to connect to podman socket on Windows
        os.environ["PODMAN_CONNECTION_URI"] = "npipe:////./pipe/podman-machine-default"
        podman_client = podman.PodmanClient(
            base_url="npipe:////./pipe/podman-machine-default"
        )
    else:
        podman_client = podman.from_env()

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
            # Fetch all submissions between start_time and end_time
            cur.execute(
                """
                SELECT id, problemID, user_id, code, submitted_at FROM submissions
                WHERE submitted_at >= %s AND submitted_at <= %s AND eval_status = '未评测'
                ORDER BY submitted_at""",
                (start_time, end_time),
            )
            submissions = [
                SubmissionIn(
                    id=row[0], problem_id=row[1], user_id=row[2], code=row[3], submitted_at=row[4]
                )
                for row in cur.fetchall()
            ]
    logging.info(
        f"Found {len(submissions)} submissions between {start_time} and {end_time}"
    )
    # for each user and each problem, only keep the latest submission and mark the rest as ignored
    latest = {}
    for s in submissions:
        key = (s.user_id, s.problem_id)
        if (
            key not in latest 
            or s.submitted_at > latest[key].submitted_at
        ):
            latest[key] = s
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
            for s in submissions:
                key = (s.user_id, s.problem_id)
                if key in latest and latest[key].id != s.id:
                    cur.execute("UPDATE submissions SET eval_status = '已忽略' WHERE id = %s", (s.id,))
            conn.commit()
    ignored_count = len(submissions) - len(latest)
    submissions = list(latest.values())
    logging.info(f"Ignored {ignored_count} submissions from the same user, {len(submissions)} submissions left to judge")
    

    async with httpx.AsyncClient(
        limits = httpx.Limits(max_keepalive_connections=3, max_connections=6)
    ) as client:
        openai_client = openai.AsyncOpenAI(
            api_key=keys.api_key,
            base_url=keys.base_url,
            http_client=client,
            timeout=180.0,
            max_retries=5
        )
        for s in submissions:
            async with await trio.open_file("answer.py", "wb") as f:
                await f.write(s.code.encode("utf-8"))
            logging.info(f"Submission {s.id} loaded")

            problem_id = PROBLEM_IDS[s.problem_id]
            path = PATHS[problem_id]
            questions = LOADS[problem_id](path)
            results = Results()

            start_time = datetime.now()
            async with task_container(podman_client, PATHS[problem_id]):
                await judge_problem(openai_client, questions, results)
            results.log()
            score = results.score()
            end_time = datetime.now()
            logging.info(f"Total time: {(end_time - start_time).total_seconds():.2f} seconds")

            logging.info(f"Writing {s.id} to database ...")
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
                    cur.execute(
                        "UPDATE submissions SET score = %s, evaluated_at = %s, eval_status = '评测成功' WHERE id = %s",
                        (score, end_time.astimezone(tz=timezone.utc), s.id),
                    )
                    conn.commit()
            logging.info(f"Submission {s.id} updated with score {score}, evaluated at {end_time}")


if __name__ == "__main__":
    trio.run(main)
