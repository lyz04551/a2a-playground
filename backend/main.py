import json
import uuid
import logging
import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from backend.models import (
    Agent, AgentRegister, Conversation, Message, TaskEvent,
    SendMessageRequest, ApiResponse,
)
from backend import database as db
from backend.a2a_client import fetch_agent_card, send_message_to_agent, stream_message_to_agent, check_agent_health
from backend.events.feed import build_event_feed
from backend.events.single_agent import relay_agent_events, stream_step
from backend.settings import AppSettings, configure_http_security

logger = logging.getLogger(__name__)

app = FastAPI(title="A2A Playground API")
configure_http_security(app, AppSettings.from_env())


# ============================================================
# Health
# ============================================================

@app.post("/api/ping")
async def ping():
    return ApiResponse(result="Pong")


# ============================================================
# Agent Management
# ============================================================

@app.post("/api/agents/list")
async def agent_list():
    agents = db.list_agents()
    return ApiResponse(result=agents)


@app.post("/api/agents/fetch-card")
async def fetch_card(req: AgentRegister):
    try:
        card = await fetch_agent_card(req.agentAddress)
        return ApiResponse(result=card.model_dump(mode="json", by_alias=True))
    except Exception as e:
        return ApiResponse(success=False, error=str(e))


@app.post("/api/agents/register")
async def agent_register(req: AgentRegister):
    try:
        saved = await register_agent_address(req.agentAddress)
        return ApiResponse(result=saved)
    except Exception as e:
        return ApiResponse(success=False, error=str(e))


async def register_agent_address(
    address: str,
    *,
    stable_id: str | None = None,
    risk_level: str | None = None,
) -> dict:
    card = await fetch_agent_card(address)
    agent_url = address.strip()
    if not agent_url.startswith("http"):
        agent_url = f"http://{agent_url}"
    agent = Agent(
        id=stable_id or uuid.uuid4().hex[:12],
        name=card.name or "Unknown Agent",
        url=agent_url,
        description=card.description or "",
        provider=card.provider.model_dump() if card.provider else None,
        capabilities=card.capabilities.model_dump(mode="json") if card.capabilities else {},
        inputModes=card.default_input_modes or ["text"],
        outputModes=card.default_output_modes or ["text"],
        skills=[s.model_dump() for s in (card.skills or [])],
        version=card.version or "",
        protocolVersion=card.protocol_version or "",
        preferredTransport=card.preferred_transport or "",
        documentationUrl=card.documentation_url or "",
        read_only=risk_level != "write_approval",
        risk_level=risk_level or "read_only",
    ).model_dump()
    agent["health"] = {"online": True}
    return db.add_agent(agent)


