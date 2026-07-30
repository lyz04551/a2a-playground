"""LangGraph-based Host Agent using a2a-sdk v0.3+ for remote agent communication."""

import json
import logging
import os
import uuid
import asyncio
from contextvars import ContextVar
from typing import AsyncIterable, Optional

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import AgentCard, Message, TextPart, Role, Task

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
A2A_CLIENT_TIMEOUT = float(os.getenv("A2A_CLIENT_TIMEOUT", "120"))


# ── Text extraction helpers ──

def _get_text_from_part(p) -> str:
    if isinstance(p, Message):
        return "".join(_get_text_from_part(part) for part in p.parts)
    if hasattr(p, 'root'):
        inner = p.root
        if isinstance(inner, TextPart):
            return inner.text
    elif isinstance(p, TextPart):
        return p.text
    return ""


def _extract_text_from_task(task) -> str:
    parts = []
    if task.status and task.status.message and task.status.message.parts:
        parts.extend(task.status.message.parts)
    if task.artifacts:
        for artifact in task.artifacts:
            if artifact and artifact.parts:
                parts.extend(artifact.parts)
    return "".join(_get_text_from_part(p) for p in parts)


# ── Remote agent connection (a2a-sdk v0.3+) ──

class RemoteAgentConnections:
    """Wraps a remote A2A agent using the new a2a-sdk (v0.3+)."""

    def __init__(self, agent_card: AgentCard):
        self.card = agent_card
        self.httpx_client = httpx.AsyncClient(timeout=A2A_CLIENT_TIMEOUT)
        config = ClientConfig(streaming=True, httpx_client=self.httpx_client)
        factory = ClientFactory(config)
        self.client = factory.create(agent_card)

    async def send_message(self, text: str, session_id: str, task_id: str) -> str:
        """Send message and return ONLY the final accumulated text (no duplicates)."""
        sdk_msg = Message(
            message_id=task_id,
            role=Role.user,
            parts=[TextPart(text=text)],
            context_id=session_id,
        )
        accumulated = ""
        try:
            async for event in self.client.send_message(sdk_msg):
                chunk = ""
                if isinstance(event, Message):
                    chunk = _get_text_from_part(event)
                elif isinstance(event, tuple):
                    task, update = event
                    chunk = _extract_text_from_task(task)
                if chunk:
                    # A2A streaming: each event may contain the full accumulated text
                    # If the new chunk starts with our current accumulated text,
                    # it's a replacement (full state), not an append
                    if accumulated and chunk.startswith(accumulated):
                        # Only take the new part
                        accumulated = chunk
                    elif accumulated and chunk in accumulated:
                        # Chunk is already contained in accumulated, skip
                        pass
                    else:
                        accumulated += chunk
        except Exception as e:
            logger.warning(f"A2A send_message error: {e}")
            # Try non-streaming fallback
            try:
                await self.client.close()
            except:
                pass
            config = ClientConfig(streaming=False, httpx_client=self.httpx_client)
            factory = ClientFactory(config)
            self.client = factory.create(self.card)
            async for event in self.client.send_message(sdk_msg):
                chunk = ""
                if isinstance(event, Message):
                    chunk = _get_text_from_part(event)
                elif isinstance(event, tuple):
                    task, update = event
                    chunk = _extract_text_from_task(task)
                if chunk and chunk not in accumulated:
                    accumulated += chunk
        return accumulated


# ── LangGraph Host Agent ──

