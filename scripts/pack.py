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
    "problem0/answer_zero.py",
    "problem1/__init__.py",
    "problem1/answer.py",
    "problem1/answer_zero.py",
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


def make_zero():
    """Make a small test dataset for problem0"""

    # Get first 11 images from problem0 folder
    problem0_dir = "problem0/imgs"
    assert os.path.exists(problem0_dir)

    image_files = [f for f in os.listdir(problem0_dir) if f.lower().endswith(".png")]
    selected_images = [f for f in image_files if f.startswith("0_")]

    print(f"Selected images: {selected_images}")

    # Load and filter JSON data with these images
    dataset_file = "problem0/qa_final.json"
    assert os.path.exists(dataset_file)

    with open(dataset_file, "rb") as f:
        dataset = json.load(f)

    testset = [item for item in dataset if item.get("image_id") in selected_images]
    print(f"Filtered dataset size: {len(testset)}")

    # Save dataset and selected images
    dist_dir = "dist/weyoungcity/problem0"
    os.makedirs(dist_dir, exist_ok=True)
    os.makedirs(os.path.join(dist_dir, "imgs"), exist_ok=True)
    for image in selected_images:
        src = os.path.join(problem0_dir, image)
        dst = os.path.join(dist_dir, "imgs", image)
        shutil.copy2(src, dst)
    with open(os.path.join(dist_dir, "qa_final.json"), "w", encoding="utf-8") as f:
        json.dump(testset, f, ensure_ascii=False, indent=4)


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
    make_zero()

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
