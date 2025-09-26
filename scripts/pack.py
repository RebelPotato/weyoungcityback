import os
import shutil
import json

FILES = [
    "README.md",
    ".gitignore",
    "pyproject.toml",
    ".python-version",
    "uv.lock",
    "local_judge.py",
    "judge.py",
    "common.py",
    "data.py",
    "eval.py",
    "problem0/__init__.py",
    "problem0/answer.py",
    "problem1/__init__.py",
    "problem1/answer.py",
    "problem2/__init__.py",
    "problem2/answer.py",
    "problem2/system_prompt.txt",
    "assets",
]


def make_files():
    """Copy every file in FILES to dist/weyoungcity"""
    for file in FILES:
        src = file
        dst = os.path.join("dist/weyoungcity", file)
        if os.path.exists(src):
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        else:
            print(f"Warning: {src} does not exist and will not be copied.")


def make_zero(count):
    """Make a small test dataset for problem1"""
    problem1_dir = "problem0"
    dataset_file = "problem0/qa_final.json"
    assert os.path.exists(dataset_file)

    with open(dataset_file, "rb") as f:
        dataset = json.load(f)

    testset = dataset[0:count]
    selected_images = [os.path.join(item["image_id"]) for item in testset]
    print(f"Filtered dataset size: {len(testset)}")

    # Save dataset and selected videos
    dist_dir = "dist/weyoungcity/problem0"
    os.makedirs(os.path.join(dist_dir, "imgs"), exist_ok=True)
    for image in selected_images:
        src = os.path.join(problem1_dir, "imgs", image)
        dst = os.path.join(dist_dir, "imgs", image)
        shutil.copy2(src, dst)
    with open(os.path.join(dist_dir, "qa_final.json"), "w", encoding="utf-8") as f:
        json.dump(testset, f, ensure_ascii=False, indent=4)


def make_one(count):
    """Make a small test dataset for problem1"""
    problem1_dir = "problem1"
    dataset_file = "problem1/MVBench_qa.json"
    assert os.path.exists(dataset_file)

    with open(dataset_file, "rb") as f:
        dataset = json.load(f)

    testset = dataset[0:count]
    selected_videos = [os.path.join(item["video_id"]) for item in testset]
    print(f"Filtered dataset size: {len(testset)}")

    # Save dataset and selected videos
    dist_dir = "dist/weyoungcity/problem1"
    os.makedirs(os.path.join(dist_dir, "videos", "left"), exist_ok=True)
    os.makedirs(os.path.join(dist_dir, "videos", "right"), exist_ok=True)
    for video in selected_videos:
        src = os.path.join(problem1_dir, "videos", video)
        dst = os.path.join(dist_dir, "videos", video)
        shutil.copy2(src, dst)
    with open(os.path.join(dist_dir, "MVBench_qa.json"), "w", encoding="utf-8") as f:
        json.dump(testset, f, ensure_ascii=False, indent=4)


def make_two(count):
    """Make a small test dataset for problem2"""
    problem2_dir = "problem2"
    dataset_file = "problem2/qwen2-vl-7b-fine-tune.jsonl"

    with open(dataset_file, "rb") as f:
        testset = [json.loads(line) for line in f.readlines()[0:count]]

    selected_images = [os.path.join(item["image"]) for item in testset]
    print(f"Filtered dataset size: {len(testset)}")

    assert os.path.exists(dataset_file)
    dist_dir = "dist/weyoungcity/problem2"
    os.makedirs(os.path.join(dist_dir, "O3DVQA/EmbodiedCity/Wuhan/rgb"), exist_ok=True)
    for image in selected_images:
        src = os.path.join(problem2_dir, image)
        dst = os.path.join(dist_dir, image)
        shutil.copy2(src, dst)
    with open(
        os.path.join(dist_dir, "qwen2-vl-7b-fine-tune.jsonl"), "w", encoding="utf-8"
    ) as f:
        for line in testset:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def main():
    assert os.path.exists("dist")
    # Clear the dist directory first
    for item in os.listdir("dist"):
        item_path = os.path.join("dist", item)
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)

    make_files()
    make_zero(200)
    make_one(64)
    make_two(200)

    # Create a zip file from the dist/weyoungcity directory
    os.chdir("dist")
    shutil.make_archive(
        base_name="weyoungcity",
        format="zip",
        root_dir="weyoungcity",
    )
    os.chdir("..")
    print("Created dist/weyoungcity.zip")


if __name__ == "__main__":
    main()