@app.on_event("startup")
async def bootstrap_builtin_agents():
    raw = os.getenv("BOOTSTRAP_AGENTS", "[]")
    try:
        definitions = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("BOOTSTRAP_AGENTS is not valid JSON")
        return
    for definition in definitions:
        try:
            await register_agent_address(
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


@app.post("/api/agents/delete")
async def agent_delete(data: dict):
    agent_id = data.get("agentId", "")
    ok = db.delete_agent(agent_id)
    if not ok:
        return ApiResponse(success=False, error="Agent not found")
    return ApiResponse()


@app.post("/api/agents/get")
async def agent_get(data: dict):
    agent_id = data.get("agentId", "")
    agent = db.get_agent(agent_id)
    if not agent:
        return ApiResponse(success=False, error="Agent not found")
    return ApiResponse(result=agent)


@app.post("/api/agents/health-check")
async def agents_health_check():
    """Check health status of all registered agents concurrently."""
    agents = db.list_agents()
    if not agents:
        return ApiResponse(result=[])

    import asyncio
    tasks = [check_agent_health(a["url"]) for a in agents]
    results = await asyncio.gather(*tasks)

    health_map = {}
    for agent, health in zip(agents, results):
        health_map[agent["id"]] = health

    return ApiResponse(result=health_map)


# ============================================================
# Conversations
# ============================================================

@app.post("/api/conversation/create")
async def create_conversation(data: dict):
    agent_id = data.get("agentId", "")
    title = data.get("title", "New Chat")
    conv_type = data.get("type", "single")
    conv = Conversation(agent_id=agent_id, title=title, type=conv_type)
    saved = db.create_conversation(conv.model_dump())
    return ApiResponse(result=saved)


@app.post("/api/conversation/list")
async def list_conversations(data: dict):
    agent_id = data.get("agentId", "")
    conv_type = data.get("type", "")
    if agent_id:
        convs = db.list_conversations_by_agent(agent_id)
    else:
        convs = db.list_conversations()
    if conv_type:
        convs = [c for c in convs if c.get("type", "single") == conv_type]
    convs.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return ApiResponse(result=convs)


@app.post("/api/conversation/get")
async def get_conversation(data: dict):
    conv_id = data.get("conversationId", "")
    conv = db.get_conversation(conv_id)
    if not conv:
        return ApiResponse(success=False, error="Conversation not found")
    messages = db.list_messages(conv_id)
    messages.sort(key=lambda m: m.get("created_at", ""))
    conv["messages"] = messages
    return ApiResponse(result=conv)


@app.post("/api/conversation/update")
async def update_conversation(data: dict):
    conv_id = data.get("conversationId", "")
    title = data.get("title")
    updates = {}
    if title:
        updates["title"] = title
    updated = db.update_conversation(conv_id, updates)
    if not updated:
        return ApiResponse(success=False, error="Conversation not found")
    return ApiResponse(result=updated)


@app.post("/api/conversation/delete")
async def delete_conversation(data: dict):
    conv_id = data.get("conversationId", "")
    ok = db.delete_conversation(conv_id)
    if not ok:
        return ApiResponse(success=False, error="Conversation not found")
    return ApiResponse()


# ============================================================
# Messages
# ============================================================

@app.post("/api/message/list")
async def list_messages(data: dict):
    conversation_id = data.get("conversationId", "")
    messages = db.list_messages(conversation_id)
    return ApiResponse(result=messages)


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
# Events
# ============================================================

@app.post("/api/events/list")
async def events_list():
    return ApiResponse(result=build_event_feed(
        db.list_events(),
        db.list_conversations(),
        db.list_agents(),
    ))


@app.post("/api/events/query")
async def events_query(data: dict):
    conversation_id = data.get("conversationId", "")
    return ApiResponse(result=build_event_feed(
        db.get_events_for_conversation(conversation_id),
        db.list_conversations(),
        db.list_agents(),
    ))


# ============================================================
# Host Agent (simple keyword-based router)
# ============================================================

@app.post("/api/host/agents")
async def host_agents():
    agents = db.list_agents()
    return ApiResponse(result=agents)


async def select_best_agent(content: str, agents: list) -> Optional[dict]:
    """Simple keyword-based agent selection."""
    content_lower = content.lower()
    best = None
    best_score = 0
    for a in agents:
        score = 0
        name = a.get("name", "").lower()
        desc = a.get("description", "").lower()
        skills = a.get("skills", [])
        for kw in content_lower.split():
            if kw in name:
                score += 3
            if kw in desc:
                score += 2
            for s in skills:
                if kw in s.get("name", "").lower() or kw in s.get("description", "").lower():
                    score += 1
        if score > best_score:
            best_score = score
            best = a
    return best or (agents[0] if agents else None)


@app.post("/api/host/send")
async def host_send(data: dict):
    content = data.get("content", "")
    conversation_id = data.get("conversation_id", "")
    agents = db.list_agents()
    if not agents:
        return ApiResponse(success=False, error="No agents registered")

    selected = await select_best_agent(content, agents)
    if not selected:
        return ApiResponse(success=False, error="No suitable agent found")

    result = await send_message_to_agent(selected["url"], content, conversation_id or uuid.uuid4().hex)
    return ApiResponse(result={
        "response": result.get("text", ""),
        "state": result.get("state", "unknown"),
        "selected_agent": selected["name"],
        "selected_agent_id": selected["id"],
    })

@app.post("/api/host/send-stream")
async def host_send_stream(data: dict):
    content = data.get("content", "")
    conversation_id = data.get("conversation_id", "")
    agents = db.list_agents()
    if not agents:
        return ApiResponse(success=False, error="No agents registered")

    selected = await select_best_agent(content, agents)
    if not selected:
        return ApiResponse(success=False, error="No suitable agent found")

    async def event_stream():
        yield f"data: {json.dumps({'type': 'routing', 'agent': selected['name'], 'agent_id': selected['id']})}\n\n"
        async for chunk in stream_message_to_agent(selected["url"], content, conversation_id or uuid.uuid4().hex):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ============================================================
# ADK Host Agent — Multi-Agent with LLM Router (google.adk)

from backend.host.adk.manager import get_manager as get_adk_manager

@app.post("/api/host-adk/send")
async def host_adk_send(data: dict):
    content = data.get("content", "")
    session_id = data.get("session_id", uuid.uuid4().hex)
    agents = db.list_agents()
    if not agents:
        return ApiResponse(success=False, error="No agents registered")
    mgr = get_adk_manager()
    mgr.register_agents_from_db(agents)
    mgr.recreate_runner()

    async def event_stream():
        try:
            async for evt in mgr.process_message_stream(content, session_id):
                yield f"data: {json.dumps(evt)}\n\n"
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            logger.error(f"ADK host error: {err_msg}")
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

# ============================================================
# LangGraph Host Agent — Multi-Agent Router (Streaming)
# ============================================================

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

@app.post("/api/host-lg/send")
async def host_lg_send(data: dict):
    content = data.get("content", "")
    session_id = data.get("session_id", uuid.uuid4().hex)
    conv_id = data.get("conversation_id", "")
    agents = db.list_agents()
    if not agents:
        return ApiResponse(success=False, error="No agents registered")
    mgr = get_lg_manager()
    mgr.register_agents_from_db(agents)

    # Get or create conversation
    if not conv_id:
        c = Conversation(agent_id="multi-host", title="Multi-Agent Chat", type="multi")
        conv_id = db.create_conversation(c.model_dump())["id"]
    if db.repository.get_run(session_id) is None:
        db.repository.create_run(
            session_id, conv_id, "running",
            {"title": content[:80]},
        )

    # Save user message
    db.add_message(Message(
        conversation_id=conv_id,
        role="user",
        content=content,
        task_id=session_id,
        metadata={"source": "multi-agent"},
    ).model_dump())

    async def event_stream():
        accumulated = ""
        routing_agent = "Host Agent"
        tool_calls_data = []
        tool_results_data = {}
        try:
            async for evt in mgr.process_message_stream(content, session_id):
                if evt["type"] == "text" and evt.get("text"):
                    accumulated += evt["text"]
                if evt["type"] == "routing" and evt.get("agent"):
                    routing_agent = evt["agent"]
                if evt["type"] == "tool_call":
                    tool_calls_data.append({
                        "tool": evt.get("tool", ""),
                        "args": evt.get("args", {}),
                        "id": evt.get("id", ""),
                    })
                if evt["type"] == "tool_result":
                    tool_results_data[evt.get("id", "")] = evt.get("result", "")
                # Save tool events to DB
                if evt["type"] in ("tool_call", "tool_result", "routing"):
                    db.add_event(TaskEvent(
                        conversation_id=conv_id, task_id=session_id,
                        event_type=evt["type"], state="completed",
                        content=json.dumps({
                            "tool": evt.get("tool", ""),
                            "args": evt.get("args"),
                            "result": evt.get("result"),
                            "agent": evt.get("agent", ""),
                        }, ensure_ascii=False),
                    ).model_dump())
                yield f"data: {json.dumps(evt)}\n\n"

            # Save agent message with full metadata
            if accumulated:
                db.add_message(Message(
                    conversation_id=conv_id,
                    role="agent",
                    content=accumulated,
                    task_id=session_id,
                    metadata={
                        "routing_agent": routing_agent,
                        "tool_calls": tool_calls_data,
                        "tool_results": tool_results_data,
                        "source": "multi-agent",
                    },
                ).model_dump())

            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'conversation_id': conv_id})}\n\n"
        except Exception as e:
            import traceback
            logger.error(f"LangGraph error: {traceback.format_exc()}")
            # Save error message
            db.add_message(Message(
                conversation_id=conv_id,
                role="agent",
                content=f"Error: {str(e)}",
                task_id=session_id,
                metadata={"source": "multi-agent", "error": True},
            ).model_dump())
            yield f"data: {json.dumps({'type': 'error', 'text': str(e), 'conversation_id': conv_id})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
