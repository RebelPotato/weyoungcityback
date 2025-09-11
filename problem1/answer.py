import math
from typing import List, Dict, Any
import json
import cv2
import base64
import common


def complete(model: str, messages: List[Dict[str, Any]], **kwargs):
    return common.CompleteAction(
        model=model,
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
    video = cv2.VideoCapture(path)

    video_content: List[str] = []
    while video.isOpened():
        success, frame = video.read()
        if not success:
            break
        _, buffer = cv2.imencode(".jpg", frame)
        video_content.append(
            f"data:image/jpg;base64,{base64.b64encode(buffer).decode('utf-8')}"  # type: ignore
        )

    video.release()

    filled_prompt = prompt.format(question=question)

    div_num = max(math.ceil(len(video_content) / 16), 1)
    video_content_selected = video_content[0::div_num]

    content = [
        {"type": "video", "video": video_content_selected},
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
    return res["choice"]
