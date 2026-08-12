"""ADK Host Manager — streams tool calls and intermediate results to the frontend."""

import json
import logging
import os
import uuid
from typing import AsyncIterable, Optional

from google.adk import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.artifacts import InMemoryArtifactService
from google.genai import types

from backend.host.adk.agent import HostAgent
from backend.host.adk.decisions import ADKDecisionPort
from backend.host.langgraph.agent import LangGraphHostAgent
from backend.host.orchestration.engine import HostOrchestrationEngine
from backend.host.orchestration.models import DelegationResult
from backend.a2a_gateway import A2AGateway
from backend.registry.service import AgentRegistry
from backend import database
from backend.settings import AppSettings
from a2a.types import AgentCard

logger = logging.getLogger(__name__)


class ADKHostManager:
    """Manages the ADK HostAgent and streams events to the frontend."""

    def __init__(self, *, registry=None, gateway=None, decisions=None):
        settings = AppSettings.from_env()
        self._host_agent = HostAgent()
        self._registry = registry or AgentRegistry(database.repository)
        self._gateway = gateway or A2AGateway(database.repository)
        self._decisions = decisions or ADKDecisionPort(
            LangGraphHostAgent._make_model(streaming=False)
        )
        self._engine = HostOrchestrationEngine(
            self._registry,
            self._decisions,
            self._delegate_task,
            max_concurrency=settings.host_max_concurrency,
            max_tasks=settings.host_max_tasks,
            max_attempts=settings.host_max_attempts,
        )
        self._session_service = InMemorySessionService()
        self._memory_service = InMemoryMemoryService()
        self._artifact_service = InMemoryArtifactService()
        self._runner: Optional[Runner] = None
        self.user_id = "playground_user"
        self.app_name = "a2a_playground"

    def register_agents_from_db(self, agents: list[dict]):
        for a in agents:
            try:
                card = AgentCard(
                    name=a.get("name", "Unknown"),
                    description=a.get("description", ""),
                    url=a.get("url", ""),
                    version=a.get("version", "1.0"),
                    default_input_modes=a.get("inputModes", ["text"]),
                    default_output_modes=a.get("outputModes", ["text"]),
                    capabilities={"streaming": True} if a.get("capabilities", {}).get("streaming") else {},
                    skills=a.get("skills", []),
                    preferred_transport=a.get("preferredTransport", "JSONRPC"),
                )
                self._host_agent.register_agent_card(a["id"], card)
                logger.info(f"Registered ADK sub-agent: {card.name}")
            except Exception as e:
                logger.warning(f"Failed to register agent {a.get('name')}: {e}")

    def unregister_agent(self, agent_id: str):
        self._host_agent.unregister_agent(agent_id)

    def ensure_runner(self) -> Runner:
        if self._runner is None:
            agent = self._host_agent.create_agent()
            self._runner = Runner(
                app_name=self.app_name,
                agent=agent,
                artifact_service=self._artifact_service,
                session_service=self._session_service,
                memory_service=self._memory_service,
            )
        return self._runner

    def recreate_runner(self):
        self._runner = None

    async def process_message_stream(
        self, text: str, session_id: str
    ) -> AsyncIterable[dict]:
        async for event in self._engine.stream(text, session_id):
            yield event

    async def _delegate_task(
        self, run_id: str, agent_id: str, message: str, on_event
    ) -> DelegationResult:
        agent = self._registry.get(agent_id)
        if agent is None:
            return DelegationResult(
                state="failed", error=f"Agent '{agent_id}' not found"
            )
        response = {"state": "completed", "text": ""}
        accumulated = ""
        async for event in self._gateway.delegate_stream(run_id, agent, message):
            event_type = str(event.get("type") or "")
            if event_type in {"tool_call", "tool_result", "status"}:
                await on_event(event)
            if event_type == "text":
                accumulated += str(event.get("text") or "")
            elif event_type == "done":
                response = event
                response["text"] = str(event.get("text") or accumulated)
            elif event_type == "error":
                response = {"state": "failed", "error": event.get("text")}
            elif not event_type:
                response = event
        state = str(response.get("state") or "").replace("_", "-").lower()
        if response.get("approval") or state == "input-required":
            return DelegationResult(
                state="approval_required",
                text=str(response.get("text") or ""),
                approval=response.get("approval"),
            )
        if state in {"failed", "error", "rejected", "cancelled", "canceled"}:
            return DelegationResult(
                state="failed",
                error=str(
                    response.get("error")
                    or response.get("text")
                    or "remote execution failed"
                ),
            )
        return DelegationResult(
            state="completed", text=str(response.get("text") or "")
        )

    async def _process_legacy_message_stream(self, text: str, session_id: str) -> AsyncIterable[dict]:
        """Process a user message and stream ADK events to the frontend.

        Yields dicts:
          - {"type": "routing", "agent": "..."}
          - {"type": "tool_call", "tool": "...", "args": ...}
          - {"type": "tool_result", "tool": "...", "result": ...}
          - {"type": "text", "text": "..."}
          - {"type": "done"}
        """
        runner = self.ensure_runner()

        session = await self._session_service.get_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id,
        )
        if not session:
            session = await self._session_service.create_session(
                app_name=self.app_name, user_id=self.user_id, session_id=session_id,
            )

        tool_agent_map = {}
        async for event in runner.run_async(
            user_id=self.user_id,
            session_id=session_id,
            new_message=types.Content(
                parts=[types.Part.from_text(text=text)],
                role="user",
            ),
        ):
            # Function calls (tool invocations)
            fcs = event.get_function_calls()
            if fcs:
                for fc in fcs:
                    # Track agent name for send_task
                    if fc.name == "send_task" and fc.args:
                        an = getattr(fc.args, "get", None)
                        if an:
                            agent_name = an("agent_name", "")
                            if agent_name:
                                tool_agent_map[fc.id] = agent_name
                    yield {
                        "type": "tool_call",
                        "tool": fc.name,
                        "args": self._simplify(fc.args) if fc.args else {},
                        "id": fc.id,
                    }

            # Function responses (tool results)
            frs = event.get_function_responses()
            if frs:
                for fr in frs:
                    result = self._simplify(fr.response)
                    yield {"type": "tool_result", "tool": fr.name, "result": result, "id": fr.id}
                    # For send_task results, yield the agent's response as text with the agent name
                    if fr.name == "send_task":
                        # Result can be str or dict {"result": "..."} from ADK
                        text = ""
                        if isinstance(result, str):
                            text = result
                        elif isinstance(result, dict):
                            text = result.get("result") or result.get("text") or ""
                        if len(text) > 20:
                            agent_name = tool_agent_map.pop(fr.id, "Agent")
                            yield {"type": "routing", "agent": agent_name}
                            yield {"type": "text", "text": text}

            # Model text responses
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and event.author != "user":
                        # Show which agent is responding (routing info)
                        if event.author != "host_agent":
                            yield {"type": "routing", "agent": event.author}
                        yield {"type": "text", "text": part.text}

        yield {"type": "done", "session_id": session_id}

    def _simplify(self, obj):
        """Convert complex types to JSON-serializable dicts."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "__dict__"):
            return {k: self._simplify(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
        if isinstance(obj, dict):
            return {k: self._simplify(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._simplify(v) for v in obj]
        return obj


_manager: Optional[ADKHostManager] = None

def get_manager() -> ADKHostManager:
    global _manager
    if _manager is None:
        _manager = ADKHostManager()
    return _manager
