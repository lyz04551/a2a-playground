"""LangGraph Host Manager — bridges the LangGraph host agent with the playground backend."""

import logging
from typing import AsyncIterable, Optional

from backend.host.langgraph.agent import LangGraphHostAgent
from backend.host.langgraph.decisions import LangGraphDecisionPort
from backend.host.orchestration.engine import HostOrchestrationEngine
from backend.host.orchestration.models import DelegationResult
from a2a.types import AgentCard
from backend import database
from backend.a2a_gateway import A2AGateway
from backend.registry.service import AgentRegistry
from backend.settings import AppSettings

logger = logging.getLogger(__name__)


class LangGraphHostManager:
    """Manages the LangGraph HostAgent lifecycle and bridges to the playground backend."""

    def __init__(self, *, registry=None, gateway=None, decisions=None):
        settings = AppSettings.from_env()
        self._gateway = gateway or A2AGateway(database.repository)
        self._registry = registry or AgentRegistry(database.repository)
        self._host_agent = LangGraphHostAgent(gateway=self._gateway)
        self._decisions = decisions or LangGraphDecisionPort(
            self._host_agent._make_model(streaming=False)
        )
        self._engine = HostOrchestrationEngine(
            self._registry,
            self._decisions,
            self._delegate_task,
            max_concurrency=settings.host_max_concurrency,
            max_tasks=settings.host_max_tasks,
            max_attempts=settings.host_max_attempts,
            max_rounds=settings.host_max_rounds,
        )

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
            except Exception as e:
                logger.warning(f"Failed to register agent {a.get('name')}: {e}")

    async def summarize_approval_result(
        self,
        approval: dict,
        execution_result: str,
    ) -> str:
        return await self._host_agent.summarize_approval_result(
            approval,
            execution_result,
        )

    async def process_message_stream(self, text: str, session_id: str) -> AsyncIterable[dict]:
        """Process a user message and stream LangGraph events to the frontend.

        Yields dicts:
          - {"type": "tool_call", "tool": "...", "args": ..., "id": "..."}
          - {"type": "tool_result", "tool": "...", "result": ..., "id": "..."}
          - {"type": "routing", "agent": "..."}
          - {"type": "text", "text": "..."}
          - {"type": "done", "session_id": "..."}
        """
        async for event in self._engine.stream(text, session_id):
            yield event

    async def resume_message_stream(
        self,
        text: str,
        session_id: str,
        *,
        state=None,
        plan=None,
        results=None,
        successful=None,
    ) -> AsyncIterable[dict]:
        async for event in self._engine.stream(
            text,
            session_id,
            state=state,
            plan=plan,
            initial_results=results,
            initial_successful=successful,
        ):
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
        specialist_output = None
        async for event in self._gateway.delegate_stream(run_id, agent, message):
            event_type = str(event.get("type") or "")
            if event_type in {"tool_call", "tool_result", "status"}:
                await on_event(event)
            if event_type == "text":
                accumulated += str(event.get("text") or "")
                await on_event(event)
            elif event_type == "done":
                current_state = str(
                    response.get("state") or ""
                ).replace("_", "-").lower()
                if current_state not in {
                    "failed", "error", "rejected", "cancelled", "canceled",
                    "input-required",
                }:
                    response = event
                    response["text"] = str(
                        event.get("text") or accumulated
                    )
            elif event_type == "error":
                response = {"state": "failed", "error": event.get("text")}
            elif event_type == "approval_required":
                response = event
            elif not event_type:
                response = event
            if event.get("specialist_output") is not None:
                specialist_output = event["specialist_output"]
        state = str(response.get("state") or "").replace("_", "-").lower()
        if response.get("approval") or state == "input-required":
            return DelegationResult(
                state="approval_required",
                text=str(response.get("text") or ""),
                output=specialist_output,
                approval=response.get("approval"),
            )
        if state in {"failed", "error", "rejected", "cancelled", "canceled"}:
            return DelegationResult(
                state="failed",
                output=specialist_output,
                error=str(response.get("error") or response.get("text") or "remote execution failed"),
            )
        return DelegationResult(
            state="completed",
            text=str(response.get("text") or ""),
            output=specialist_output,
        )


_manager: Optional[LangGraphHostManager] = None


def get_manager() -> LangGraphHostManager:
    global _manager
    if _manager is None:
        _manager = LangGraphHostManager()
    return _manager
