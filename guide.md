# A2A Kubernetes Playground 本地使用指南

本文以当前代码为准，包含完整启动、健康检查、多智能体执行流程、回归测试和常见故障排查。

## 1. 启动 Backend、可选 Agent 和 Frontend

以下命令都在项目根目录执行。首次运行前先按照第 4、6 节配置 `.env` 并安装依赖。

### 终端 1：K8s 资源编排 Agent

```bash
agents/.venv/bin/python agents/k8s-orchestrator/main.py
```

### 终端 2：K8s Ops Agent

```bash
agents/.venv/bin/python agents/k8s-ops/main.py
```

### 终端 3：K8s Security Agent

```bash
agents/.venv/bin/python agents/k8s-security/main.py
```

其他可选 Agent：

```bash
agents/.venv/bin/python agents/k8s-infrastructure/main.py
agents/.venv/bin/python agents/k8s-helm/main.py
```

### Backend

```bash
export PLAYGROUND_ALLOW_PRIVATE_AGENTS=true
# 可选：只填写当前希望预注册且已经可访问的 Agent；也可以不设置。
export BOOTSTRAP_AGENTS='[]'

backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8050
```

### 终端 5：Frontend

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

启动后访问 <http://127.0.0.1:5173>。Backend 不依赖本地 Agent，可在零 Agent 时先启动；之后可从 Agent 页面注册本地或外部 A2A Server。

## 2. 服务与端口

| 服务 | 默认端口 | 说明 |
| --- | ---: | --- |
| Frontend | 5173 | Vite 开发服务器 |
| Backend | 8050 | FastAPI、Host Agent、Run/Event/Approval API |
| K8s 资源编排 Agent | 8051 | 通过 MCP 创建和管理 Kubernetes 资源，写操作需要审批 |
| K8s Ops Agent | 8052 | 集群运行状态与运维诊断 |
| K8s Security Agent | 8053 | RBAC、配置和安全风险审计 |
| K8s Infrastructure Agent | 8054 | 节点、默认类和集群注册管理 |
| K8s Helm Agent | 8055 | Helm release 生命周期 |

主要页面：

- `/dashboard`：运行总览。
- `/workspace?mode=auto`：Host Agent 多智能体协作。
- `/workspace?mode=direct`：直接调用指定 Agent。
- `/agents`：Agent 状态、依赖检查和详情。
- `/events`：执行事件摘要、完整事件、异常和工具调用。
- `/multi`：兼容地址，会重定向到 `/workspace?mode=auto`。

## 3. 环境要求

- Python 3.11 或更高版本。
- Node.js 18 或更高版本。
- 可用的 DeepSeek/OpenAI 兼容模型服务。
- 可选：可访问的 Kubernetes MCP Streamable HTTP 或旧 SSE 服务。
- 可选：Docker 和 Docker Compose。

项目目录：

```bash
cd /Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1
```

## 4. 环境变量

Backend 从启动目录的 `.env` 或当前 Shell 环境读取配置。每个 Agent 还会分别读取自己目录下的 `.env`。

Backend 直接启动时复制独立示例：

```bash
cp backend/.env.example backend/.env
```

`backend/.env` 示例：

```dotenv
HOST_LLM_PROVIDER=deepseek
HOST_LLM_API_KEY=your-host-key
HOST_LLM_BASE_URL=https://api.deepseek.com/v1
HOST_LLM_MODEL=deepseek-chat

PLAYGROUND_ALLOW_PRIVATE_AGENTS=true
```

不配置时，Backend 默认使用：

- SQLite：`backend/data/playground-local.db`
- `HOST_MAX_TASKS=6`
- `HOST_MAX_CONCURRENCY=3`
- `HOST_MAX_ATTEMPTS=2`

只有需要覆盖默认值时，才把这些变量写入 `.env`。

每个 Agent 都有独立示例，按需分别复制：

```bash
cp agents/k8s-ops/.env.example agents/k8s-ops/.env
cp agents/k8s-security/.env.example agents/k8s-security/.env
cp agents/k8s-orchestrator/.env.example agents/k8s-orchestrator/.env
cp agents/k8s-infrastructure/.env.example agents/k8s-infrastructure/.env
cp agents/k8s-helm/.env.example agents/k8s-helm/.env
```

每份 Agent `.env` 至少配置：

```dotenv
AGENT_LLM_PROVIDER=vllm
AGENT_LLM_API_KEY=your-agent-key
AGENT_LLM_BASE_URL=http://your-vllm-host:4000/v1
AGENT_LLM_MODEL=your-openai-compatible-model
K8S_MCP_URL=http://10.2.0.57:9096/mcp
MCP_TRANSPORT=streamable_http
```

新版 Streamable HTTP MCP Server 应改为：

```dotenv
K8S_MCP_URL=http://your-mcp-host:9096/mcp
MCP_TRANSPORT=streamable_http
```

`MCP_TRANSPORT` 只接受 `sse` 和 `streamable_http`；未配置时默认使用
`sse`。客户端不会自动探测或回退，请确保 endpoint 与 transport 匹配。

每个 `agents/k8s-*` 目录都使用自己的 `.env`，可以单独配置、启动或迁移。

不要将真实 API Key 提交到 Git。

## 5. 可选方式：Docker Compose 启动全部服务

Docker Compose 会启动三个可选本地 Agent、Backend 和 Frontend。Infrastructure 和 Helm Agent 源码仍保留，可按前文命令手动启动。Backend 与 Agent 没有启动依赖：

```bash
docker compose up --build
```

访问：

- Frontend：<http://127.0.0.1:5173>
- Backend：<http://127.0.0.1:8050>

停止并保留 SQLite 数据卷：

```bash
docker compose down
```

## 6. 首次安装依赖

