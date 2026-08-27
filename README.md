# A2A Playground

A full-stack web application for managing and chatting with A2A (Agent-to-Agent) protocol agents. Built with **FastAPI** backend and **React + Ant Design** frontend. Features **Host Agent** multi-agent routing powered by LangGraph / LLM.

## Engineering MVP

The current architecture keeps every Kubernetes specialist as an independent
`a2a-sdk==0.3.25` service:

| Service | Stable ID | Responsibility | MCP policy |
|---|---|---|---|
| K8s Ops | `k8s-ops` | Inspection and approved Pod debugging | Writes require approval |
| K8s Resource Orchestrator | `k8s-orchestrator` | Creates and manages Kubernetes resources | Every write requires approval |
| K8s Security | `k8s-security` | Workload, RBAC, image and network assessment | Read-only |
| K8s Infrastructure | `k8s-infrastructure` | Node, class and cluster registry operations | Writes require approval |
| K8s Helm | `k8s-helm` | Helm release lifecycle | Writes require approval |

The LangGraph Host lives in the backend and delegates only through A2A. It routes
with stable IDs and reuses each child Agent's A2A context inside an orchestration
run. The run is a durable SQLite trace, not a fixed workflow: the Host LLM remains
responsible for asking questions, selecting Agents, and deciding when to summarize.

The shared runtime under `agents/shared-runtime` provides MCP connection handling,
tool schema adaptation, deterministic allow/deny policy, approval digests, A2A task
status, and artifacts. Direct single-Agent chat remains supported.

### One-command startup

```bash
# For Docker Compose, create a root .env from the service examples:
cp backend/.env.example .env
# Add any AGENT_LLM_* values you want from agents/k8s-ops/.env.example,
# then fill the Host and Agent API keys locally.
docker compose up --build
```

Open `http://localhost:5173`. Compose starts the frontend, backend, and three
independent A2A Agent servers on ports 8051–8053. The backend discovers them through
their Agent Cards and stores data in `/app/data/playground.db`.

The backend has no startup dependency on these local Agents. It remains healthy with
zero or partial local Agents, and arbitrary external A2A servers can be registered at
runtime through the Agent API or UI.

The existing JSON files are imported into SQLite once on first startup and remain
unchanged as backups.

### Safety model

- Read-only inspection tools execute automatically.
- Kubernetes mutations stop the A2A task in `input_required`.
- The Playground shows the exact tool, target, arguments, and action digest.
- Approval resumes the same Agent run; changed arguments require a new approval.
- Pod exec/file operations, cluster registry changes, node maintenance, resource
  deletion and Helm mutations are exposed only by their owning Agent and require approval.

---

## Architecture

```
┌──────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────┐
│   React + Ant Design     │ SSE  │   FastAPI Backend        │ A2A  │   Remote Agent   │
│   (Vite 5)               │<────>│   (Python / uvicorn)     │<────>│   (A2A Protocol) │
│                          │ HTTP │                          │JSON  │                  │
│   Port 5173              │      │   Port 8050              │ RPC  │   Ports vary     │
└──────────────────────────┘      └──────────────────────────┘      └──────────────────┘
                                         │
                                         v
                                 ┌──────────────────┐     ┌─────────────────────┐
                                 │  SQLite DB        │     │  Host Agent         │
                                 │  (data/*.json)    │     │  LangGraph / ADK    │
                                 └──────────────────┘     │  + DeepSeek Chat     │
                                                          └─────────────────────┘
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Agent Management** | Register A2A agents by URL, auto-discover Agent Card |
| **Single Chat** | Chat with individual agents, SSE streaming responses |
| **Multi-Agent Chat** | Host Agent routes requests to the best sub-agent via LLM |
| **Tool Visibility** | Tool calls (send_task, list_remote_agents) shown in chat |
| **Persistent History** | Conversations, messages, runs, approvals, and events saved transactionally in SQLite |
| **Task Events** | Full event log with tool_call, tool_result, routing events |
| **Pagination** | Agent cards paginated (9 per page) |

### Operations console experience

The frontend includes a responsive operations console designed for internal
engineering and Kubernetes operations workflows:

- Dashboard with live Agent, run, approval, and model-configuration summaries.
- Global `Command+K` / `Ctrl+K` search for pages, Agents, conversations, and
  loaded events.
- Light and dark themes, comfortable and compact density, collapsible
  navigation, and Chinese/English shell labels.
- Kubernetes prompt templates for health checks, abnormal Pod analysis,
  security reviews, warning-event triage, and deployment reviews.
- Searchable and renameable conversations, message copy actions, responsive
  conversation/trace drawers, and deep links from Dashboard search results.
- Host → Agent → Tool execution timeline and a debugger drawer with raw SSE
  events, IDs, elapsed time, and copyable JSON.
- First-use guidance and resilient partial-data states when one dashboard API
  is unavailable.

Token statistics are displayed only when the backend supplies real usage data.
Server-side full-text search, favorites, pinning, regenerate, and historical
analytics remain follow-up features.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- At least one running A2A agent (e.g., from [a2a-samples](https://github.com/GoogleCloudPlatform/a2a-samples))
- A DeepSeek API key with balance (for Host Agent routing)

### 1. Start A2A Agents

Start your A2A agents first (examples from a2a-samples):

```bash
# Travel planner agent
cd samples/python/agents/travel_planner_agent && uv run
# Currency agent
cd samples/python/agents/langgraph && uv run app
```

### 2. Start the Backend and Frontend

```bash
# Backend (from the project root)
PLAYGROUND_ALLOW_PRIVATE_AGENTS=true backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8050

