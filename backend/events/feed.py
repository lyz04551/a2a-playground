from __future__ import annotations

import json
from typing import Any


def _payload(event: dict[str, Any]) -> dict[str, Any]:
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
        agent = agents_by_id.get(conversation.get("agent_id"), {})
        enriched = {
            **row,
            "conversation_title": conversation.get("title", "未命名会话"),
            "conversation_type": conversation_type,
            "source": (
                "multi-agent" if conversation_type == "multi"
                else "single-agent"
            ),
            "agent_id": payload.get("agent_id") or agent.get("id", ""),
            "agent_name": (
                payload.get("agent")
                or payload.get("agent_name")
                or agent.get("name")
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

