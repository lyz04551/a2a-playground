# A2A Playground — 设计文档

## 1. 系统概览

A2A Playground 是一个基于 A2A（Agent-to-Agent Protocol）协议的智能体管理平台。用户可以通过 Web UI 注册远程 A2A 智能体、与单个智能体对话、查看任务事件，以及通过 **Host Agent**（多智能体路由器）将任务自动委派给最合适的子智能体。

### 核心功能

- 通过 URL 注册 A2A 智能体（自动发现 Agent Card 获取能力信息）
- 每个智能体支持多个对话，消息持久化保存
- 发送消息并实时接收流式响应（SSE）
- 可视化 A2A 任务生命周期事件
- **Host Agent 多智能体路由** — 自动将用户请求委派给最合适的子智能体
- 支持 LangGraph 和 Google ADK 两种 Host Agent 实现

---

## 2. 后端架构

### 2.1 组件图

```
   HTTP 请求 (前端 → 后端)
       |
       v
+------------------+     +------------------+     +-------------------+
|  FastAPI Router   |---->|  database.py     |     |  JSON 文件         |
|  (main.py)        |     |  (CRUD)          |---->|  (data/*.json)    |
+------------------+     +------------------+     +-------------------+
       |
       | (智能体通信)
       v
+------------------+     +------------------+     +-------------------+
|  a2a_client.py   |---->|  a2a-sdk v0.3+   |---->|  远程 A2A 智能体   |
|  (封装层)         |     |  (ClientFactory)  |     |  (JSON-RPC / SSE)  |
+------------------+     +------------------+     +-------------------+
       |
       | (Host Agent 路由)
       v
+------------------+     +------------------+     +-------------------+
|  host/           |     |  LangGraph / ADK  |     |  DeepSeek LLM     |
|  (多智能体路由器)  |---->|  (Agent + Tools)  |---->|  (路由决策)        |
+------------------+     +------------------+     +-------------------+
```

### 2.2 后端文件结构

```
backend/
├── main.py              # FastAPI 应用，~500 行，30+ 端点
├── models.py            # Pydantic 模型
├── database.py          # JSON 文件持久化层
├── a2a_client.py        # A2A SDK 封装层
├── .env                 # DeepSeek API Key 配置
├── host/
│   ├── agent.py         # ADK Host Agent 实现
│   ├── manager.py       # ADK Host Manager（桥接层）
│   ├── router.py        # ADK 路由工具
│   ├── langgraph_agent.py    # LangGraph Host Agent 实现
│   └── langgraph_manager.py  # LangGraph Host Manager（桥接层）
└── data/
    ├── agents.json          # 注册的智能体
    ├── conversations.json   # 对话会话
    ├── messages.json        # 消息历史
    └── events.json          # 任务事件
```

### 2.3 路由端点

#### 智能体管理 (`/api/agents/*`)

| 端点 | 功能 |
|------|------|
| `POST /api/agents/list` | 列出所有注册智能体 |
| `POST /api/agents/register` | 注册智能体（自动获取 Agent Card） |
| `POST /api/agents/fetch-card` | 仅获取 Agent Card 预览 |
| `POST /api/agents/get` | 获取单个智能体详情 |
| `POST /api/agents/delete` | 删除智能体 |

#### 对话管理 (`/api/conversation/*`)

| 端点 | 功能 |
|------|------|
| `POST /api/conversation/create` | 创建新对话（支持 `type: single\|multi`） |
| `POST /api/conversation/list` | 列出对话（支持按 agentId 或 type 过滤） |
| `POST /api/conversation/get` | 获取对话详情（含消息列表） |
| `POST /api/conversation/update` | 更新对话标题 |
| `POST /api/conversation/delete` | 删除对话（级联删除消息和事件） |

#### 消息交换 (`/api/message/*`)

