# A2A Playground 后端代码导读

> 这份文档只讲 `backend/`，不涉及前端和 `agents/` 的内部实现。
> 目标不是逐行解释代码，而是帮助你先建立地图，再沿着一次真实请求读懂后端。

## 1. 一句话理解这个后端

这是一个 FastAPI 服务，负责：

1. 注册和查询远程 A2A Agent；
2. 保存会话、消息、运行记录和事件；
3. 以 Direct 模式把请求交给指定 Agent；
4. 以 Auto 模式让 Host LLM 决定如何拆任务、选择 Agent、并发执行和汇总结果；
5. 把运行过程保存到 SQLite，并通过 SSE 持续返回；
6. 在写操作前暂停运行，等待人工审批。

主链路可以压缩成：

```text
HTTP 请求
  -> backend/api/runs.py
  -> backend/orchestration/service.py
  -> DirectExecutionStrategy 或 AutoExecutionStrategy
  -> A2AGateway 或 HostOrchestrationEngine
  -> 远程 A2A Agent
  -> RunEvent
  -> SQLite 持久化
  -> SSE 响应
```

## 2. 先看目录地图

```text
backend/
├── main.py                    FastAPI 装配入口，同时保留少量旧接口
├── settings.py                HTTP 安全和 Host 执行上限
├── llm_config.py              Host LLM 环境变量读取
├── security.py                Agent URL / SSRF 防护
├── models.py                  旧接口和通用 API 的 Pydantic 模型
├── database.py                全局 SQLiteRepository 和旧式兼容函数
│
├── api/
│   ├── agents.py              Agent 注册、查询、删除、健康检查
│   ├── conversations.py       会话、消息和事件查询
│   └── runs.py                统一 Run、SSE、取消、恢复和审批 API
│
├── orchestration/
│   ├── commands.py            RunCommand 输入模型
│   ├── events.py              RunEvent 统一事件模型
│   ├── service.py             Run 生命周期、持久化、取消和恢复
│   └── strategies.py          Direct / Auto 两种执行策略
│
├── host/
│   ├── orchestration/
│   │   ├── models.py          Host 计划、任务、结果和状态模型
│   │   ├── validation.py      计划、依赖、风险和 Agent 能力校验
│   │   ├── context.py         为子任务拼装上下文
│   │   └── engine.py          Host 多轮决策、并发调度、重试和汇总
│   └── langgraph/
│       ├── agent.py           创建 OpenAI 兼容模型
│       ├── decisions.py       LLM 结构化决策适配器
│       └── manager.py         Host Engine 与 A2A Gateway 的连接层
│
├── registry/service.py        Agent 能力查询和候选 Agent 排序
├── a2a_client.py              A2A SDK 的底层请求与事件解析
├── a2a_gateway.py             编排层使用的 A2A 统一网关
├── approvals/service.py       审批只执行一次及审批后续传
│
├── persistence/
│   ├── models.py              SQLAlchemy Core 表定义
│   ├── repository.py          所有 SQLite 读写
│   └── migrate_json.py        旧 JSON 数据的一次性导入
│
└── events/
    ├── single_agent.py        旧单 Agent SSE 事件中继
    └── feed.py                将新旧事件整理成统一查询视图
```

## 3. 推荐阅读顺序

不要先啃最长的 `service.py` 和 `strategies.py`。推荐分四轮读。

### 第一轮：只建立骨架

1. `backend/main.py`
2. `backend/orchestration/commands.py`
3. `backend/orchestration/events.py`
4. `backend/api/runs.py`

读完要能回答：服务如何启动、请求长什么样、事件长什么样、SSE 从哪里返回。

### 第二轮：读一次 Run 的生命周期

5. `backend/orchestration/service.py` 中的 `stream()`、`_stream()`、`cancel()`
6. `backend/orchestration/strategies.py` 中的 `DirectExecutionStrategy`
7. `backend/a2a_gateway.py`

读完要能回答：Direct 请求如何创建 Run、调用 Agent、保存事件、完成或失败。

