# 未央城评测中心

## 开始比赛

解压你得到的压缩包，文件夹里会有这些文件：

TODO: 每个文件做什么？

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

## 维护说明

按照部署说明添加完 git 配置后，上传代码只需要两步。

```bash
# on your computer:
git push prod
# on the server:
git pull
```

## 部署说明

这里描述我们如何在服务器上运行评测程序。

### 配置硬件软件

TODO：什么硬件配置？网络？评测速度如何？

TODO：什么软件配置？

git, python 3.11.13, docker 版本……

TODO: 服务器上需要怎么配置网络？见 <https://stackoverflow.com/a/64464693>，其中出现的几个 ip 是私有的。

### 把评测程序搬到服务器上

我们的代码放在 `/app` 下，包含代码文件夹 `/app/weyoungcity` 与 git bare repo `/app/weyoungcity.git`。

在 `/app/weyoungcity.git` 创建一个 [git bare repo](https://ratfactor.com/cards/git-bare-repos)。

```bash
cd /app
mkdir weyoungcity.git
cd /app/weyoungcity.git
git init --bare
```

在开发电脑里的 `.git/config` 里添加如下设置：

```toml
[remote "prod"]
  url = ssh://username@server/app/weyoungcity.git
```

然后运行 `git push prod`，代码就跑到了服务器上！

随后在服务器上运行：

```bash
cd /app
git clone weyoungcity.git
```

这会创建代码文件夹 `/app/weyoungcity`。

### 配置软件环境

python 环境与选手的配置方法类似。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[prod]
```

docker 环境使用：

```bash
docker build -t judged .
```

### 保证代码一直运行

TODO: 一个 systemd 配置。
