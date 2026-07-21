import json
import logging
import uuid
from typing import AsyncIterable, Optional

import httpx
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import (
    AgentCard,
    Message,
    TextPart,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from a2a.utils.constants import PREV_AGENT_CARD_WELL_KNOWN_PATH

logger = logging.getLogger(__name__)


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


async def fetch_agent_card(agent_url: str) -> AgentCard:
    url = agent_url.strip().rstrip("/")
    if not url.startswith("http"):
        url = f"http://{url}"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resolver = A2ACardResolver(client, url)
            return await resolver.get_agent_card()
        except Exception as e:
            try:
                legacy_url = f"{url}{PREV_AGENT_CARD_WELL_KNOWN_PATH}"
                resp = await client.get(legacy_url)
                resp.raise_for_status()
                return AgentCard.model_validate(resp.json())
            except Exception as fallback_e:
                raise Exception(f"Cannot fetch agent card from {agent_url}: {e}; legacy fallback also failed: {fallback_e}")


def _make_sdk_message(text: str, conversation_id: str) -> Message:
    return Message(
        message_id=uuid.uuid4().hex,
        role=Role.user,
        parts=[TextPart(text=text)],
        context_id=conversation_id,
    )


# ────────── Legacy: tasks/send (for old A2A servers) ──────────

async def _send_tasks_send_legacy(agent_url: str, text: str, session_id: str) -> dict:
    """Send using the old 'tasks/send' method (A2AServer from A2AServer project)."""
    url = agent_url.strip().rstrip("/")
    if not url.startswith("http"):
        url = f"http://{url}"
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "tasks/send",
        "params": {
            "id": uuid.uuid4().hex,
            "sessionId": session_id,
            "message": {"role": "user", "parts": [{"type": "text", "text": text}]},
        },
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    result = data.get("result", {})
    # Extract text from result.history[-1] (agent message) or result.status.message
    history = result.get("history", [])
    text_content = ""
    if history:
        for msg in reversed(history):
            if msg.get("role") == "agent":
                for part in msg.get("parts", []):
                    if part.get("type") == "text":
                        text_content += part.get("text", "")
    if not text_content:
        status = result.get("status", {})
        status_msg = status.get("message", {})
        if status_msg:
            for part in status_msg.get("parts", []):
                if part.get("type") == "text":
                    text_content += part.get("text", "")
    return {"text": text_content, "state": result.get("status", {}).get("state", "unknown")}


async def _send_tasks_send_subscribe_legacy(agent_url: str, text: str, session_id: str) -> AsyncIterable[dict]:
    """Stream using old 'tasks/sendSubscribe' method. Yields text chunks."""
    url = agent_url.strip().rstrip("/")
    if not url.startswith("http"):
        url = f"http://{url}"
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "tasks/sendSubscribe",
        "params": {
            "id": uuid.uuid4().hex,
            "sessionId": session_id,
            "message": {"role": "user", "parts": [{"type": "text", "text": text}]},
        },
    }
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        evt = json.loads(line[6:])
                        result = evt.get("result", {})
                        if "status" in result:
                            status = result["status"]
                            msg = status.get("message", {})
                            for part in msg.get("parts", []):
                                if part.get("type") == "text":
                                    yield {"type": "text", "text": part.get("text", ""), "state": status.get("state", ""), "task_id": result.get("id", "")}
                            if result.get("final"):
                                yield {"type": "status", "state": status.get("state", ""), "final": True, "task_id": result.get("id", "")}
                        elif "artifact" in result:
                            artifact = result["artifact"]
                            for part in artifact.get("parts", []):
                                if part.get("type") == "text":
                                    yield {"type": "text", "text": part.get("text", ""), "task_id": result.get("id", "")}
                    except (json.JSONDecodeError, KeyError):
                        pass


# ────────── Main functions ──────────