### 第三轮：只追 Auto 多 Agent 主线

8. `backend/orchestration/strategies.py` 中的 `AutoExecutionStrategy`
9. `backend/host/langgraph/manager.py`
10. `backend/host/orchestration/engine.py`
11. `backend/host/langgraph/decisions.py`
12. `backend/host/orchestration/validation.py`

读完要能回答：Host 如何决定下一步、任务为何能并发、如何重试、何时停止。

### 第四轮：理解数据和安全

13. `backend/persistence/models.py`
14. `backend/persistence/repository.py`，按调用点查方法即可，不必顺读 800 行
15. `backend/approvals/service.py`
16. `backend/security.py` 和 `backend/settings.py`

## 4. 后端是如何装配起来的

入口是：

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8050
```

导入 `backend.main` 时会依次发生：

1. `database.py` 创建全局 `SQLiteRepository`；
2. 初始化数据表，并尝试导入旧 JSON 数据；
3. `main.py` 创建 FastAPI `app`；
4. 配置 CORS 和可选 Bearer Token；
5. 挂载 Agent、Conversation、Run 和 Approval 路由；
6. 创建 `A2AGateway`、`AgentRegistry`、Host Manager 和 `RunService`；
7. FastAPI startup 阶段恢复异常中断的 Run，并注册 `BOOTSTRAP_AGENTS`。

核心对象关系：

```text
FastAPI app
  └── Run routes
      └── RunService
          ├── SQLiteRepository
          ├── AgentRegistry
          ├── A2AGateway
          └── LangGraphHostManager
              └── HostOrchestrationEngine
                  ├── AgentRegistry
                  ├── LangGraphDecisionPort
                  └── delegate callback -> A2AGateway
```

这里大量使用构造函数注入，而不是在业务类中临时创建依赖，因此测试可以传入 Fake Repository、Fake Gateway 或 Fake Host。

## 5. 最重要的三个数据模型

### 5.1 RunCommand：用户想做什么

```python
class RunCommand(BaseModel):
    conversation_id: str | None
    mode: Literal["direct", "auto"]
    target_agent_id: str | None
    message: str
```

- `direct` 必须提供 `target_agent_id`；
- `auto` 会主动丢弃 `target_agent_id`，避免旧 UI 状态干扰 Host；
- `message` 长度为 1 到 20,000 字符。

### 5.2 RunEvent：系统发生了什么

每个事件都有：

```text
event_id        全局事件 ID，用于去重
sequence        同一个 Run 内严格递增的顺序号
run_id          本次运行 ID
conversation_id 所属会话
task_id         可选，所属任务
type            事件类型
timestamp       带时区的 UTC 时间
data            各事件自己的载荷
```

常见事件顺序：

```text
run.started
host.round_started
host.decision_created
task.context_prepared
task.delegated
task.started
tool.called / tool.completed
message.delta / message.completed
task.evaluated
task.completed
host.round_completed
message.completed
run.completed
```

### 5.3 HostRunState：Host 已经知道什么

Auto 模式不是只调用一次 LLM。Host 会持有：

- 当前目标和轮次；
- 历次决策；
- 已观察到的任务结果；
- 已成功任务；
- 已执行任务的语义指纹；
- 等待审批的任务；
- 总任务数。

这个状态会作为 checkpoint 持久化，所以审批完成后可以从原位置继续，而不是从头再规划。

## 6. Direct 模式完整调用链

请求示例：

```json
{
  "mode": "direct",
  "target_agent_id": "ops-agent",
  "message": "检查 default 命名空间中的 Pod"
}
```

调用顺序：

```text
POST /api/runs/stream
  -> runs.py::_command()
  -> RunService.stream()
  -> RunService._stream()
      -> 创建 Conversation（如需要）
      -> 创建 Run 和 root task
      -> 保存用户消息
      -> 保存并发送 run.started
  -> DirectExecutionStrategy.execute()
      -> AgentRegistry.get(target_agent_id)
      -> A2AGateway.delegate_stream()
      -> a2a_client.stream_message_to_agent()
      -> 翻译远端事件为 RunEvent
  -> RunService 先持久化每个事件，再 yield
  -> 更新 Run/root task 状态
  -> 保存并发送 run.completed 或 run.failed
