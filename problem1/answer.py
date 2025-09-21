from typing import List, Dict, Any
import json
import base64
import common
from pathlib import Path


def complete(messages: List[Dict[str, Any]], **kwargs):
    return common.CompleteAction(
        messages=messages,
        kwargs=kwargs,
    )


prompt = """
This video (captured into multiple frames of images as follows) presents the perception data of an agent moving in the environment from a first person perspective. 

{question}

Output your answer in json format, with the following template:

```json
{{
    "reason": "The reason for your choice.",
    "choice": "Your choice. It should be a single letter A, B, C, D, or E",
}}
```
"""


def query(question: str, path: str):
    filled_prompt = prompt.format(question=question)
    video_url = f"data:video/mp4;base64,{base64.b64encode((Path(path).read_bytes() if (p:=Path(path)) else b'')).decode()}"
    content = [
        {"type": "video_url", "video_url": {"url": video_url}},
        {"type": "text", "text": filled_prompt},
    ]

    PROMPT_MESSAGES = [{"role": "user", "content": content}]
    result = yield complete(
        messages=PROMPT_MESSAGES,
        temperature=0,
        response_format={"type": "json_object"},
    )

    res = json.loads(result.choices[0].message.content)
    return res["choice"]
