# A2A Playground 本地启动指南

以下命令均在项目根目录执行：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-playground
```

## 手动启动

手动启动时，每个长期运行的服务需要占用一个终端。

### 1. 启动 PostgreSQL

当前项目依赖 PostgreSQL，因此需要先启动数据库：

```bash
docker compose up -d postgres
```

首次启动或数据库结构发生变化后，执行迁移：

```bash
set -a
source backend/.env
set +a
backend/.venv/bin/python -m backend.persistence.migrate
```

### 2. 启动三个主要 Agent

分别在三个终端执行以下命令。

K8s Resource Orchestrator Agent：

```bash
agents/.venv/bin/python agents/k8s-orchestrator/main.py
```

K8s Ops Agent：

```bash
agents/.venv/bin/python agents/k8s-ops/main.py
```

K8s Security Agent：

```bash
agents/.venv/bin/python agents/k8s-security/main.py
```

### 3. 启动后端

在新的终端中执行：

```bash
DATABASE_URL='postgresql+psycopg://a2a:a2a_dev_password@127.0.0.1:5432/playground' \
PLAYGROUND_ALLOW_PRIVATE_AGENTS=true \
backend/.venv/bin/python -m uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port 8050
```

### 4. 启动前端

在新的终端中执行：

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

## 服务端口

| 服务 | 端口 |
| --- | ---: |
| Frontend | 5173 |
| Backend | 8050 |
| K8s Resource Orchestrator Agent | 8051 |
| K8s Ops Agent | 8052 |
| K8s Security Agent | 8053 |

## Docker Compose 一键启动

如果不需要分别调试各个服务，可以直接构建并启动全部服务：

```bash
docker compose up --build
```

如需在后台运行：

```bash
docker compose up -d --build
```

停止 Compose 服务：

```bash
docker compose down
```

## 访问地址

启动完成后访问：

<http://127.0.0.1:5173>
