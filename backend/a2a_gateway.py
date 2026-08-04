from __future__ import annotations

import uuid
import json
from typing import Any

from backend.a2a_client import send_message_to_agent


class SDKTransport:
    """Production transport using the project's a2a-sdk client wrapper."""

    async def send(
        self,
        *,
        agent: dict[str, Any],
        message: str,
        context_id: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        result = await send_message_to_agent(
            agent["url"],
            message,
            context_id,
            task_id=task_id,
        )
        return {
            **result,
            "context_id": context_id,
            "task_id": result.get("task_id") or task_id or "",
            "artifacts": result.get("artifacts", []),
        }


class A2AGateway:
    def __init__(self, repository, *, transport=None):
        self.repository = repository
        self.transport = transport or SDKTransport()

    async def delegate(
        self,
        run_id: str,
        agent: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        agent_id = agent["id"]
        binding = self.repository.get_remote_binding(run_id, agent_id)
        context_id = (
            binding["context_id"]
            if binding
            else f"ctx_{uuid.uuid4().hex}"
        )
        is_task_continuation = False
        try:
            payload = json.loads(message)
            is_task_continuation = (
                payload.get("type") == "approval_decision"
            )
        except (TypeError, json.JSONDecodeError):
            pass
        task_id = (
            binding["task_id"]
            if binding and is_task_continuation
            else None
        )
        result = await self.transport.send(
            agent=agent,
            message=message,
            context_id=context_id,
            task_id=task_id,
        )
        actual_task_id = result.get("task_id") or task_id or ""
        self.repository.upsert_remote_binding(
            run_id=run_id,
            agent_id=agent_id,
            context_id=result.get("context_id") or context_id,
            task_id=actual_task_id,
        )
        state = str(result.get("state", "")).replace("_", "-").lower()
        pending = (
            self._find_pending_action(result.get("artifacts", []))
            if state == "input-required"
            else None
        )
        approval = None
        if pending:
            approval = self.repository.get_approval(
                pending["approval_id"]
            )
            if approval is None:
                approval = self.repository.create_approval(
                    approval_id=pending["approval_id"],
                    run_id=run_id,
                    agent_id=agent_id,
                    tool_name=pending["tool_name"],
                    arguments=pending["arguments"],
                    action_digest=pending["action_digest"],
                )
            self.repository.update_run_status(
                run_id, "approval_required"
            )
        return {
            **result,
            "agent_id": agent_id,
            "context_id": result.get("context_id") or context_id,
            "task_id": actual_task_id,
            "approval": approval,
        }

    @staticmethod
    def _find_pending_action(artifacts: list[dict]) -> dict | None:
        for artifact in artifacts:
            if artifact.get("name") != "pending_action":
                continue
            for part in artifact.get("parts", []):
                root = part.get("root", part)
                text = root.get("text") if isinstance(root, dict) else None
                if not text:
                    continue
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        return None
