from typing import List, Generator, Any
import common
import base64
import cv2


def complete(messages, **kwargs):
    return common.CompleteAction(
        messages=messages,
        kwargs=kwargs,
    )


prompt = """
This image presents the perception data of an drone flying in a city environment from a first person perspective.

Given this picture, please answer this question: {question}

Try to answer as succinctly as possible.
"""


def query(question: str, path: str) -> Generator[common.Action, Any, str]:
    image = cv2.imread(path)
    assert image is not None
    _, buffer = cv2.imencode(".png", image)
    base64_image = base64.b64encode(buffer).decode("utf-8")  # type: ignore

    filled_prompt = prompt.format(question=question)

    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64_image}"},
        },
        {"type": "text", "text": filled_prompt},
    ]

    PROMPT_MESSAGES = [{"role": "user", "content": content}]
    result = yield complete(
        messages=PROMPT_MESSAGES,
        temperature=0,
    )
    res = result.choices[0].message.content
    return res
