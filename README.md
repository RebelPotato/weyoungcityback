# 未央城评测中心

## 开始比赛

解压你得到的压缩包，文件夹里会有这些文件：

```text
TODO
```

运行评测程序需要先安装 python 环境。推荐把所有包装在一个虚拟环境（venv）里，Windows 系统下如下操作：

```powershell
python -m venv .venv              # create venv in folder .venv
.\.venv\Scripts\activate.ps1      # activate venv, the next pip comes from .venv
pip install -e .                  # install dependencies and packages (each problem is a package) from 'pyproject.toml' in editable mode
```

Linux 下换成：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

启动本地评测脚本使用：

```powershell
python local_judge.py
```

你的任务是修改 answer.py，使你的分数尽可能高。

## 文件说明

TODO