| 端点 | 功能 |
|------|------|
| `POST /api/message/send` | 发送消息，阻塞返回完整回复 |
| `POST /api/message/send-stream` | 发送消息，SSE 流式返回 |
| `POST /api/message/list` | 获取消息历史 |

#### 事件观察 (`/api/events/*`)

| 端点 | 功能 |
|------|------|
| `POST /api/events/list` | 列出所有事件（仅当前注册智能体的） |
| `POST /api/events/query` | 按对话查询事件 |

#### Host Agent 多智能体路由 (`/api/host/*`, `/api/host-adk/*`, `/api/host-lg/*`)

| 端点 | 功能 |
|------|------|
| `POST /api/host/agents` | 列出可用子智能体 |
| `POST /api/host/send` | 简单关键词路由，阻塞发送 |
| `POST /api/host/send-stream` | 简单关键词路由，SSE 流式 |
| `POST /api/host-adk/send` | Google ADK 多智能体路由，SSE 流式 |
| `POST /api/host-lg/send` | LangGraph 多智能体路由，SSE 流式 |

### 2.4 持久化层

所有数据以 JSON 文件存储在 `data/` 目录：

- `agents.json` — 智能体 ID、名称、URL、描述、能力、技能列表
- `conversations.json` — 对话 ID、智能体ID、标题、类型（single/multi）、消息数
- `messages.json` — 消息 ID、对话ID、角色、内容、元数据（含 routing agent、tool calls 等）
- `events.json` — 事件 ID、对话ID、任务ID、事件类型（tool_call/tool_result/routing/status_update）、状态、内容

### 2.5 A2A 协议客户端 (`a2a_client.py`)

封装了 `a2a-sdk>=0.3.25` 的 `ClientFactory`，提供三个核心函数：

- `fetch_agent_card(url)` — 获取 Agent Card（默认 `/.well-known/agent-card.json`，向后兼容 `/.well-known/agent.json`）
- `send_message_to_agent(url, text, conv_id)` — 阻塞发送，返回完整响应
- `stream_message_to_agent(url, text, conv_id)` — SSE 流式发送，逐条 yield 事件

自动降级：
1. 优先尝试 `message/send`（新协议）
2. 遇到 400 错误自动降级到 `tasks/send`（旧协议）
3. 流式同理降级到 `tasks/sendSubscribe`

---

## 3. Host Agent 多智能体路由

### 3.1 架构概述

Host Agent 是一个智能路由器，它使用 LLM（DeepSeek Chat）来决定哪个子智能体最适合处理用户请求。

```
用户请求 → Host Agent (LLM Router) → 选择子智能体 → send_task 工具 → 子智能体回复
                                   ↓
                            list_remote_agents 工具
```

### 3.2 LangGraph 实现（推荐，当前默认）

`host/langgraph_agent.py` + `host/langgraph_manager.py`

**核心组件：**

- `LangGraphHostAgent` — 管理远程 A2A 连接，提供 `list_remote_agents` 和 `send_task` 工具
- `LangGraphHostManager` — 桥接层，将 LangGraph 事件流转换为前端 SSE 格式
- `RemoteAgentConnections` — 使用 `a2a-sdk` 连接远程智能体

**LangGraph 节点：**
```
HumanMessage → LLM (DeepSeek Chat) → 工具调用 (send_task / list_remote_agents)
                                    → 工具结果 → LLM → AIMessage (最终回复)
```

**系统提示词：**
```
You are an expert delegator. Delegate user requests to the best remote agent.
Tools:
- `list_remote_agents` — list available agents
- `send_task` — send a task to a specific agent by name

Available agents:
{"name": "travel planner Agent", "description": "travel planner", ...}
{"name": "Currency Agent", "description": "Helps with exchange rates", ...}
```

**流式事件格式（SSE）：**
```json
{"type": "tool_call", "tool": "send_task", "args": {"agent_name": "...", "message": "..."}, "id": "..."}
{"type": "tool_result", "tool": "send_task", "result": "...", "id": "..."}
{"type": "routing", "agent": "travel planner Agent"}
{"type": "text", "text": "好的，我来帮你规划北京之旅..."}
{"type": "done", "session_id": "...", "conversation_id": "..."}
```