```

关键点：`RunService` 管生命周期，Strategy 管“怎样执行”。两者不要混在一起理解。

## 7. Auto 模式完整调用链

请求示例：

```json
{
  "mode": "auto",
  "message": "检查集群安全问题并给出处理建议"
}
```

调用顺序：

```text
RunService
  -> AutoExecutionStrategy
  -> LangGraphHostManager.process_message_stream()
  -> HostOrchestrationEngine.stream()
  -> LangGraphDecisionPort.decide_next()
  -> HostDecision
```

当前主流程优先使用多轮 ReAct 式决策：每一轮 LLM 只能选择一种动作：

- `delegate`：创建 1 到 3 个当前轮可以并行的任务；
- `clarify`：缺少关键信息，向用户追问；
- `request_approval`：请求写操作授权；
- `complete`：目标已经满足，生成回答；
- `stop`：继续执行不安全或不可能。

当动作是 `delegate` 时，Engine 会：

1. 用确定性规则校验任务和 Agent 能力；
2. 为每个任务构造包含历史观察的 prompt；
3. 用 `asyncio.gather()` 并发运行本轮任务；
4. 用 Semaphore 限制最大并发量；
5. 把 Agent 的工具调用和文本增量作为进度事件向上转发；
6. 让 LLM 对每个结果做 `sufficient / insufficient / failed / blocked` 评价；
7. 必要时重试，失败时可按能力选择替代 Agent；
8. 把结果写入 `HostRunState`，进入下一轮决策。

这意味着“LLM 决策”和“系统安全约束”是两层：LLM 提议，`validation.py` 再做不可绕过的确定性校验。

## 8. SSE 为什么能重连

首次请求 `/api/runs/stream` 时，API 会创建一个后台 producer：

```text
RunService.stream() -> asyncio.Queue -> StreamingResponse
```

因此 HTTP 客户端暂时断开，不会立刻杀死正在执行的后台 Run。

重连时客户端传：

```json
{
  "run_id": "已有的 run id",
  "after_sequence": 12
}
```

后端会：

1. 从 SQLite 返回 `sequence > 12` 的历史事件；
2. 如果 Run 仍在执行，则等待新事件通知；
3. 15 秒没有新事件时发送 SSE heartbeat；
4. Run 进入终态后关闭事件流。

所以 `sequence` 不只是展示顺序，也是可靠重放的游标。

## 9. A2A 边界怎么分层

两个文件名字很像，但层次不同：

### `a2a_client.py`

负责协议和 SDK 细节：

- 获取 Agent Card；
- 健康检查；
- 构造 A2A Message；
- 普通发送和流式发送；
- 兼容旧版 A2A 方法；
- 从 Task、Artifact、Status 中提取文本；
- 将网络异常转换成公开错误。

### `a2a_gateway.py`

负责业务语义：

- 根据 Agent ID 和 Run 保存远端 `context_id / task_id` 绑定；
- 将远端流转换成编排层可消费的字典事件；
- 从 artifact 中提取 `specialist_result` 和 `pending_action`；
- 发现待审批操作时创建 Approval；
- 对工具参数和结果中的 secret、token、cookie 等字段脱敏；
- 截断过长的公开文本。

记忆方法：Client 懂 A2A 协议，Gateway 懂本项目的 Run。

## 10. 审批流程

写操作不会直接继续执行：

```text
Agent 返回 input-required + pending_action artifact
  -> A2AGateway 创建 approvals 记录
  -> Run 状态变为 approval_required
  -> SSE 发出 approval.required
  -> POST /api/approvals/decide
  -> ApprovalService 原子领取该决定
  -> 用相同远端 task_id 发送 approval_decision
  -> Auto Run 从 Host checkpoint 恢复
