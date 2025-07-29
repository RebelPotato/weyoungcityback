import math
from typing import List, Generator, Any
import json


def complete(model, messages, **kwargs):
    return {
        "action": "complete",
        "model": model,
        "messages": messages,
        "kwargs": kwargs,
    }


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
    question: str, choices: List[str], base64_image: str
) -> Generator[dict, Any, str]:
    filled_prompt = prompt.format(question=question, choices="\n".join(choices))

    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64_image}"},
        },
        {"type": "text", "text": filled_prompt},
    ]

    PROMPT_MESSAGES = [{"role": "user", "content": content}]
    result = yield complete(
        model="qwen-vl-plus-latest",
        messages=PROMPT_MESSAGES,
        temperature=0,
        response_format={"type": "json_object"},
    )
    res = json.loads(result.choices[0].message.content)
    return res["choice"]