### 3.3 Google ADK 实现（备选）

`host/agent.py` + `host/manager.py`

使用 Google ADK 的 `Runner` + `LiteLlm`（DeepSeek 模型），功能与 LangGraph 版本相同。

### 3.4 消息持久化流程

Host Agent 的每条消息（包括 tool calls 和子智能体回复）都会保存到后端：

1. 用户消息 → `db.add_message({role: "user", ...})`
2. 工具调用事件 → `db.add_event({event_type: "tool_call", ...})`
3. 工具结果事件 → `db.add_event({event_type: "tool_result", ...})`
4. 路由事件 → `db.add_event({event_type: "routing", ...})`
5. 最终回复 → `db.add_message({role: "agent", metadata: {routing_agent, tool_calls, tool_results}, ...})`

---

## 4. 前端架构

### 4.1 技术栈

- React 18 + React Router 6
- Ant Design 5（UI 组件库）
- Vite 5（构建工具）
- CSS（自定义样式 + Ant Design 主题）

### 4.2 组件树

```
App.jsx
├── Layout (Ant Design)
│   ├── Sider (侧边栏)
│   │   ├── Logo (A2A Playground)
│   │   └── Menu
│   │       ├── / (Agents 页面)
│   │       ├── /chat (Chat 页面)
│   │       ├── /events (Events 页面)
│   │       └── /multi (Multi-Agent 页面)
│   └── Content (路由出口)
│
├── AgentsPage (/)
│   ├── AgentCard (智能体卡片)
│   │   ├── Agent 名称、URL、版本、能力标签
│   │   ├── 描述、技能列表、输入输出格式
│   │   └── 聊天 / 删除 按钮
│   └── AddAgentModal
│       ├── URL 输入
│       ├── Agent Card 预览
│       └── 确认添加
│
├── ChatPage (/chat/:agentId?)
│   ├── Sidebar (左侧)
│   │   ├── Agent 选择器
│   │   ├── 新建对话按钮
│   │   └── 对话历史列表
│   ├── ChatArea (右侧)
│   │   ├── Agent 信息栏
│   │   ├── MessageBubble 列表
│   │   │   ├── 用户消息 (蓝色)
│   │   │   └── 智能体回复 (白色)
│   │   └── 输入框
│   └── EventsDrawer (浮动事件面板)
│
├── EventsPage (/events)
│   └── 事件列表（按类型和状态过滤）
│
└── MultiAgentPage (/multi)
    ├── Sidebar (左侧)
    │   ├── 子智能体标签
    │   ├── 新建对话按钮
    │   └── 对话历史列表
    ├── ChatArea (右侧)
    │   ├── ToolCallCard (工具调用展开/折叠)
    │   ├── MessageBubble
    │   │   ├── 用户消息 (蓝色)
    │   │   └── Host Agent 回复 (含 routing agent 名称)
    │   └── 输入框
    └── EventsDrawer (浮动事件面板)
```

### 4.3 API 层 (`api/api.js`)

所有后端 API 调用的统一封装，包含：

- `request()` — 通用 POST 请求，自动解析 `{success, result}` 格式
- `sendMessageStream()` — SSE 流式接收，自动解析 `data: {...}` 事件
- `hostLgSendStream()` — LangGraph Host Agent 流式接口
- `hostAdkSendStream()` — ADK Host Agent 流式接口

### 4.4 页面详解

#### AgentsPage

- 挂载时从 `/api/agents/list` 获取智能体列表
- 卡片形式展示，包括名称、URL、能力标签、描述、技能、输入输出格式
- 分页支持（每页 9 个）
- 添加、删除、跳转聊天

#### ChatPage

