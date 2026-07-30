from __future__ import annotations

import inspect
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import Any


def stream_step(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = event.get("type")
    if event_type == "text" and event.get("text"):
        return {"type": "text", "content": event["text"]}
    if event_type == "tool_call":
        return {
            "type": "tool_call",
            "id": event.get("id", ""),
            "tool": event.get("tool", ""),
            "args": event.get("args", {}),
            "content": event.get("text", ""),
        }
    if event_type == "tool_result":
        return {
            "type": "tool_result",
            "id": event.get("id", ""),
            "result": event.get("result", ""),
            "content": event.get("text", ""),
        }
    return None


async def _call(callback: Callable | None, value: dict[str, Any]) -> None:
    if callback is None:
        return
    result = callback(value)
    if inspect.isawaitable(result):
        await result


async def relay_agent_events(
    upstream: AsyncIterable[dict[str, Any]],
    *,
    persist_event: Callable | None = None,
    persist_completion: Callable | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Relay one A2A turn and durably finalize it before emitting done."""
    accumulated = ""
    task_id = ""
    upstream_done: dict[str, Any] | None = None

    async for event in upstream:
        if event.get("task_id"):
            task_id = event["task_id"]
        if event.get("type") == "done":
            upstream_done = event
            continue
        if event.get("type") == "text" and event.get("text"):
            accumulated += event["text"]
        await _call(persist_event, event)
        yield event

    final_text = (upstream_done or {}).get("text", "")
    if not accumulated and final_text:
        accumulated = final_text
        recovered = {
            "type": "text",
            "text": final_text,
            "state": "completed",
            "task_id": task_id,
        }
        await _call(persist_event, recovered)
        yield recovered

    result = {
        "type": "done",
        "task_id": task_id,
        "text": accumulated,
    }
    await _call(persist_completion, result)
    yield result
