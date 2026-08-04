# 本地启动指南

项目目录：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1
```

## 1. 创建 Agent 虚拟环境

三个新 Agent 共用 `agents/.venv`：

```bash
python3.11 -m venv agents/.venv
agents/.venv/bin/pip install --upgrade pip
agents/.venv/bin/pip install -e agents/shared-runtime python-dotenv uvicorn
```

Backend 继续使用已有的 `backend/.venv` 和 `backend/.env`。

三个 Agent 分别读取自己目录中的 `.env`。启动前，请在以下文件中填写
`DEEPSEEK_API_KEY`：

```text
agents/k8s-orchestrator/.env
agents/k8s-ops/.env
agents/k8s-security/.env
```

安装前端依赖：

```bash
npm --prefix frontend install
```

## 2. 启动三个 Agent

打开三个终端，分别执行。

终端 1：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1
agents/.venv/bin/python agents/k8s-orchestrator/main.py
```

终端 2：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1
agents/.venv/bin/python agents/k8s-ops/main.py
```

终端 3：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1
agents/.venv/bin/python agents/k8s-security/main.py
```

## 3. 启动 Backend

终端 4：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1

export PLAYGROUND_DB_PATH="$PWD/backend/data/playground-local.db"
export PLAYGROUND_ALLOW_PRIVATE_AGENTS=true
export BOOTSTRAP_AGENTS='[{"id":"k8s-ops","url":"http://127.0.0.1:8052","risk_level":"read_only"},{"id":"k8s-orchestrator","url":"http://127.0.0.1:8051","risk_level":"write_approval"},{"id":"k8s-security","url":"http://127.0.0.1:8053","risk_level":"read_only"}]'

backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8050
```

## 4. 启动前端

终端 5：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1
npm --prefix frontend run dev -- --host 127.0.0.1
```

访问：

- 首页：<http://127.0.0.1:5173>
- Multi-Agent：<http://127.0.0.1:5173/multi>

停止服务时，在对应终端按 `Ctrl+C`。