- 左侧：Agent 选择器 + 对话历史列表
- 右侧：聊天区域
- 消息气泡：用户蓝色，智能体白色
- 用户图标使用 `UserOutlined`，智能体使用首字母
- 浮动事件面板（右下角按钮）

#### MultiAgentPage

- 左侧：子智能体标签 + 对话历史列表
- 右侧：聊天区域，显示 tool calls 展开/折叠
- 每个子智能体分配独立颜色
- 消息气泡显示 routing agent 名称
- 支持切换对话历史，刷新后自动恢复

---

## 5. 关键数据流

### 5.1 注册智能体

```
前端输入 URL → POST /api/agents/register
→ 后端获取 Agent Card (A2ACardResolver)
→ 解析 name, description, capabilities, skills
→ 保存到 data/agents.json
→ 返回注册的智能体信息
```

### 5.2 单智能体聊天（SSE 流式）

```
前端 POST /api/message/send-stream
→ 后端保存用户消息
→ 调用 a2a-sdk stream_message_to_agent()
→ 逐条 yield SSE 事件
→ 前端 ReadableStream reader 逐条解析
→ 追加到消息气泡
→ 完成后保存智能体回复到后端
```

### 5.3 Host Agent 多智能体路由

```
前端 POST /api/host-lg/send
→ 后端创建/获取对话
→ 保存用户消息
→ LangGraph Agent 处理:
   1. list_remote_agents → 列出可用子智能体
   2. LLM 选择最佳子智能体
   3. send_task → 发送到子智能体
   4. 子智能体回复 → 返回给用户
→ 每步 yield SSE 事件 (tool_call, tool_result, routing, text)
→ 保存最终回复到后端
→ 前端显示 tool calls 展开/折叠 + 子智能体名称
```

---

## 6. 关键设计决策

### 6.1 JSON 文件 vs 数据库

当前使用 JSON 文件存储，零配置即可运行。数据文件可读可手动编辑。未来可迁移到 SQLite。

### 6.2 SSE vs WebSocket

使用 Server-Sent Events 而非 WebSocket：
- 标准 HTTP，无需协议升级
- `fetch()` ReadableStream 原生支持
- 前端无额外依赖
- 后端的 `StreamingResponse` 也无需额外库

### 6.3 LangGraph vs ADK

两种 Host Agent 实现，当前默认使用 LangGraph：
- **LangGraph** — 更轻量，依赖少，流式事件清晰
- **ADK** — 功能更丰富，但依赖 `google-adk` 包

### 6.4 重复内容去重

LangGraph 的 `stream_mode="values"` 每次迭代返回完整消息列表，可能导致相同 `ToolMessage` 被多次 yield。通过 `seen_tool_call_ids` 和 `seen_tool_result_ids` 集合去重。

### 6.5 A2A SDK Part 类型

SDK 的 `Part` 类型是 `RootModel[TextPart | FilePart | DataPart]`，文本提取必须通过 `part.root.text` 访问，而非 `isinstance(part, TextPart)`。

---

## 7. 启动指南

### 7.1 前提条件

- Python 3.11+
- Node.js 18+
- 一个或多个正在运行的 A2A 智能体

### 7.2 快速启动

```bash
cd a2a-playground
bash run.sh
```

后端运行在 `http://127.0.0.1:8050`，前端在 `http://127.0.0.1:5174`。

### 7.3 环境变量

在 `backend/.env` 中配置：

```env
DEEPSEEK_API_KEY="sk-..."
```

---

## 8. 未来改进方向

| 方向 | 描述 |
|------|------|
| **SQLite 持久化** | 替换 JSON 文件，支持并发访问 |
| **WebSocket** | 替代 SSE 实现双向通信 |
| **多用户** | 用户会话和对话隔离 |
| **智能体发现** | 集成 A2A Registry 自动发现 |
| **E2E 测试** | Playwright + pytest |
| **更多路由策略** | 基于关键词、向量相似度、历史表现等 |
| **子智能体流式转发** | 将子智能体的流式输出直接转发到前端 |
