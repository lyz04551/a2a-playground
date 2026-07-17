# A2A Playground

A full-stack web application for managing and chatting with A2A (Agent-to-Agent) protocol agents. Built with **FastAPI** backend and **React + Ant Design** frontend. Features **Host Agent** multi-agent routing powered by LangGraph / LLM.

---

## Architecture

```
┌──────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────┐
│   React + Ant Design     │ SSE  │   FastAPI Backend        │ A2A  │   Remote Agent   │
│   (Vite 5)               │<────>│   (Python / uvicorn)     │<────>│   (A2A Protocol) │
│                          │ HTTP │                          │JSON  │                  │
│   Port 5174              │      │   Port 8050              │ RPC  │   Ports vary     │
└──────────────────────────┘      └──────────────────────────┘      └──────────────────┘
                                         │
                                         v
                                 ┌──────────────────┐     ┌─────────────────────┐
                                 │  JSON File DB     │     │  Host Agent         │
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
| **Persistent History** | Conversations, messages, and events saved to JSON files |
| **Task Events** | Full event log with tool_call, tool_result, routing events |
| **Pagination** | Agent cards paginated (9 per page) |

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

### 2. Start the Playground

```bash
cd a2a-playground

# Configure DeepSeek API key
echo 'DEEPSEEK_API_KEY="sk-your-key-here"' > backend/.env

# Run everything
bash run.sh
```

### 3. Open the UI

Open [http://127.0.0.1:5174](http://127.0.0.1:5174) in your browser.

### Manual Setup

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn httpx pydantic python-dotenv a2a-sdk>=0.3.25 langgraph langchain-openai langchain-core
.venv/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8050 --log-level info

# Frontend
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5174
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
| `POST /api/host-adk/send` | `{"content": "..."}` | Google ADK routing, SSE |
| `POST /api/host-lg/send` | `{"content": "..."}` | **LangGraph routing, SSE (recommended)** |

---

## Project Structure

```
a2a-playground/
├── run.sh                    # One-click startup
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
    │   ├── api/api.js         # API client (HTTP + SSE)
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
| `DEEPSEEK_API_KEY` | Yes | API key for Host Agent route decisions |

#### Default configuration

| Setting | Value |
|---------|-------|
| Backend port | 8050 |
| Frontend port | 5174 |
| DeepSeek model | `deepseek-chat` |
| DeepSeek base URL | `https://api.deepseek.com/v1` |
| A2A SDK | `>=0.3.25` |
| Data storage | JSON files in `backend/data/` |

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
| 404 on API calls | Backend not running | Run `bash run.sh` or start manually |
| Multi-agent empty agents | Wrong API format | Fixed in latest version, refresh page |

---

## Related Projects

- [a2a-samples](https://github.com/GoogleCloudPlatform/a2a-samples) — Sample A2A agents
- [a2a-registry](https://github.com/GoogleCloudPlatform/a2a-registry) — A2A protocol registry
- [A2AServer](https://github.com/...) — Host Agent API (inspiration for multi-agent routing)
- [a2a-sdk](https://pypi.org/project/a2a-sdk/) — Python SDK for A2A protocol (>=0.3.25)
- [LangGraph](https://langchain-ai.github.io/langgraph/) — Agent orchestration framework
- [Google ADK](https://google.github.io/adk/) — Agent Development Kit
