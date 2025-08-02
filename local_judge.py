import judge
import common
import data
import logging
import warnings
import trio
import openai
import os
import json
import httpx
import time
import argparse
from dataclasses import dataclass
from contextlib import asynccontextmanager
from colorama import Style, just_fix_windows_console


RESULT_TYPES = [
    data.Accepted,
    data.WrongAnswer,
    data.RuntimeError,
    data.TimeLimitExceeded,
    data.LLMUsageLimitExceeded,
]
NAMES = [
    "  AC",
    "  WA",
    "  RE",
    " TLE",
    "LULE",
]


async def slurp(path: str) -> bytes:
    async with await trio.open_file(path, "rb") as f:
        return await f.read()


async def barf(path: str, data: bytes):
    async with await trio.open_file(path, "wb") as f:
        await f.write(data)


class Results(judge.Results):
    def log(self):
        width = 60
        for c, name in zip(RESULT_TYPES, NAMES):
            count = self.count.get(c, 0)
            accuracy = count / self.total if self.total > 0 else 0.0
            print(
                f"{c.color}{name} [{count:3}/{self.total}|{accuracy:>6.1%}"
                f"|{common.bar(accuracy, width).ljust(width)}]{Style.RESET_ALL}"
            )


@asynccontextmanager
async def task_process():
    python_exec = ".venv/Scripts/python" if os.name == "nt" else ".venv/bin/python"
    async with trio.open_nursery() as nursery:
        process = await nursery.start(
            trio.run_process,
            [python_exec, "eval.py"],
        )
        logging.info("process for eval.py spawned")
        await trio.sleep(3)  # give eval.py some time to start.
        yield process
        nursery.cancel_scope.cancel()
    logging.info("trio: eval.py stopped")


@dataclass
class Keys:
    api_key: str
    base_url: str


async def main():
    just_fix_windows_console()
    common.config_logging()

    parser = argparse.ArgumentParser(description="WeYoung City Local Judge")
    parser.add_argument(
        "-p",
        "--problem",
        type=int,
        required=True,
        choices=[0, 1],
        help="Problem ID to judge.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=12,
        help="Number of concurrent jobs to run. Defaults to 12, "
        "increase it if you are impatient, and change it to 1 for easier debugging.",
    )
    parser.add_argument(
        "input",
        type=str,
        nargs="?",
        help="Path to the input file. Defaults to 'answer.py' in the problem directory.",
    )
    args = parser.parse_args()

    with open("key.json", "r") as f:
        d = json.load(f)
        keys = Keys(api_key=d["api_key"], base_url=d["base_url"])

    problem_id = args.problem
    path = judge.PATHS[problem_id]
    questions = judge.LOADS[problem_id]()
    input_path = (
        args.input if args.input is not None else os.path.join(path, "answer.py")
    )
    # hidden feature: set to negative to disable the limiter
    judge.WORKER_LIMITER.total_tokens = args.jobs if args.jobs > 0 else 65535
    await barf("answer.py", await slurp(input_path))
    await barf("answer_zero.py", await slurp(os.path.join(path, "answer_zero.py")))
    results = Results()

    start_time = time.time()
    async with httpx.AsyncClient() as client, task_process():
        openai_client = openai.AsyncOpenAI(
            api_key=keys.api_key, base_url=keys.base_url, http_client=client
        )
        await judge.judge_problem(openai_client, questions, results)
    results.log()
    end_time = time.time()
    logging.info(f"Total time: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    trio.run(main)