class LangGraphHostAgent:
    """LangGraph-based host agent that delegates to remote A2A agents."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.remote_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: dict[str, dict] = {}
        self._current_run: ContextVar[str] = ContextVar(
            "host_current_run", default=""
        )
        self._graph = None

    def register_agent_card(self, agent_id: str, card: AgentCard):
        existing = self.cards.get(agent_id)
        changed = existing is None or existing != card
        if self.gateway is None and changed:
            self.remote_connections[agent_id] = RemoteAgentConnections(card)
        self.cards[agent_id] = card
        self.agents[agent_id] = {
            "id": agent_id,
            "name": card.name or agent_id,
            "url": card.url,
        }
        if changed:
            self._graph = None

    def unregister_agent(self, agent_id: str):
        self.remote_connections.pop(agent_id, None)
        self.cards.pop(agent_id, None)
        self.agents.pop(agent_id, None)
        self._graph = None

    def set_current_run(self, run_id: str):
        return self._current_run.set(run_id)

    def reset_current_run(self, token) -> None:
        self._current_run.reset(token)

    def _make_tools(self):
        cards = self.cards
        connections = self.remote_connections
        agents = self.agents
        gateway = self.gateway

        @tool
        def list_remote_agents() -> list[dict]:
            """List the available remote agents."""
            return [
                {
                    "id": agent_id,
                    "name": cards[agent_id].name,
                    "description": cards[agent_id].description or "",
                    "url": cards[agent_id].url,
                }
                for agent_id in cards
            ]

        async def _send_task(agent_id: str, message: str) -> str:
            if agent_id not in cards:
                raise ValueError(f"Agent '{agent_id}' not found")
            if gateway is not None:
                run_id = self._current_run.get()
                if not run_id:
                    raise ValueError("No active orchestration run")
                response = await gateway.delegate(
                    run_id, agents[agent_id], message
                )
                if response.get("approval"):
                    return json.dumps(
                        {
                            "state": response.get("state"),
                            "text": response.get("text"),
                            "approval": response["approval"],
                        },
                        ensure_ascii=False,
                    )
                return response.get("text") or "(no response)"
            result = await connections[agent_id].send_message(
                message, str(uuid.uuid4()), str(uuid.uuid4())
            )
            return result or "(no response)"

        @tool
        async def send_task(agent_id: str, message: str) -> str:
            """Send a task through A2A using a stable agent ID from list_remote_agents."""
            return await _send_task(agent_id, message)

        return [list_remote_agents, send_task]

    def _build_agents_text(self) -> str:
        lines = []
        for agent_id, card in self.cards.items():
            skills = card.skills or []
            skills_str = "; ".join(f"{s.name}: {s.description}" for s in skills if s.name) or "general"
            lines.append(json.dumps({"id": agent_id, "name": card.name, "description": card.description or "", "skills": skills_str}))
        return "\n".join(lines) if lines else "No agents available"

    @staticmethod
    def _make_model(*, streaming: bool = True):
        return ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_base=DEEPSEEK_BASE_URL,
            temperature=0,
            streaming=streaming,
        )

    async def summarize_approval_result(
        self,
        approval: dict,
        execution_result: str,
    ) -> str:
        messages = [
            SystemMessage(content=(
                "你是 Host Agent。用户已经通过正式审批，子智能体也已经完成"
                " Kubernetes 写操作。请根据审批参数和 MCP 执行结果，用中文向"
                "用户给出简洁明确的执行总结。不要调用任何工具，不要再次请求"
                "审批，也不要声称尚未执行。"
            )),
            HumanMessage(content=json.dumps({
                "tool_name": approval.get("tool_name"),
                "arguments": approval.get("arguments", {}),
                "decision": approval.get("status"),
                "mcp_result": execution_result,
            }, ensure_ascii=False)),
        ]
        model = self._make_model(streaming=False)
        for attempt, delay in enumerate((0, 0.5, 1.5)):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await model.ainvoke(messages)
                return str(response.content or execution_result)
            except Exception as exc:
                is_busy = getattr(exc, "status_code", None) == 503
                if not is_busy or attempt == 2:
                    raise
        return execution_result

    def get_graph(self):
        if self._graph is not None:
            return self._graph

        model = self._make_model()

        prompt = (
            "You are an expert delegator. Delegate user requests to the best remote agent.\n\n"
            "Tools:\n"
            "- `list_remote_agents` — list available agents\n"
            "- `send_task` — send an A2A task using a stable agent ID\n\n"
            "IMPORTANT: After using send_task, briefly tell the user which agent handled their request "
            "and summarize the result. Do NOT repeat the full response from the agent verbatim. "
            "Just provide a short summary and let the user know the task was completed.\n\n"
            f"Available agents:\n{self._build_agents_text()}"
        )

        memory = MemorySaver()
        self._graph = create_react_agent(model, tools=self._make_tools(), prompt=prompt, checkpointer=memory)
        return self._graph
