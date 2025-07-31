# 未央城评测东西

## 选手使用方法

解压你得到的压缩包，文件夹里会有这些文件：

```text
TODO
```

运行评测程序需要先安装 python 环境。推荐把所有包装在一个虚拟环境（venv）里，Windows 系统下如下操作：

```powershell
python -m venv .venv              # create venv in folder .venv
.\.venv\Scripts\activate.ps1      # activate venv
pip install -e .                  # install dependencies and packages (each problem is a package) from 'pyproject.toml' in editable mode
```

启动本地评测脚本使用：

```powershell
.\.venv\Scripts\python.exe local_judge.py
```

Linux 同样操作。

## 文件说明

TODO