```

`claim_approval_decision()` 用于防止重复点击导致同一个写操作执行两次。审批记录还保存 `action_digest`，让待批准动作可以被稳定识别。

## 11. SQLite 保存了什么

默认数据库：

```text
backend/data/playground-local.db
```

可用 `PLAYGROUND_DB_PATH` 修改。

主要表：

| 表 | 作用 |
|---|---|
| `agents` | 已注册 Agent 和完整 Agent Card 数据 |
| `conversations` | 会话元数据 |
| `messages` | 用户、Agent 和 Host 消息 |
| `events` | 新旧事件；Run 事件用 `(run_id, sequence)` 保证唯一 |
| `orchestration_runs` | Run 状态、模式、请求和 Host checkpoint |
| `orchestration_tasks` | 根任务和委派子任务 |
| `remote_task_bindings` | 本地 Run/Agent 到远端 A2A context/task 的映射 |
| `approvals` | 待审批及已处理写操作 |
| `artifacts` | Run 产物 |
| `migrations` | 数据迁移记录 |

`persistence/repository.py` 是唯一主要数据库访问层。阅读其他代码时遇到 Repository 方法，再回到这里按方法名查，比从头读到尾更高效。

## 12. API 速查

### 主 Run API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/runs/stream` | 新建 Run 或重连 SSE |
| POST | `/api/runs/get` | Run、任务和审批详情 |
| POST | `/api/runs/list` | Run 列表，可选分页 |
| POST | `/api/runs/events` | 按 sequence 重放事件 |
| POST | `/api/runs/cancel` | 取消 Run |
| POST | `/api/approvals/list` | 查询审批 |
| POST | `/api/approvals/decide` | 批准或拒绝操作 |
| POST | `/api/system/status` | Host 模型配置状态，不返回 API Key |

### Agent 和会话 API

| 路径前缀 | 用途 |
|---|---|
| `/api/agents/*` | Agent 列表、Card、注册、删除、健康检查 |
| `/api/conversation/*` | 会话创建、列表、详情、更新、删除 |
| `/api/message/list` | 查询旧式会话消息 |
| `/api/events/*` | 查询整理后的新旧事件 Feed |

### 旧兼容接口

- `/api/message/send`
- `/api/message/send-stream`

它们是旧单 Agent 链路。新功能应优先追 `/api/runs/stream`。

`/api/host/send` 和 `/api/host/send-stream` 已返回 HTTP 410，不再有独立的关键词路由实现。

## 13. 配置和安全边界

常用环境变量：

| 变量 | 作用 |
|---|---|
| `HOST_LLM_API_KEY` | Host 模型密钥 |
| `HOST_LLM_BASE_URL` | OpenAI 兼容模型地址 |
| `HOST_LLM_MODEL` | 模型名 |
| `PLAYGROUND_DB_PATH` | SQLite 文件路径 |
| `PLAYGROUND_API_KEY` | 为 `/api/*` 开启 Bearer Token；`/api/ping` 除外 |
| `PLAYGROUND_CORS_ORIGINS` | 允许的前端 Origin，逗号分隔 |
| `PLAYGROUND_ALLOW_PRIVATE_AGENTS` | 是否允许注册内网或回环 Agent |
| `A2A_CLIENT_TIMEOUT` | A2A 请求超时秒数，默认 120 |
| `HOST_MAX_TASKS` | 单次 Auto Run 最大任务数 |
| `HOST_MAX_ROUNDS` | Host 最大决策轮数 |
| `HOST_MAX_CONCURRENCY` | 最大并发 Agent 数 |
| `HOST_MAX_ATTEMPTS` | 单任务最大尝试次数 |
| `BOOTSTRAP_AGENTS` | 启动时注册的 Agent JSON 数组 |

需要注意的防护：

