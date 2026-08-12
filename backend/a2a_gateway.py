from __future__ import annotations

import uuid
import json
from collections.abc import AsyncIterator
from typing import Any

from backend.a2a_client import send_message_to_agent, stream_message_to_agent


_SENSITIVE_KEYS = {
    "authorization", "cookie", "kubeconfig", "password", "private_key",
    "secret", "token", "api_key", "apikey", "access_token", "refresh_token",
}


def _public_value(value: Any, *, max_text: int = 20_000) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS
            else _public_value(item, max_text=max_text)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_public_value(item, max_text=max_text) for item in value]
    if isinstance(value, tuple):
        return [_public_value(item, max_text=max_text) for item in value]
    if isinstance(value, str) and len(value) > max_text:
        return f"{value[:max_text]}\n… [truncated {len(value) - max_text} characters]"
    return value


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

    async def stream(
        self,
        *,
        agent: dict[str, Any],
        message: str,
        context_id: str,
        task_id: str | None,
    ) -> AsyncIterator[dict[str, Any]]:
        # A new streamed request starts a new remote task. Approval continuation
        # remains on the blocking path until the SDK supports task-id streaming.
        async for event in stream_message_to_agent(
            agent["url"], message, context_id
        ):
            yield event


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

    async def delegate_stream(
        self,
        run_id: str,
        agent: dict[str, Any],
        message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Expose only public remote execution events, with blocking fallback."""
        agent_id = agent["id"]
        binding = self.repository.get_remote_binding(run_id, agent_id)
        context_id = binding["context_id"] if binding else f"ctx_{uuid.uuid4().hex}"
        remote_task_id = ""

        stream = getattr(self.transport, "stream", None)
        if stream is None:
            yield await self.delegate(run_id, agent, message)
            return

        async for upstream in stream(
            agent=agent,
            message=message,
            context_id=context_id,
            task_id=None,
        ):
            event = dict(upstream)
            if event.get("task_id"):
                remote_task_id = str(event["task_id"])
                self.repository.upsert_remote_binding(
                    run_id=run_id,
                    agent_id=agent_id,
                    context_id=context_id,
                    task_id=remote_task_id,
                )
            if event.get("type") == "tool_call":
                event["args"] = _public_value(event.get("args", {}))
            elif event.get("type") == "tool_result":
                event["result"] = _public_value(event.get("result", ""))
            event["agent_id"] = agent_id
            event["context_id"] = context_id
            if remote_task_id:
                event["task_id"] = remote_task_id
            yield event

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