五个 Agent 共用 `agents/.venv`：

```bash
python3 -m venv agents/.venv
agents/.venv/bin/pip install --upgrade pip
agents/.venv/bin/pip install -e agents/shared-runtime python-dotenv uvicorn
```

Backend 使用独立虚拟环境：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install fastapi uvicorn httpx pydantic python-dotenv a2a-sdk langgraph langchain-openai langchain-core
```

安装前端依赖：

```bash
npm --prefix frontend install
```

## 7. 手动启动命令说明

### 7.1 启动所需 Agent

分别在三个终端执行：

```bash
agents/.venv/bin/python agents/k8s-orchestrator/main.py
```

```bash
agents/.venv/bin/python agents/k8s-ops/main.py
```

```bash
agents/.venv/bin/python agents/k8s-security/main.py
```

### 7.2 启动 Backend

在项目根目录执行：

```bash
export PLAYGROUND_ALLOW_PRIVATE_AGENTS=true
export BOOTSTRAP_AGENTS='[{"id":"k8s-ops","url":"http://127.0.0.1:8052","risk_level":"read_only"},{"id":"k8s-orchestrator","url":"http://127.0.0.1:8051","risk_level":"write_approval"},{"id":"k8s-security","url":"http://127.0.0.1:8053","risk_level":"read_only"}]'

backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8050
```

`PLAYGROUND_ALLOW_PRIVATE_AGENTS=true` 是本地注册 `127.0.0.1` Agent 所必需的。

### 7.3 启动 Frontend

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

访问 <http://127.0.0.1:5173>。

## 8. 健康检查

### Backend

Backend 健康接口是 POST：

```bash
curl -sS -X POST http://127.0.0.1:8050/api/ping \
  -H 'Content-Type: application/json' \
  --data '{}'
```

### Agent HTTP 在线状态

```bash
curl -sS http://127.0.0.1:8051/.well-known/agent-card.json
curl -sS http://127.0.0.1:8052/.well-known/agent-card.json
curl -sS http://127.0.0.1:8053/.well-known/agent-card.json
```

Agent Card 返回 200 只表示 Agent HTTP 服务在线，不代表其 LLM、MCP 和 Kubernetes 依赖全部可用。

### Agent 依赖就绪状态

```bash
curl -sS http://127.0.0.1:8051/health/ready
curl -sS http://127.0.0.1:8052/health/ready
curl -sS http://127.0.0.1:8053/health/ready
```

Backend 聚合检查：

```bash
curl -sS -X POST http://127.0.0.1:8050/api/agents/health-check \
  -H 'Content-Type: application/json' \
  --data '{}'
```

状态含义：

- `Ready`：Agent 在线，必要依赖可用。
- `Degraded`：Agent 在线，但 LLM、MCP 或 Kubernetes 依赖不可用或未验证。
- `Offline`：Agent HTTP 服务不可达。
- `Unknown`：尚未完成健康检查。

MCP 暂时不可用时，Agent 仍会以 `Degraded` 状态启动，并在收到请求时重新尝试初始化；不会因为启动预热失败而直接退出。

## 9. Host Agent 多智能体流程

Auto 模式不是简单选择一个 Agent，而是按以下阶段执行：

1. Host 分析请求并生成结构化计划。
2. 校验任务数量、Agent 能力、依赖关系和风险策略。
3. 无依赖任务并行执行，有依赖任务等待前序结果。
4. 只向下游任务传递必要且标明来源的上下文。
5. 结果不足或调用失败时，在限制内重试。
6. 必要时选择能力兼容的替代 Agent。
7. Host 综合各 Agent 结果并生成最终回复。

默认限制：

- 最多 6 个任务。
- 最多 3 个任务并行执行。
- 每个任务最多尝试 2 次。

写操作始终进入审批流程。审批绑定工具名、参数和摘要；参数变化后必须重新审批。Direct 模式只调用用户指定的 Agent。

## 10. Events 与运行追踪

Workspace 会实时显示 Host 规划、任务创建、Agent 执行、重试、工具调用和结果综合阶段。右侧任务卡片可以打开查看任务输入、依赖、尝试次数、错误和返回结果。

Events 页面提供：

- 摘要：计划、任务、重试、结果和综合事件。
- 完整事件：所有标准化 RunEvent。
- 仅异常：失败、阻塞、取消和重试事件。
- 仅工具：工具调用和工具完成事件。

运行、事件和审批记录保存在 SQLite 中。SSE 连接中断后，Frontend 使用相同 `run_id` 和事件序号继续读取，不会创建新的 Run。

## 11. 回归测试

Backend 全量测试：

```bash
pytest -q
```

Frontend 全量测试：

```bash
npm --prefix frontend test
```

Frontend 生产构建：

```bash
npm --prefix frontend run build
```

提交前建议连续执行：

```bash
pytest -q && npm --prefix frontend test && npm --prefix frontend run build
```

## 12. 常见问题

### Agent 显示 Degraded

先打开 Agent 详情查看 HTTP、LLM、MCP 和 Kubernetes 检查结果。若出现 `MCP warm-up timed out`，检查 `K8S_MCP_URL`、网络连通性和 MCP 服务日志。

### Agent Card 正常但任务无结果

Agent Card 只能证明 HTTP 在线。继续检查 `/health/ready`，并确认 LLM Key 和 MCP 可用。

### Backend 无法注册本地 Agent

确认设置：

```bash
export PLAYGROUND_ALLOW_PRIVATE_AGENTS=true
```

### Frontend API 返回 404 或连接失败

确认 Backend 监听 8050，Frontend 监听 5173。

### 端口被占用

先查找对应进程：

```bash
lsof -nP -iTCP:8050-8053 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

确认进程确实属于本项目后再停止，避免误杀其他服务。