- `security.py` 阻止危险协议、URL 用户名密码、无法解析地址以及默认的私网/回环地址；
- 本地开发注册 `127.0.0.1` Agent 时必须显式打开 `PLAYGROUND_ALLOW_PRIVATE_AGENTS=true`；
- `settings.py` 对 Host 上限做范围校验；
- Gateway 在事件离开后端前脱敏常见凭据字段；
- LLM 的结构化输出必须通过 Pydantic 和确定性业务规则双重校验。

## 14. 哪些文件暂时可以跳过

刚开始读时可以先跳过：

- `backend/host/agent.py`
- `backend/host/manager.py`
- `backend/host/router.py`
- `backend/host/langgraph_agent.py`
- `backend/host/langgraph_manager.py`
- `backend/host/adk/`

当前 `main.py` 实际装配的是 `backend.host.langgraph.manager.get_manager()`。上面这些主要是旧实现、兼容入口或另一套 ADK 适配器，不是当前 Run 主线。

同样，`events/single_agent.py` 只服务旧 `/api/message/send-stream`；理解统一 Run 时先不用读。

## 15. 调试时从哪里下断点

### 请求没有进入后端

- `backend/main.py` 的 `/api/ping`
- `backend/api/runs.py::runs_stream`
- 检查 `PLAYGROUND_API_KEY` 和 CORS

### Agent 注册失败或离线

- `backend/api/agents.py::AgentService.register`
- `backend/security.py::validate_agent_url`
- `backend/a2a_client.py::fetch_agent_card`
- `backend/a2a_client.py::check_agent_health`

### Run 建立了但没有事件

- `backend/orchestration/service.py::RunService._stream`
- `backend/orchestration/strategies.py::execute`
- SQLite `events` 表中的 `run_id / sequence`

### Auto 模式没有正确拆任务

- `backend/host/langgraph/decisions.py::decide_next`
- `backend/host/orchestration/validation.py::validate_decision`
- `backend/host/orchestration/engine.py::_stream_react`

### Agent 调用失败

- `backend/host/langgraph/manager.py::_delegate_task`
- `backend/a2a_gateway.py::delegate_stream`
- `backend/a2a_client.py::stream_message_to_agent`

### 审批后没有继续

- `backend/approvals/service.py::decide`
- `backend/orchestration/service.py::resume_after_approval`
- `remote_task_bindings` 和 `approvals` 表

## 16. 后端测试怎么对应代码

```text
test_runs_api.py                    Run HTTP/SSE API
test_run_service.py                Run 生命周期、取消和恢复
test_execution_strategies.py       Direct/Auto 事件翻译
test_host_orchestration_engine.py  Host 调度、并发、重试
test_host_plan_validation.py       计划确定性校验
test_langgraph_host_decisions.py   LLM 结构化决策适配
test_a2a_gateway.py                A2A 网关和远端绑定
test_a2a_client.py                 A2A SDK 兼容和错误处理
test_approval_service.py           审批幂等和续传
test_persistence.py                基础数据持久化
test_run_repository.py             Run/Task/Event 数据操作
test_security.py                   Agent URL 安全校验
```

运行全部后端测试：

```bash
backend/.venv/bin/python -m pytest -q tests/backend
```

只验证一次 Run 主链路：

```bash
backend/.venv/bin/python -m pytest -q \
  tests/backend/test_runs_api.py \
  tests/backend/test_run_service.py \
  tests/backend/test_execution_strategies.py
```

## 17. 最后用这五个问题检查是否读懂

1. `RunService` 和 `ExecutionStrategy` 为什么分开？
2. Direct 和 Auto 从哪一行开始走向不同路径？
3. Host 的 LLM 决策为什么不能直接执行，必须再过 `validation.py`？
4. SSE 断开后为什么不会丢事件，`sequence` 在其中起什么作用？
5. 审批完成后，系统怎样找到原来的远端 A2A Task 并继续执行？

如果这五个问题都能顺着文件和函数回答，后端主干就已经读通了。之后再针对具体问题深入 Repository、A2A SDK 兼容层或历史接口即可。
