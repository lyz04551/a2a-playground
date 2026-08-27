"""LangGraph-based Host Agent using a2a-sdk v0.3+ for remote agent communication."""

import json
import logging
import os
import uuid
from typing import AsyncIterable, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import AgentCard, Message, TextPart, Role, Task

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


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
        config = ClientConfig(streaming=True)
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
            config = ClientConfig(streaming=False)
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

    def __init__(self):
        self.remote_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self._graph = None

    def register_agent_card(self, card: AgentCard):
        conn = RemoteAgentConnections(card)
        name = card.name or card.url
        self.remote_connections[name] = conn
        self.cards[name] = card
        self._graph = None

    def unregister_agent(self, agent_id: str):
        for name in list(self.remote_connections.keys()):
            if agent_id in name or agent_id in self.cards.get(name, AgentCard(name='', description='', url='', version='', default_input_modes=[], default_output_modes=[], capabilities={}, skills=[])).url:
                del self.remote_connections[name]
                del self.cards[name]
                self._graph = None
                return

    def _make_tools(self):
        cards = self.cards
        connections = self.remote_connections

        @tool
        def list_remote_agents() -> list[dict]:
            """List the available remote agents."""
            return [{"name": n, "description": (cards[n].description or ""), "url": cards[n].url} for n in cards]

        async def _send_task(agent_name: str, message: str) -> str:
            if agent_name not in connections:
                raise ValueError(f"Agent '{agent_name}' not found")
            result = await connections[agent_name].send_message(
                message, str(uuid.uuid4()), str(uuid.uuid4())
            )
            return result or "(no response)"

        @tool
        async def send_task(agent_name: str, message: str) -> str:
            """Send a task to a remote agent by name. Use the agent's full name from list_remote_agents."""
            return await _send_task(agent_name, message)

        return [list_remote_agents, send_task]

    def _build_agents_text(self) -> str:
        lines = []
        for name, card in self.cards.items():
            skills = card.skills or []
            skills_str = "; ".join(f"{s.name}: {s.description}" for s in skills if s.name) or "general"
            lines.append(json.dumps({"name": name, "description": card.description or "", "skills": skills_str}))
        return "\n".join(lines) if lines else "No agents available"

    def get_graph(self):
        if self._graph is not None:
            return self._graph

        model = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_base=DEEPSEEK_BASE_URL,
            temperature=0,
            streaming=True,
        )

        prompt = (
            "You are an expert delegator. Delegate user requests to the best remote agent.\n\n"
            "Tools:\n"
            "- `list_remote_agents` — list available agents\n"
            "- `send_task` — send a task to a specific agent by name\n\n"
            "IMPORTANT: After using send_task, briefly tell the user which agent handled their request "
            "and summarize the result. Do NOT repeat the full response from the agent verbatim. "
            "Just provide a short summary and let the user know the task was completed.\n\n"
            f"Available agents:\n{self._build_agents_text()}"
        )

        self._graph = create_react_agent(
            model,
            tools=self._make_tools(),
            prompt=prompt,
        )
        return self._graph
