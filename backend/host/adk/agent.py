"""ADK-based Host Agent using a2a-sdk v0.3+ for remote agent communication."""

import json
import uuid
import os
from typing import Optional

from a2a.types import (
    AgentCard, Message, TextPart, Role, Task, TaskState,
    TaskArtifactUpdateEvent, TaskStatusUpdateEvent,
)

from a2a.client.client import ClientConfig, ClientEvent
from a2a.client.client_factory import ClientFactory

from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from google.adk.models.lite_llm import LiteLlm


# ── Text extraction helpers (same as a2a_client.py) ──

def _get_text_from_part(p) -> str:
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


# ── Remote agent connection using a2a-sdk v0.3+ ──

class RemoteAgentConnections:
    """Wraps a remote A2A agent using the new a2a-sdk (v0.3+)."""

    def __init__(self, agent_card: AgentCard):
        self.card = agent_card
        # Create a client factory; streaming=True means the SDK will try message/stream first
        config = ClientConfig(streaming=True)
        factory = ClientFactory(config)
        self.client = factory.create(agent_card)

    async def send_message(self, text: str, session_id: str, task_id: str) -> str:
        """Send a message to the remote agent and return the accumulated text response."""
        sdk_msg = Message(
            message_id=task_id,
            role=Role.user,
            parts=[TextPart(text=text)],
            context_id=session_id,
        )
        accumulated = ""
        async for event in self.client.send_message(sdk_msg):
            if isinstance(event, Message):
                accumulated += _get_text_from_part(event)
            elif isinstance(event, tuple):
                task, update = event
                accumulated += _extract_text_from_task(task)
        return accumulated


# ── The Host Agent (ADK) ──

class HostAgent:
    """ADK-based host agent that delegates to remote A2A agents."""

    _deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")

    def __init__(self):
        self.remote_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}

    def register_agent_card(self, agent_id: str, card: AgentCard):
        """Register a remote agent by its AgentCard."""
        conn = RemoteAgentConnections(card)
        self.remote_connections[agent_id] = conn
        self.cards[agent_id] = card

    def unregister_agent(self, agent_id: str):
        """Remove a registered agent by ID."""
        self.remote_connections.pop(agent_id, None)
        self.cards.pop(agent_id, None)

    def _get_agents_text(self) -> str:
        """Build the agents description text for the system prompt."""
        lines = []
        for agent_id, card in self.cards.items():
            skills = card.skills or []
            skills_str = "; ".join(
                f"{s.name}: {s.description}" for s in skills if s.name
            ) or "general"
            lines.append(json.dumps({
                "id": agent_id,
                "name": card.name or agent_id,
                "description": card.description or "",
                "skills": skills_str,
                "url": card.url,
            }))
        return "\n".join(lines) if lines else "No agents available"

    def _root_instruction(self, context: ReadonlyContext) -> str:
        """System prompt for the ADK agent."""
        agents_text = self._get_agents_text()
        return (
            "You are an expert delegator. Delegate user requests to the best remote agent.\n\n"
            "Tools:\n"
            "- `list_remote_agents` — list available agents\n"
            "- `send_task` — send a task to a specific agent by name\n\n"
            "Use the tools to address the request. Do not make up responses.\n"
            "If you're not sure which agent to use, ask the user.\n\n"
            f"Available agents:\n{agents_text}"
        )

    def _before_model_callback(self, callback_context: CallbackContext, llm_request):
        """Initialize session state before the LLM is called."""
        state = callback_context.state
        if 'session_active' not in state or not state['session_active']:
            if 'session_id' not in state:
                state['session_id'] = str(uuid.uuid4())
            state['session_active'] = True

    # ── Tools ──

    def list_remote_agents(self, tool_context: ToolContext):
        """List the available remote agents."""
        result = []
        for agent_id, card in self.cards.items():
            result.append({
                "id": agent_id,
                "name": card.name or agent_id,
                "description": card.description or "",
                "url": card.url,
            })
        return result

    async def send_task(self, agent_id: str, message: str, tool_context: ToolContext):
        """Send a task to a remote agent by name.

        Args:
            agent_id: The stable ID of the agent to delegate to.
            message: The message/query to send.
        """
        if agent_id not in self.remote_connections:
            raise ValueError(f"Agent '{agent_id}' not found")

        state = tool_context.state
        if 'session_id' not in state:
            state['session_id'] = str(uuid.uuid4())

        state['agent'] = agent_id
        task_id = state.get('task_id') or str(uuid.uuid4())
        state['task_id'] = task_id

        conn = self.remote_connections[agent_id]
        response_text = await conn.send_message(message, state['session_id'], task_id)

        # Mark session as no longer active unless agent says otherwise
        state['session_active'] = False

        return response_text or "(no response)"

    # ── Create ADK Agent ──

    def create_agent(self) -> Agent:
        return Agent(
            model=LiteLlm(model="deepseek/deepseek-chat", api_key=self._deepseek_api_key),
            name="host_agent",
            instruction=self._root_instruction,
            before_model_callback=self._before_model_callback,
            tools=[self.list_remote_agents, self.send_task],
        )
