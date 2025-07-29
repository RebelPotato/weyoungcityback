import json
from openai import OpenAI, AzureOpenAI
from tqdm import tqdm
from datetime import datetime
import os


result_path = r"problem2/qwen2-vl-7b-fine-tune.jsonl"
filename = os.path.basename(result_path)
model_name = filename.split("_")[0]
log_file = f"evaluation_log/{model_name}_4.txt"


def log_progress(index, correct, total):
    accuracy = correct / total if total > 0 else 0.0
    # with open(log_file, "a", encoding="utf-8") as logf:
    #     logf.write(
    #         f"[{datetime.now()}] Step {index}: Accuracy = {accuracy:.4f} ({correct}/{total})\n"
    #     )


def check_match(question, answer, response):

    prompt = f"""
You should help me to evaluate the response given the question and the correct answer.
To mark a response, you should output a single integer between 0 and 1.
1 means that the response perfectly matches the answer.
0 means that the response is completely different from the answer.
"""

    post_fix = f"""
Your Turn:
Question: {question}
Answer: {answer}
Response: {response}
    """

    # content = prompt + examples.format(question=question) + post_fix.format(question, answer, response)
    content = prompt + post_fix
    max_retries = 10
    retry_count = 0
    while retry_count < max_retries:
        try:
            # add repeat tries
            # response = client.chat.completions.create(
            #     timeout=75,
            #     model="gpt-4o",
            #     messages=[
            #         {
            #             "role": "system",
            #             "content": "You are a helpful assistant designed to evaluate qa quality.",
            #         },
            #         {"role": "user", "content": content},
            #     ],
            # )
            # return response.choices[0].message.content
            return "1"
        except Exception as e:
            print(f"发生异常: {e}，正在重试...")
            retry_count += 1


def evaluate(json_path):
    if json_path.endswith(".jsonl"):
        data = []
        with open(json_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():  # 防止空行报错
                    data.append(json.loads(line))
    elif json_path.endswith(".json"):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    # all_items = []
    # # 展平成列表，同时保留上层键的信息
    # for dataset_name, scenes in data.items():  # 第一层，例如 "EmbodiedCity"
    #     for scene_name, items in scenes.items():  # 第二层，例如 "Wuhan"
    #         for item in items:  # 第三层：列表中的每个 item
    #             all_items.append((dataset_name, scene_name, item))

    total = 0
    correct = 0

    for i, item in enumerate(tqdm(data, desc="Evaluating"), 1):
        # first part
        # if i > 6116:
        #     continue
        # last part
        # if i < 6635:
        #     continue
        question = item.get("question", "")
        pred = item.get("pred", "")
        gt = item.get("answer", "")
        if pred and gt:
            score = check_match(question, pred, gt)
            if score == "1":
                correct += 1
                total += 1
            elif score == "0":
                correct += 0
                total += 1
            # if i % 5 == 0:
            log_progress(i, correct, total)

    accuracy = correct / total if total > 0 else 0.0
    print(f"\n Accuracy: {accuracy:.4f} ({correct}/{total})")
    log_progress("Final", correct, total)


if __name__ == "__main__":
    evaluate(result_path)  # 替换为你的 json 文件路径
