# 未央城评测中心

## 开始比赛

解压你得到的压缩包，文件夹里会有这些文件：

```plaintext
weyoungcity.zip
├── common.py
├── data.py
├── eval.py
├── judge.py
├── local_judge.py
├── problem0
│   ├── answer.py
│   ├── answer_zero.py
│   ├── imgs
│   │   └── [*].png
│   ├── __init__.py
│   └── qa_final.json
├── problem1
│   ├── answer.py
│   ├── answer_zero.py
│   └── __init__.py
├── pyproject.toml
├── README.md
└── uv.lock
```

运行评测程序需要先安装 python 环境。推荐把所有包装在一个虚拟环境（venv）里，Windows 系统下如下操作：

```powershell
python -m venv .venv              # create venv in folder .venv
.\.venv\Scripts\activate.ps1      # activate venv, the next pip will come from .venv
pip install -e .                  # install dependencies from 'pyproject.toml' in editable mode
```

Linux 下换成：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

启动本地评测脚本使用：

```bash
python local_judge.py
```

你的任务是修改每个文件夹下的 answer.py，使你的分数尽可能高。

## 部署说明

TODO: 在这里描述我们是如何在服务器上运行评测程序的。

TODO: 服务器上需要怎么配置网络？见 <https://stackoverflow.com/a/64464693>，其中出现的几个 ip 是私有的。

## 文件说明

TODO: 每个文件做什么？
