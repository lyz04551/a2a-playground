from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI

from backend.orchestration.commands import RunCommand
from backend.orchestration.service import RunService
from tests.postgres_helpers import create_test_repository
from backend.registry.service import AgentRegistry
from backend.api.runs import (
    _schedule_auto_approval_execution,
    _schedule_auto_resume,
    create_approval_router,
)


class FakeGateway:
    def delegate(self, run_id, agent, message):
        async def stream():
            yield {"type": "done", "text": "Ready"}

        return stream()


class UnusedAutoHost:
    async def process_message_stream(self, text, session_id):
        raise AssertionError("unexpected Auto execution")
        yield


@pytest.mark.anyio
async def test_auto_approval_resume_runs_in_background_after_marking_run_active():
    gate = asyncio.Event()

    class Repository:
        def __init__(self):
            self.updates = []

        def update_run_status(self, run_id, status):
            self.updates.append((run_id, status))

    class Service:
        def __init__(self):
            self.repository = Repository()

        async def resume_after_approval(self, approval, execution):
            await gate.wait()

    service = Service()
    background = set()
    task = _schedule_auto_resume(
        service,
        {"id": "approval-1", "run_id": "run-1"},
        {"state": "completed", "text": "created"},
        background,
    )

    assert service.repository.updates == [("run-1", "running")]
    assert task in background
    assert not task.done()

    gate.set()
    await task


@pytest.mark.anyio
async def test_auto_approval_execution_is_owned_once_and_resumes_after_result():
    gate = asyncio.Event()
    calls = []

    class ApprovalService:
        async def execute_claimed(self, approval):
            calls.append(("execute", approval["id"]))
            await gate.wait()
            return {
                "approval": approval,
                "result": {"state": "completed", "text": "Pod created"},
            }

    class RunService:
        class Repository:
            def __init__(self):
                self.updates = []

            def update_run_status(self, run_id, status):
                self.updates.append((run_id, status))

        def __init__(self):
            self.repository = self.Repository()

        async def resume_after_approval(self, approval, execution):
            calls.append(("resume", approval["id"], execution["text"]))

    background = set()
    run_service = RunService()
    task = _schedule_auto_approval_execution(
        ApprovalService(),
        run_service,
        {"id": "approval-1", "run_id": "run-1", "status": "approved"},
        background,
    )

    await asyncio.sleep(0)
    assert calls == [("execute", "approval-1")]
    assert run_service.repository.updates == [("run-1", "running")]
    assert task in background
    assert not task.done()

    gate.set()
    await task
    assert calls == [
        ("execute", "approval-1"),
        ("resume", "approval-1", "Pod created"),
    ]


@pytest.mark.anyio
async def test_auto_approval_endpoint_returns_before_execution_and_deduplicates():
    gate = asyncio.Event()
    delegated = []
    resumed = []

    class Repository:
        def __init__(self):
            self.approval = {
                "id": "approval-1", "run_id": "run-1", "agent_id": "ops",
                "tool_name": "apply_k8s_yaml", "arguments": {"yaml": "kind: Pod"},
                "action_digest": "b" * 64, "status": "pending",
            }

        def claim_approval_decision(self, approval_id, decision):
            claimed = self.approval["status"] == "pending"
            if claimed:
                self.approval["status"] = decision
            return dict(self.approval), claimed

        def get_run(self, run_id):
            return {"id": run_id, "mode": "auto"}

        def get_agent(self, agent_id):
            return {"id": agent_id}

        def update_run_status(self, run_id, status):
            return None

        def list_approvals(self, run_id=None):
            return [dict(self.approval)]

    class Gateway:
        async def delegate(self, run_id, agent, message):
            delegated.append(json.loads(message))
            await gate.wait()
            return {"state": "completed", "text": "Pod created"}

    class Service:
        def __init__(self):
            self.repository = Repository()

        async def resume_after_approval(self, approval, execution):
            resumed.append((approval, execution))

    service = Service()
    app = FastAPI()
    app.include_router(create_approval_router(service, Gateway(), object()))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/api/approvals/decide", json={
            "approval_id": "approval-1", "decision": "approved",
        })
        duplicate = await client.post("/api/approvals/decide", json={
            "approval_id": "approval-1", "decision": "approved",
        })

        assert first.json()["result"]["result"]["state"] == "accepted"
        assert duplicate.json()["result"]["result"]["state"] == "already_decided"
        await asyncio.sleep(0)
        assert len(delegated) == 1
        assert resumed == []

        gate.set()
        for _ in range(10):
            if resumed:
                break
            await asyncio.sleep(0)

    assert len(resumed) == 1
    assert resumed[0][1]["text"] == "Pod created"


