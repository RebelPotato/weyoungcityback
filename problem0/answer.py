from typing import List, Generator, Any
import json
import common
import cv2
import base64


def complete(model, messages, **kwargs):
    return common.CompleteAction(
        model=model,
        messages=messages,
        kwargs=kwargs,
    )


prompt = """
This image presents the perception data of an drone flying in a city environment from a first person perspective.

{question}

{choices}

Output your answer in json format, with the following template:

```json
{{
    "reason": "The reason for your choice.",
    "choice": "Your choice. It should be a single letter.",
}}
```
"""


def query(
    question: str, choices: List[str], path: str
) -> Generator[common.Action, Any, str]:
    image = cv2.imread(path)
    assert image is not None
    _, buffer = cv2.imencode(".png", image)
    base64_img = base64.b64encode(buffer).decode("utf-8")  # type: ignore

    filled_prompt = prompt.format(question=question, choices="\n".join(choices))
    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64_img}"},
        },
        {"type": "text", "text": filled_prompt},
    ]

    PROMPT_MESSAGES = [{"role": "user", "content": content}]
    result = yield complete(
        model="Qwen2.5-VL-72B-Instruct",
        messages=PROMPT_MESSAGES,
        temperature=0,
        response_format={"type": "json_object"},
    )
    res = json.loads(result.choices[0].message.content)
    return res["choice"][0]
