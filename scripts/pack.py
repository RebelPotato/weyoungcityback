import os
import shutil

FILES = [
    "README.md",
    ".gitignore",
    "pyproject.toml",
    ".python-version",
    "uv.lock",
    "requirements.txt",
    "local_judge.py",
    "judge.py",
    "common.py",
    "data.py",
    "eval.py",
    "problem0/__init__.py",
    "problem0/answer_std.py",
    "problem0/answer_zero.py",
    "problem1/__init__.py",
    "problem1/answer_std.py",
    "problem1/answer_zero.py",
]


def main():
    assert os.path.exists("dist")
    # Clear the dist directory first
    for item in os.listdir("dist"):
        item_path = os.path.join("dist", item)
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)

    # Copy every file in FILES to dist/weyoungcity
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
