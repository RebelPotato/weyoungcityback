import judge
import data
import math
import logging
import warnings
import trio
import openai
import os
import json
import httpx
from dataclasses import dataclass
from contextlib import asynccontextmanager
from colorama import Fore, Back, Style, just_fix_windows_console

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
warnings.filterwarnings("error")
CHARS = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]


def bar(value: float, max_width: int) -> str:
    n = len(CHARS)
    value = max(0, min(value, 1))
    length = math.floor(value * max_width * n)
    return CHARS[-1] * (length // n) + CHARS[length % n]


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
        for c, name in zip(RESULT_TYPES, NAMES):
            count = self.count.get(c, 0)
            accuracy = count / self.total if self.total > 0 else 0.0
            print(
                f"{c.color}{name} [{accuracy:06.2%}] {bar(accuracy, 40)}{Style.RESET_ALL}"
                f" {count}/{self.total}"
            )


@asynccontextmanager
async def task_process():
    async with trio.open_nursery() as nursery:
        logger.info("trio: process for eval.py spawned")
        process = await nursery.start(
            trio.run_process,
            [".venv/Scripts/python", "eval.py"],
        )
        yield process
        nursery.cancel_scope.cancel()
    logger.info("trio: eval.py stopped")


@dataclass
class Keys:
    api_key: str
    base_url: str


async def main():
    just_fix_windows_console()
    with open("key.json", "r") as f:
        d = json.load(f)
        keys = Keys(api_key=d["api_key"], base_url=d["base_url"])

    problem_id = "0"
    loader = judge.LOADERS[problem_id]
    await barf("answer.py", await slurp(os.path.join(loader.path(), "answer.py")))
    await barf(
        "answer_zero.py", await slurp(os.path.join(loader.path(), "answer_zero.py"))
    )
    results = Results()
    async with httpx.AsyncClient() as client, task_process():
        openai_client = openai.AsyncOpenAI(
            api_key=keys.api_key, base_url=keys.base_url, http_client=client
        )
        await judge.judge_problem(openai_client, loader, results)


if __name__ == "__main__":
    trio.run(main)
