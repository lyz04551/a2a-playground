from __future__ import annotations

import json
from typing import Any


_LEGACY_EVENT_TYPES = {
    "run_started": "run.started",
    "started": "task.started",
    "completed": "task.completed",
    "routing": "task.delegated",
    "tool_call": "tool.called",
    "tool_result": "tool.completed",
    "status_update": "task.status_changed",
    "approval_required": "approval.required",
    "approval_decided": "approval.decided",
    "artifact": "artifact.created",
    "error": "task.failed",
    "done": "run.completed",
}


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    if isinstance(data, dict):
        return data
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    content = event.get("content")
    if isinstance(content, str) and content.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            pass
    return {}


def _state(event_type: str, current: str | None) -> str:
    if current:
        return current
    if event_type.endswith(".failed"):
        return "failed"
    if event_type.endswith(".cancelled"):
        return "canceled"
    if event_type in {"run.completed", "task.completed", "message.completed", "tool.completed"}:
        return "completed"
    if event_type.startswith("approval."):
        return "input-required"
    if event_type in {"run.started", "task.started", "host.planning", "host.synthesis_started", "message.delta"}:
        return "working"
    return "submitted"


def _content(event_type: str, row: dict[str, Any], payload: dict[str, Any]) -> str:
    if row.get("content"):
        return str(row["content"])
    for key in ("content", "result", "error", "reason", "summary"):
        if payload.get(key):
            return str(payload[key])
    defaults = {
        "run.started": "运行已开始",
        "run.completed": "本次运行已完成",
        "run.cancelled": "本次运行已取消",
        "host.planning": "Host 正在制定执行计划",
        "host.synthesis_started": "Host 正在综合各 Agent 结果",
        "task.delegated": "任务已分派给 Agent",
        "task.started": "任务开始执行",
        "task.completed": "任务执行完成",
        "task.blocked": "任务因依赖条件未满足而阻塞",
    }
    return defaults.get(event_type, "")


def build_event_feed(
    event_rows: list[dict[str, Any]],
    conversations: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    conversations_by_id = {item["id"]: item for item in conversations}
    agents_by_id = {item["id"]: item for item in agents}
    result = []

    for row in event_rows:
        conversation = conversations_by_id.get(row.get("conversation_id"))
        if conversation is None:
            continue
        conversation_type = conversation.get("type", "single")
        payload = _payload(row)
        raw_event_type = str(row.get("event_type") or row.get("type") or "")
        event_type = _LEGACY_EVENT_TYPES.get(raw_event_type, raw_event_type)
        event_agent_id = payload.get("agent_id") or row.get("agent_id") or ""
        agent = agents_by_id.get(event_agent_id) or agents_by_id.get(conversation.get("agent_id"), {})
        enriched = {
            **row,
            "id": row.get("id") or row.get("event_id"),
            "event_type": event_type,
            "state": _state(event_type, row.get("state")),
            "content": _content(event_type, row, payload),
            "conversation_title": conversation.get("title", "未命名会话"),
            "conversation_type": conversation_type,
            "source": (
                "multi-agent" if conversation_type == "multi"
                else "single-agent"
            ),
            "agent_id": event_agent_id or agent.get("id", ""),
            "agent_name": (
                payload.get("agent")
                or agent.get("name")
                or payload.get("agent_name")
                or ("Host Agent" if conversation_type == "multi" else "Unknown Agent")
            ),
            "payload": payload,
        }
        result.append(enriched)

    return sorted(
        result,
        key=lambda item: item.get("timestamp") or item.get("created_at") or "",
        reverse=True,
    )