# Frontend (in another terminal)
npm --prefix frontend run dev -- --host 127.0.0.1
```

### 3. Open the UI

Open [http://127.0.0.1:5173](http://127.0.0.1:5173) in your browser.

### Manual Setup

```bash
# Backend (run from the repository root)
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
PLAYGROUND_ALLOW_PRIVATE_AGENTS=true backend/.venv/bin/python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8050 --log-level info

# Frontend
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5173
```

---

## Usage Guide

### Adding an Agent

1. Go to **Agents** page
2. Click **Add Agent** button
3. Enter agent URL (e.g., `localhost:10001`)
4. Click **Fetch** to retrieve Agent Card
5. Review capabilities and skills
6. Click **Add Agent**

### Single Agent Chat

1. Go to **Chat** page
2. Select an agent from the dropdown
3. Click **New Chat**
4. Type your message and press Enter

### Multi-Agent Chat (Host Agent)

1. Go to **Multi** page (sidebar)
2. Ensure agents are registered on the **Agents** page
3. Click **New** to start a conversation
4. Ask anything — Host Agent will:
   - Use `list_remote_agents` to find available agents
   - Call `send_task` to delegate to the best agent
   - Show tool calls and results in the chat
   - Return the final response

### Viewing Events

- Click the document button (bottom-right corner) during a chat
- Or go to the **Events** page

---

## API Reference

All endpoints accept `POST` with `Content-Type: application/json`.

### Agents

| Endpoint | Body | Description |
|----------|------|-------------|
| `POST /api/ping` | `{}` | Health check |
| `POST /api/agents/list` | `{}` | List all registered agents |
| `POST /api/agents/register` | `{"agentAddress": "..."}` | Register a new agent |
| `POST /api/agents/fetch-card` | `{"agentAddress": "..."}` | Preview agent card only |
| `POST /api/agents/get` | `{"agentId": "..."}` | Get agent details |
| `POST /api/agents/delete` | `{"agentId": "..."}` | Remove an agent |

### Conversations

| Endpoint | Body | Description |
|----------|------|-------------|
| `POST /api/conversation/create` | `{"agentId": "...", "type": "single\|multi"}` | Create conversation |
| `POST /api/conversation/list` | `{"agentId": "..."}` or `{"type": "..."}` | List conversations |
| `POST /api/conversation/get` | `{"conversationId": "..."}` | Get detail + messages |
| `POST /api/conversation/update` | `{"conversationId": "...", "title": "..."}` | Rename |
| `POST /api/conversation/delete` | `{"conversationId": "..."}` | Delete with messages + events |

### Messages

| Endpoint | Body | Description |
|----------|------|-------------|
| `POST /api/message/send` | `{"conversation_id": "...", "content": "..."}` | Send, get full reply |
| `POST /api/message/send-stream` | `{"conversation_id": "...", "content": "..."}` | Send, SSE streaming |
| `POST /api/message/list` | `{"conversationId": "..."}` | Get message history |

### Events

| Endpoint | Body | Description |
|----------|------|-------------|
| `POST /api/events/list` | `{}` | List all events (current agents only) |
| `POST /api/events/query` | `{"conversationId": "..."}` | Events for a conversation |

### Host Agent (Multi-Agent)

| Endpoint | Body | Description |
|----------|------|-------------|
| `POST /api/host/agents` | `{}` | List agents available for routing |
| `POST /api/host/send` | `{"content": "..."}` | Keyword-based routing, blocking |
| `POST /api/host/send-stream` | `{"content": "..."}` | Keyword-based routing, SSE |
| `POST /api/runs/stream` | `{"mode":"auto","message":"..."}` | Unified Host orchestration with versioned SSE |

---

## Project Structure

```
a2a-playground/
├── DESIGN.md                 # Chinese design document
├── README.md                 # This file
├── backend/
│   ├── main.py               # FastAPI app (30+ endpoints)
│   ├── models.py             # Pydantic models
│   ├── database.py           # JSON file persistence
│   ├── a2a_client.py         # A2A SDK wrapper
│   └── host/
│       ├── langgraph_agent.py    # LangGraph Host Agent
│       ├── langgraph_manager.py  # LangGraph event bridge
│       ├── agent.py              # ADK Host Agent
│       └── manager.py            # ADK event bridge
└── frontend/
    ├── src/
    │   ├── App.jsx            # Layout + routing
    │   ├── api/api.js         # JSON API client
    │   ├── api/runStream.js   # Versioned Run SSE client with replay/reconnect
    │   └── pages/
    │       ├── AgentsPage.jsx     # Agent management
    │       ├── ChatPage.jsx       # Single agent chat
    │       ├── EventsPage.jsx     # Event viewer
    │       └── MultiAgentPage.jsx # Host Agent multi-chat
    └── vite.config.js         # Dev proxy to :8050
