from __future__ import annotations

import asyncio
import pytest

from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEventType
from backend.persistence.repository import SQLiteRepository
from backend.registry.service import AgentRegistry


class FakeGateway:
    def __init__(self, events):
        self.events = events

    def delegate(self, run_id, agent, message):
        async def stream():
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                yield event

        return stream()


class UnusedAutoHost:
    async def process_message_stream(self, text, session_id):
        raise AssertionError("the Auto Host must not be used for Direct runs")
        yield


def make_service(tmp_path, events):
    from backend.orchestration.service import RunService

    repository = SQLiteRepository(tmp_path / "playground.db")
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
        FakeGateway(events),
        UnusedAutoHost(),
    )
    return repository, service


async def collect(stream):
    return [event async for event in stream]


@pytest.mark.anyio
async def test_stream_creates_conversation_run_and_root_task(tmp_path):
    repository, service = make_service(
        tmp_path,
        [{"type": "done", "text": "Ready"}],
    )

    events = await collect(
        service.stream(
            RunCommand(
                mode="direct",
                target_agent_id="ops",
                message="Inspect the cluster",
            )
        )
    )

    started = events[0]
    assert started.type == RunEventType.RUN_STARTED
    assert started.data == {
        "mode": "direct",
        "target_agent_id": "ops",
    }
    assert repository.get_conversation(started.conversation_id)["id"] == (
        started.conversation_id
    )
    run = repository.get_run(started.run_id)
    assert run["conversation_id"] == started.conversation_id
    assert run["status"] == "completed"
    tasks = repository.list_tasks(started.run_id)
    assert len(tasks) == 1
    assert tasks[0]["parent_task_id"] is None
    assert tasks[0]["status"] == "completed"


@pytest.mark.anyio
async def test_persists_each_event_before_yielding_it(tmp_path):
    repository, service = make_service(
        tmp_path,
        [{"type": "done", "text": "Ready"}],
    )
    stream = service.stream(
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        )
    )

    yielded = []
    async for event in stream:
        yielded.append(event)
        assert repository.list_run_events(
            event.run_id, event.sequence - 1
        )[0] == event

    persisted = repository.list_run_events(yielded[0].run_id)
    assert persisted == yielded
    assert [event.sequence for event in persisted] == list(
        range(1, len(persisted) + 1)
    )


@pytest.mark.anyio
async def test_saves_the_completed_assistant_message_once(tmp_path):
    repository, service = make_service(
        tmp_path,
        [
            {"type": "text", "text": "Re", "task_id": "remote-1"},
            {"type": "text", "text": "ady", "task_id": "remote-1"},
            {"type": "done", "text": "Ready", "task_id": "remote-1"},
        ],
    )

    events = await collect(
        service.stream(
            RunCommand(
                mode="direct",
                target_agent_id="ops",
                message="Inspect the cluster",
            )
        )
    )

    messages = repository.list_messages(events[0].conversation_id)
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "Inspect the cluster"),
        ("agent", "Ready"),
    ]
    assert messages[-1]["metadata"]["run_id"] == events[0].run_id


@pytest.mark.anyio
async def test_failure_marks_run_and_root_task_and_preserves_partial_output(
    tmp_path,
):
    repository, service = make_service(
        tmp_path,
        [
            {"type": "text", "text": "Part", "task_id": "remote-1"},
            RuntimeError("gateway unavailable"),
        ],
    )

    events = await collect(
        service.stream(
            RunCommand(
                mode="direct",
                target_agent_id="ops",
                message="Inspect the cluster",
            )
        )
    )

    assert events[-1].type == RunEventType.RUN_FAILED
    assert events[-1].data["error"] == "gateway unavailable"
    assert repository.get_run(events[0].run_id)["status"] == "failed"
    assert repository.list_tasks(events[0].run_id)[0]["status"] == "failed"
    assert [
        (message["role"], message["content"])
        for message in repository.list_messages(events[0].conversation_id)
    ] == [
        ("user", "Inspect the cluster"),
        ("agent", "Part"),
    ]


@pytest.mark.anyio
async def test_closing_client_iterator_cancels_orphaned_run(tmp_path):
    repository, service = make_service(
        tmp_path,
        [
            {"type": "text", "text": "partial"},
            {"type": "done", "text": "complete"},
        ],
    )
    stream = service.stream(
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        )
    )

    started = await anext(stream)
    await stream.aclose()

    assert repository.get_run(started.run_id)["status"] == "cancelled"
    assert repository.list_tasks(started.run_id)[0]["status"] == "cancelled"
    assert [event.type for event in repository.list_run_events(started.run_id)] == [
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]


@pytest.mark.anyio
async def test_returns_only_persisted_events_after_sequence_cursor(tmp_path):
    repository, service = make_service(
        tmp_path,
        [{"type": "done", "text": "Ready"}],
    )
    events = await collect(
        service.stream(
            RunCommand(
                mode="direct",
                target_agent_id="ops",
                message="Inspect the cluster",
            )
        )
    )

    replayed = service.events(events[0].run_id, after_sequence=2)

    assert replayed == events[2:]


@pytest.mark.anyio
async def test_cancelled_live_stream_cannot_resume_or_complete(tmp_path):
    repository, service = make_service(
        tmp_path,
        [{"type": "done", "text": "Ready"}],
    )
    stream = service.stream(
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        )
    )
    started = await anext(stream)

    service.cancel(started.run_id)
    remaining = [event async for event in stream]

    assert remaining == []
    assert repository.get_run(started.run_id)["status"] == "cancelled"
    assert [event.type for event in service.events(started.run_id)] == [
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]


@pytest.mark.anyio
async def test_cancel_stops_active_execution_and_cleans_registry(tmp_path):
    gate = asyncio.Event()

    class BlockingGateway:
        def delegate(self, run_id, agent, message):
            async def stream():
                await gate.wait()
                yield {"type": "done", "text": "too late"}
            return stream()

    repository, service = make_service(tmp_path, [])
    service.gateway = BlockingGateway()
    started = asyncio.Queue()

    async def consume():
        async for event in service.stream(
            RunCommand(mode="direct", target_agent_id="ops", message="inspect")
        ):
            if event.type == RunEventType.RUN_STARTED:
                await started.put(event)

    task = asyncio.create_task(consume())
    event = await started.get()
    service.cancel(event.run_id)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert repository.get_run(event.run_id)["status"] == "cancelled"
    assert event.run_id not in service._active_tasks
    assert [item.type for item in service.events(event.run_id)].count(
        RunEventType.RUN_CANCELLED
    ) == 1