async def send_message_to_agent(agent_url: str, text: str, conversation_id: str, agent_card: Optional[AgentCard] = None) -> dict:
    """Send message. Tries new SDK (message/send), then falls back to legacy (tasks/send)."""
    # Try new SDK path first
    try:
        if agent_card is None:
            agent_card = await fetch_agent_card(agent_url)
        config = ClientConfig(streaming=False, polling=False)
        factory = ClientFactory(config)
        client = factory.create(agent_card)
        sdk_msg = _make_sdk_message(text, conversation_id)
        accumulated = ""
        state = "unknown"
        async for event in client.send_message(sdk_msg):
            if isinstance(event, Message):
                accumulated += _get_text_from_part(event)
                state = "completed"
            elif isinstance(event, tuple):
                task, update = event
                if task and task.status:
                    state = task.status.state
                accumulated += _extract_text_from_task(task)
        await client.close()
        return {"text": accumulated, "state": state}
    except Exception as e:
        err = str(e)
        if "400" in err or "Method not found" in err or "Unexpected request" in err:
            logger.warning(f"New protocol failed ({err[:80]}), falling back to legacy tasks/send")
            return await _send_tasks_send_legacy(agent_url, text, conversation_id)
        logger.exception(f"send_message_to_agent failed: {err}")
        return {"text": "", "state": "failed"}


async def stream_message_to_agent(agent_url: str, text: str, conversation_id: str, agent_card: Optional[AgentCard] = None) -> AsyncIterable[dict]:
    """Stream message. Tries new SDK first, falls back to legacy tasks/sendSubscribe."""
    # Try new SDK path first
    try:
        if agent_card is None:
            agent_card = await fetch_agent_card(agent_url)
        config = ClientConfig(streaming=True)
        factory = ClientFactory(config)
        client = factory.create(agent_card)
        sdk_msg = _make_sdk_message(text, conversation_id)
        task_id = ""
        accumulated = ""
        try:
            async for event in client.send_message(sdk_msg):
                if isinstance(event, Message):
                    t = _get_text_from_part(event)
                    accumulated += t
                    yield {"type": "text", "text": t, "state": "completed", "task_id": task_id}
                    break
                elif isinstance(event, tuple):
                    task: Task = event[0]
                    update = event[1]
                    task_id = task.id
                    state = task.status.state if task.status else "unknown"
                    if isinstance(update, TaskStatusUpdateEvent):
                        msg = update.status.message
                        if msg:
                            for part in msg.parts:
                                t = _get_text_from_part(part)
                                if t:
                                    accumulated += t
                                    yield {"type": "text", "text": t, "state": state, "task_id": task_id}
                        artifact_text = _extract_text_from_task(task)
                        if artifact_text and artifact_text not in accumulated:
                            accumulated += "\n" + artifact_text
                            yield {"type": "text", "text": artifact_text, "state": state, "task_id": task_id}
                        yield {"type": "status", "state": state, "final": update.final, "task_id": task_id}
                    elif isinstance(update, TaskArtifactUpdateEvent):
                        for part in update.artifact.parts:
                            t = _get_text_from_part(part)
                            if t:
                                accumulated += t
                                yield {"type": "text", "text": t, "state": state, "task_id": task_id}
                    else:
                        artifact_text = _extract_text_from_task(task)
                        if artifact_text and artifact_text not in accumulated:
                            accumulated += artifact_text
                            yield {"type": "text", "text": artifact_text, "state": state, "task_id": task_id}
                        yield {"type": "status", "state": state, "task_id": task_id}
            yield {"type": "done", "task_id": task_id, "text": accumulated}
        except Exception as e:
            err = str(e)
            if "400" in err or "SSE" in err or "Content-Type" in err or "event-stream" in err or "Method not found" in err:
                logger.warning(f"Streaming not supported, falling back to legacy tasks/sendSubscribe: {err[:80]}")
                await client.close()
                async for chunk in _send_tasks_send_subscribe_legacy(agent_url, text, conversation_id):
                    if chunk.get("type") == "text":
                        accumulated += chunk.get("text", "")
                    yield chunk
                yield {"type": "done", "task_id": "", "text": accumulated}
                return
            logger.exception("Streaming error")
            yield {"type": "error", "text": err, "task_id": task_id}
        finally:
            await client.close()
    except Exception as e:
        logger.warning(f"SDK init failed ({str(e)[:80]}), trying legacy tasks/sendSubscribe")
        async for chunk in _send_tasks_send_subscribe_legacy(agent_url, text, conversation_id):
            yield chunk
        yield {"type": "done", "task_id": "", "text": ""}