```

---

## Configuration

### Environment Variables (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `HOST_LLM_API_KEY` | Yes | Host Agent OpenAI-compatible API key |
| `HOST_LLM_BASE_URL` | Yes | Host model endpoint, for example DeepSeek or a local vLLM `/v1` URL |
| `HOST_LLM_MODEL` | Yes | Host model name |
| `HOST_LLM_PROVIDER` | No | Display label such as `deepseek` or `vllm` |
| `AGENT_LLM_API_KEY` | Yes | K8s specialist Agents' independent API key |
| `AGENT_LLM_BASE_URL` | Yes | K8s specialist Agents' OpenAI-compatible endpoint |
| `AGENT_LLM_MODEL` | Yes | K8s specialist Agents' model name |
| `K8S_MCP_URL` | Yes | MCP endpoint; use `/mcp` for Streamable HTTP or `/sse` for legacy HTTP+SSE |
| `MCP_TRANSPORT` | No | `streamable_http` or `sse`; defaults to `sse` |
| `PLAYGROUND_API_KEY` | No | Bearer token required by `/api/*` except `/api/ping` when set |
| `PLAYGROUND_CORS_ORIGINS` | No | Comma-separated allowed frontend origins |
| `PLAYGROUND_ALLOW_PRIVATE_AGENTS` | No | Allow private/loopback Agent addresses for trusted local networks |
| `PLAYGROUND_DB_BUSY_TIMEOUT_MS` | No | SQLite lock wait, default `5000` ms |
| `HOST_MAX_TASKS` | No | Maximum Auto-mode plan nodes, default `6` |
| `HOST_MAX_CONCURRENCY` | No | Maximum parallel Agent delegations, default `3` |
| `HOST_MAX_ATTEMPTS` | No | Attempts per Agent before replacement, default `2` |

Host and K8s Agents are configured independently. Both accept OpenAI-compatible
endpoints. The legacy `DEEPSEEK_API_KEY` and `DEEPSEEK_BASE_URL` variables remain
supported as code-level fallbacks for existing non-Compose deployments.

### Auto-mode orchestration

Direct mode always delegates to the single Agent selected by the user. Auto
mode analyzes the request, creates a bounded dependency plan, runs independent
read-only tasks concurrently, passes source-labeled findings to dependent
tasks, evaluates results, and then synthesizes one answer. A transient or
insufficient result is retried once before Host tries one compatible
replacement Agent. Independent successful results are retained when another
branch fails.

Registered Agents do not call each other directly; Host owns context transfer
and scheduling. Any mutation remains paused behind the existing approval flow,
including mutations proposed after read-only diagnosis or security review.

#### Default configuration

| Setting | Value |
|---------|-------|
| Backend port | 8050 |
| Frontend port | 5173 |
| DeepSeek model | `deepseek-chat` |
| DeepSeek base URL | `https://api.deepseek.com/v1` |
| A2A SDK | `>=0.3.25` |
| Data storage | PostgreSQL (`DATABASE_URL`) |

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Agent registration fails | Agent not running | Start the agent first |
| "Insufficient Balance" | DeepSeek API key out of credits | Top up at platform.deepseek.com |
| Frontend shows no agents | Backend endpoint format | Refresh and check browser console |
| No streaming response | Agent doesn't support SSE | Falls back to blocking mode |
| Port in use | Previous instance still running | `lsof -ti:8050 \| xargs kill -9` |
| LangGraph errors | Missing dependencies | Check `langgraph`, `langchain-openai` installed |
| 404 on API calls | Backend not running | Start Backend on port 8050 |
| Multi-agent empty agents | Wrong API format | Fixed in latest version, refresh page |

---

## Related Projects

- [a2a-samples](https://github.com/GoogleCloudPlatform/a2a-samples) — Sample A2A agents
- [a2a-registry](https://github.com/GoogleCloudPlatform/a2a-registry) — A2A protocol registry
- [A2AServer](https://github.com/...) — Host Agent API (inspiration for multi-agent routing)
- [a2a-sdk](https://pypi.org/project/a2a-sdk/) — Python SDK for A2A protocol (>=0.3.25)
- [LangGraph](https://langchain-ai.github.io/langgraph/) — Agent orchestration framework
- [Google ADK](https://google.github.io/adk/) — Agent Development Kit
