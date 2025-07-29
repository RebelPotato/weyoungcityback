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


def query(question: str, base64_frames: List[str]) -> Generator[dict, Any, str]:
    filled_prompt = prompt.format(question=question)

    div_num = max(math.ceil(len(base64_frames) / 16), 1)
    video_content_selected = base64_frames[0::div_num]

    content = [
        {"type": "video", "video": video_content_selected},
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
