import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from backend.models import Conversation, Message, TaskEvent, ApiResponse
from backend import database as db
from backend.a2a_client import fetch_agent_card, send_message_to_agent, stream_message_to_agent, check_agent_health
from backend.events.feed import build_event_feed  # Backward-compatible import.
from backend.events.single_agent import relay_agent_events, stream_step
from backend.api.agents import AgentService, create_router as create_agents_router
from backend.api.conversations import create_router as create_conversations_router
from backend.settings import AppSettings, configure_http_security

logger = logging.getLogger(__name__)

app = FastAPI(title="A2A Playground API")
configure_http_security(app, AppSettings.from_env())
agent_service = AgentService(db, fetch_agent_card)
app.include_router(create_agents_router(db, agent_service, check_agent_health))
app.include_router(create_conversations_router(db))


# ============================================================
# Health
# ============================================================

@app.post("/api/ping")
async def ping():
    return ApiResponse(result="Pong")


@app.on_event("startup")
async def bootstrap_builtin_agents():
    recovered = run_service.recover_interrupted_runs()
    if recovered:
        logger.warning("Marked %s unfinished Runs as interrupted after restart", recovered)
    raw = os.getenv("BOOTSTRAP_AGENTS", "[]")
    try:
        definitions = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("BOOTSTRAP_AGENTS is not valid JSON")
        return
    for definition in definitions:
        try:
            await agent_service.register(
                definition["url"],
                stable_id=definition["id"],
                risk_level=definition.get("risk_level"),
            )
        except Exception as exc:
            logger.warning(
                "Unable to bootstrap agent %s: %s",
                definition.get("id"),
                exc,
            )

# ============================================================
# Messages
# ============================================================


@app.post("/api/message/send")
async def message_send(data: dict):
    conversation_id = data.get("conversation_id", "")
    content = data.get("content", "")
    if not conversation_id or not content:
        return ApiResponse(success=False, error="Missing conversation_id or content")

    conv = db.get_conversation(conversation_id)
    if not conv:
        return ApiResponse(success=False, error="Conversation not found")

    # Save user message
    user_msg = Message(conversation_id=conversation_id, role="user", content=content)
    db.add_message(user_msg.model_dump())

    # Find agent and send
    agent = db.get_agent(conv.get("agent_id", ""))
    if not agent:
        return ApiResponse(success=False, error="Agent not found")

    try:
        result = await send_message_to_agent(agent["url"], content, conversation_id)
        agent_msg = Message(
            conversation_id=conversation_id,
            role="agent",
            content=result.get("text", ""),
            task_id=result.get("task_id", ""),
        )
        db.add_message(agent_msg.model_dump())

        # Save event
        db.add_event(TaskEvent(
            conversation_id=conversation_id,
            task_id=result.get("task_id", ""),
            event_type="status_update",
            state=result.get("state", "completed"),
            content=result.get("text", "")[:200],
        ).model_dump())

        return ApiResponse(result=agent_msg.model_dump())
    except Exception as e:
        logger.exception("message_send error")
        return ApiResponse(success=False, error=str(e))


@app.post("/api/message/send-stream")
async def message_send_stream(data: dict):
    conversation_id = data.get("conversation_id", "")
    content = data.get("content", "")
    if not conversation_id or not content:
        return ApiResponse(success=False, error="Missing conversation_id or content")

    conv = db.get_conversation(conversation_id)
    if not conv:
        return ApiResponse(success=False, error="Conversation not found")

    agent = db.get_agent(conv.get("agent_id", ""))
    if not agent:
        return ApiResponse(success=False, error="Agent not found")

    # Save user message
    user_msg = Message(conversation_id=conversation_id, role="user", content=content)
    db.add_message(user_msg.model_dump())

    async def event_stream():
        steps = []
        # Save started event
        db.add_event(TaskEvent(
            conversation_id=conversation_id,
            task_id="",
            event_type="started",
            state="running",
            content=f"Agent processing: {content[:100]}",
        ).model_dump())

        async def persist_event(chunk: dict):
            step = stream_step(chunk)
            if step:
                steps.append(step)
            if chunk.get("type") not in ("tool_call", "tool_result"):
                return
            db.add_event(TaskEvent(
                conversation_id=conversation_id,
                task_id=chunk.get("task_id", ""),
                event_type=chunk["type"],
                state=chunk.get("state", "working"),
                content=json.dumps(step, ensure_ascii=False),
                metadata=step,
            ).model_dump())

        async def persist_completion(result: dict):
            task_id = result.get("task_id", "")
            accumulated = result.get("text", "")
            db.add_event(TaskEvent(
                conversation_id=conversation_id,
                task_id=task_id,
                event_type="completed",
                state="completed",
                content=accumulated[:200] if accumulated else "No response",
            ).model_dump())
            if accumulated:
                db.add_message(Message(
                    conversation_id=conversation_id,
                    role="agent",
                    content=accumulated,
                    task_id=task_id,
                    metadata={"steps": steps},
                ).model_dump())

        upstream = stream_message_to_agent(
            agent["url"], content, conversation_id
        )
        async for chunk in relay_agent_events(
            upstream,
            persist_event=persist_event,
            persist_completion=persist_completion,
        ):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ============================================================
# Host Agent (simple keyword-based router)
# ============================================================

@app.post("/api/host/agents")
async def host_agents():
    agents = db.list_agents()
    return ApiResponse(result=agents)


@app.post("/api/host/send")
@app.post("/api/host/send-stream")
async def deprecated_host_send():
    raise HTTPException(
        status_code=410,
        detail="Legacy Host routing was removed; use /api/runs/stream with mode=auto",
    )


from backend.host.langgraph.manager import get_manager as get_lg_manager
from backend.a2a_gateway import A2AGateway
from backend.registry.service import AgentRegistry
from backend.orchestration.service import RunService
from backend.api.runs import create_approval_router, create_router as create_runs_router

run_gateway = A2AGateway(db.repository)
run_host = get_lg_manager()
run_service = RunService(
    db.repository,
    AgentRegistry(db.repository),
    run_gateway,
    run_host,
)
app.include_router(create_runs_router(run_service))
app.include_router(
    create_approval_router(
        run_service,
        run_gateway,
        run_host,
        logger=logger,
    )
)