@pytest.mark.anyio
async def test_followup_approval_is_not_saved_as_host_summary(monkeypatch):
    followup = {
        "id": "approval-2",
        "tool_name": "delete_k8s_pod",
        "arguments": {"name": "nginx-2", "namespace": "default"},
    }

    class Repository:
        def claim_approval_decision(self, approval_id, decision):
            return {
                "id": approval_id,
                "run_id": "run-1",
                "agent_id": "ops",
                "tool_name": "delete_k8s_pod",
                "arguments": {"name": "nginx-1", "namespace": "default"},
                "action_digest": "a" * 64,
                "status": decision,
            }, True

        def get_run(self, run_id):
            return {"id": run_id, "mode": "direct"}

    async def execute_claimed(_self, approval):
        return {
            "approval": approval,
            "result": {
                "state": "input-required",
                "text": "Approval required for delete_k8s_pod",
                "approval": followup,
            },
        }

    monkeypatch.setattr(
        "backend.api.runs.ApprovalService.execute_claimed", execute_claimed
    )

    class Service:
        def __init__(self):
            self.repository = Repository()
            self.saved = []

        def save_assistant_message(self, run_id, text, **kwargs):
            self.saved.append(text)

    service = Service()
    app = FastAPI()
    app.include_router(create_approval_router(service, object(), object()))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/approvals/decide", json={
            "approval_id": "approval-1", "decision": "approved",
        })

    assert response.json()["result"]["result"]["approval"] == followup
    assert service.saved == []


def make_app(tmp_path):
    from backend.api.runs import create_router

    repository = create_test_repository()
    repository.initialize()
    repository.upsert_agent(
        {
            "id": "ops",
            "name": "Operations",
            "url": "http://ops.test",
        }
    )
    service = RunService(
        repository,
        AgentRegistry(repository),
        FakeGateway(),
        UnusedAutoHost(),
    )
    app = FastAPI()
    app.include_router(create_router(service))
    return app, repository, service


def sse_events(response: httpx.Response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.anyio
async def test_stream_first_event_has_authoritative_run_and_conversation_ids(
    tmp_path,
):
    app, repository, _service = make_app(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/runs/stream",
            json={
                "mode": "direct",
                "target_agent_id": "ops",
                "message": "Inspect the cluster",
            },
        )

    first = sse_events(response)[0]
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert first["type"] == "run.started"
    assert repository.get_run(first["run_id"])["conversation_id"] == (
        first["conversation_id"]
    )
    assert repository.get_conversation(first["conversation_id"]) is not None


@pytest.mark.anyio
async def test_direct_without_target_returns_structured_400(tmp_path):
    app, _repository, _service = make_app(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/runs/stream",
            json={"mode": "direct", "message": "Inspect the cluster"},
        )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert "target_agent_id is required" in response.json()["error"]


@pytest.mark.anyio
async def test_stream_reconnect_replays_original_run_without_creating_another(tmp_path):
    app, repository, service = make_app(tmp_path)
    completed = [event async for event in service.stream(RunCommand(
        mode="direct", target_agent_id="ops", message="Inspect",
    ))]
    original_run_id = completed[0].run_id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post("/api/runs/stream", json={
            "mode": "direct",
            "target_agent_id": "ops",
            "message": "Inspect",
            "run_id": original_run_id,
            "after_sequence": 2,
        })

    replayed = sse_events(response)
    assert {event["run_id"] for event in replayed} == {original_run_id}
    assert [event["sequence"] for event in replayed] == [
        event.sequence for event in completed[2:]
    ]
    assert len(repository.list_runs()) == 1


def test_reconnect_event_polling_has_a_short_fallback_interval():
    """A missed in-process notification must not leave the UI stale for 15s."""
    import inspect

    timeout = inspect.signature(RunService.wait_for_events).parameters["timeout"].default
    assert timeout <= 1.0


@pytest.mark.anyio
async def test_run_query_replay_and_cancel_endpoints(tmp_path):
    app, repository, service = make_app(tmp_path)
    completed = [
        event
        async for event in service.stream(
            RunCommand(
                mode="direct",
                target_agent_id="ops",
                message="Complete this run",
            )
        )
    ]
    active_stream = service.stream(
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Cancel this run",
        )
    )
    active = await anext(active_stream)
    await active_stream.aclose()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        listed = await client.post("/api/runs/list")
        fetched = await client.post(
            "/api/runs/get", json={"run_id": completed[0].run_id}
        )
        replayed = await client.post(
            "/api/runs/events",
            json={"run_id": completed[0].run_id, "after_sequence": 2},
        )
        cancelled = await client.post(
            "/api/runs/cancel", json={"run_id": active.run_id}
        )

    assert {run["id"] for run in listed.json()["result"]} == {
        completed[0].run_id,
        active.run_id,
    }
    assert fetched.json()["result"]["id"] == completed[0].run_id
    assert fetched.json()["result"]["tasks"][0]["id"].endswith(":root")
    assert [event["sequence"] for event in replayed.json()["result"]] == [
        event.sequence for event in completed[2:]
    ]
    assert cancelled.json()["result"]["status"] == "cancelled"
    assert repository.list_run_events(active.run_id)[-1].type.value == (
        "run.cancelled"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("key, configured", [("", False), ("secret-value", True)])
async def test_system_status_reports_model_configuration_without_secret(
    tmp_path, monkeypatch, key, configured
):
    app, _repository, _service = make_app(tmp_path)
    monkeypatch.delenv("HOST_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/system/status")

    assert response.status_code == 200
    assert response.json()["result"]["model"] == {
        "configured": configured
    }
    assert "secret-value" not in response.text
