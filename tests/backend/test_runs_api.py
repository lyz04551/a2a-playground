from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

from backend.orchestration.commands import RunCommand
from backend.orchestration.service import RunService
from tests.postgres_helpers import create_test_repository
from backend.registry.service import AgentRegistry


class FakeGateway:
    def delegate(self, run_id, agent, message):
        async def stream():
            yield {"type": "done", "text": "Ready"}

        return stream()


class UnusedAutoHost:
    async def process_message_stream(self, text, session_id):
        raise AssertionError("unexpected Auto execution")
        yield


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
