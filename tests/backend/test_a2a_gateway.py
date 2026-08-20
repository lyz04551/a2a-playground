from __future__ import annotations

import json

import pytest

from backend.a2a_gateway import A2AGateway
from backend.persistence.repository import SQLiteRepository


class FakeTransport:
    def __init__(self):
        self.calls = []

    async def send(self, *, agent, message, context_id, task_id):
        self.calls.append(
            {
                "agent": agent,
                "message": message,
                "context_id": context_id,
                "task_id": task_id,
            }
        )
        remote_task_id = task_id or f"remote-task-{len(self.calls)}"
        artifacts = []
        if '"type": "approval_decision"' in message:
            artifacts = [{
                "name": "pending_action",
                "parts": [{
                    "text": json.dumps({
                        "approval_id": "ap-1",
                        "agent_id": agent["id"],
                        "tool_name": "scale_k8s_deployment",
                        "arguments": {"name": "api", "replicas": 2},
                        "action_digest": "b" * 64,
                    }),
                }],
            }]
        return {
            "text": f"{agent['id']} handled {message}",
            "context_id": context_id,
            "task_id": remote_task_id,
            "state": "completed",
            "artifacts": artifacts,
        }


class StreamingTransport(FakeTransport):
    async def stream(self, *, agent, message, context_id, task_id):
        yield {
            "type": "tool_call",
            "id": "call-1",
            "tool": "get_secret",
            "args": {"namespace": "default", "authorization": "Bearer abc"},
            "task_id": "remote-1",
        }
        yield {
            "type": "tool_result",
            "id": "call-1",
            "result": {"password": "value", "count": 3},
            "task_id": "remote-1",
        }
        yield {
            "type": "done",
            "text": "finished",
            "state": "completed",
            "task_id": "remote-1",
            "artifacts": [{
                "name": "specialist_result",
                "parts": [{
                    "text": json.dumps({
                        "status": "completed",
                        "summary": "node is healthy",
                        "continuation": {"allowed": True},
                    }),
                }],
            }],
        }


@pytest.mark.anyio
async def test_gateway_reuses_remote_context_for_same_run_and_agent(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.create_run("run-1", "conv-1", "running")
    transport = FakeTransport()
    gateway = A2AGateway(repository, transport=transport)
    agent = {"id": "k8s-ops", "url": "http://ops"}

    first = await gateway.delegate("run-1", agent, "diagnose")
    second = await gateway.delegate("run-1", agent, "continue")

    assert first["context_id"] == second["context_id"]
    assert first["task_id"] != second["task_id"]
    assert len(transport.calls) == 2
    assert transport.calls[0]["task_id"] is None
    assert transport.calls[1]["task_id"] is None
    assert transport.calls[1]["context_id"] == first["context_id"]


@pytest.mark.anyio
async def test_gateway_uses_distinct_context_for_another_agent(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.create_run("run-1", "conv-1", "running")
    gateway = A2AGateway(repository, transport=FakeTransport())

    ops = await gateway.delegate(
        "run-1", {"id": "ops", "url": "http://ops"}, "diagnose"
    )
    security = await gateway.delegate(
        "run-1",
        {"id": "security", "url": "http://security"},
        "audit",
    )

    assert ops["context_id"] != security["context_id"]


@pytest.mark.anyio
async def test_approval_continuation_reuses_pending_task_id(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.create_run("run-1", "conv-1", "running")
    transport = FakeTransport()
    gateway = A2AGateway(repository, transport=transport)
    agent = {"id": "orchestrator", "url": "http://orchestrator"}

    pending = await gateway.delegate("run-1", agent, "prepare change")
    continued = await gateway.delegate(
        "run-1",
        agent,
        json.dumps({
            "type": "approval_decision",
            "approval_id": "ap-1",
            "decision": "approved",
        }),
    )

    assert continued["task_id"] == pending["task_id"]
    assert transport.calls[-1]["task_id"] == pending["task_id"]
    assert continued["approval"] is None


@pytest.mark.anyio
async def test_gateway_stream_redacts_public_tool_events_and_saves_binding(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.create_run("run-1", "conv-1", "running")
    gateway = A2AGateway(repository, transport=StreamingTransport())
    agent = {"id": "ops", "url": "http://ops"}

    events = [
        event async for event in gateway.delegate_stream(
            "run-1", agent, "diagnose"
        )
    ]

    assert events[0]["args"] == {
        "namespace": "default",
        "authorization": "[REDACTED]",
    }
    assert events[1]["result"] == {"password": "[REDACTED]", "count": 3}
    binding = repository.get_remote_binding("run-1", "ops")
    assert binding["task_id"] == "remote-1"
    assert events[-1]["specialist_output"] == {
        "status": "completed",
        "summary": "node is healthy",
        "continuation": {"allowed": True},
    }
