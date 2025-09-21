# 维护与部署说明

按照部署说明添加完 git 配置后，上传代码只需要两步。

```bash
# on your computer:
git push prod
# on the server:
git pull
```

这里描述我们如何在服务器上运行评测程序。需要安装的软件有：git, python 3.11.13, podman。

## 把评测程序搬到服务器上

我们的代码放在 `~/app` 下，包含代码文件夹 `~/app/weyoungcity` 与 git bare repo `~/app/weyoungcity.git`。

在 `~/app/weyoungcity.git` 创建一个 [git bare repo](https://ratfactor.com/cards/git-bare-repos)。

```bash
cd ~/app
mkdir weyoungcity.git
cd ~/app/weyoungcity.git
git init --bare
```

在开发电脑里的 `.git/config` 里添加如下设置：

```toml
[remote "prod"]
  url = ssh://username@server/~/app/weyoungcity.git
```

然后运行 `git push prod`，代码就跑到了服务器上！

随后在服务器上运行：

```bash
cd ~/app
git clone weyoungcity.git
```

这会创建代码文件夹 `~/app/weyoungcity`。

## 配置软件环境

python 环境与选手的配置方法类似。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[prod] --trusted-host mirrors.cloud.aliyuncs.com --index-url http://mirrors.cloud.aliyuncs.com/pypi/simple/
```

Podman 环境使用：

```bash
podman build -t judged .
```

## 开始评测

评测程序会处理提交时间在要求区间内的所有提交。对每个选手的每个问题，评测程序只允许提交时间最迟的提交，其他提交会被忽略。

```bash
.venv/bin/python judge.py -s 20250925T000000 -e 20250928T235959
```

目前必须手动启动评测。
