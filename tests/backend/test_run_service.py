from __future__ import annotations

import asyncio
import pytest

from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEventType
from backend.orchestration.events import RunEvent
from tests.postgres_helpers import create_test_repository
from backend.registry.service import AgentRegistry


class FakeGateway:
    def __init__(self, events):
        self.events = events
        self.messages = []

    def delegate(self, run_id, agent, message):
        self.messages.append(message)
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
        FakeGateway(events),
        UnusedAutoHost(),
    )
    return repository, service


async def collect(stream):
    return [event async for event in stream]


def test_service_persists_react_checkpoint_from_round_event(tmp_path):
    repository, service = make_service(tmp_path, [])
    repository.create_run(
        "run-react",
        "conversation-react",
        "running",
        {"mode": "auto", "root_task_id": "root-react"},
    )
    checkpoint = {
        "goal": "deploy nginx",
        "round": 2,
        "decisions": [],
        "observations": {},
        "successful": [],
        "task_fingerprints": [],
        "pending_approval_task_id": None,
        "total_tasks": 2,
    }
    event = RunEvent.create(
        event_type=RunEventType.HOST_ROUND_COMPLETED,
        run_id="run-react",
        conversation_id="conversation-react",
        sequence=1,
        task_id="root-react",
        data={"round": 2, "checkpoint": checkpoint},
    )

    service._apply_checkpoint_event(event)

    assert repository.get_run("run-react")["host_state"] == checkpoint


def test_service_rebuilds_react_checkpoint_with_approved_task_result(tmp_path):
    repository, service = make_service(tmp_path, [])
    task_payload = {
        "id": "change",
        "agent_id": "orchestrator",
        "objective": "Create nginx",
        "completion_criteria": ["Deployment created"],
        "risk": "write",
        "workflow_role": "mutation",
    }
    approval_result = {
        "state": "completed",
        "text": "Deployment created",
    }
    repository.create_run(
        "run-react",
        "conversation-react",
        "approval_required",
        {
            "mode": "auto",
            "root_task_id": "root-react",
            "host_state": {
                "goal": "deploy nginx",
                "round": 2,
                "decisions": [],
                "observations": {
                    "change": {
                        "task": task_payload,
                        "result": {
                            "state": "approval_required",
                            "approval": {"id": "approval-1"},
                        },
                        "evaluation": {
                            "outcome": "blocked",
                            "reason": "approval required",
                        },
                        "actual_agent_id": "orchestrator",
                    }
                },
                "successful": [],
                "task_fingerprints": ["write-fingerprint"],
                "pending_approval_task_id": "change",
                "total_tasks": 1,
            },
        },
    )
    repository.create_task({
        "id": "root-react",
        "run_id": "run-react",
        "parent_task_id": None,
        "agent_id": "host",
        "status": "working",
    })
    repository.create_task({
        "id": "root-react:plan:change",
        "logical_id": "change",
        "run_id": "run-react",
        "parent_task_id": "root-react",
        "agent_id": "orchestrator",
        "status": "completed",
        "delegation_result": approval_result,
    })

    checkpoint = service._host_checkpoint("run-react")

    assert checkpoint["state"].pending_approval_task_id is None
    assert checkpoint["state"].observations["change"].result.text == "Deployment created"
    assert checkpoint["state"].observations["change"].evaluation.outcome == "sufficient"
    assert "change" in checkpoint["state"].successful


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
async def test_follow_up_run_receives_bounded_conversation_context(tmp_path):
    repository, service = make_service(
        tmp_path,
        [{"type": "done", "text": "Use nginx-test instead."}],
    )
    first = await collect(service.stream(RunCommand(
        mode="direct", target_agent_id="ops", message="Create an nginx pod",
    )))
    conversation_id = first[0].conversation_id

    await collect(service.stream(RunCommand(
        conversation_id=conversation_id,
        mode="direct",
        target_agent_id="ops",
        message="Create the new one",
    )))

    assert service.gateway.messages[-1] == (
        "Conversation history (oldest to newest):\n"
        "User: Create an nginx pod\n"
        "Agent: Use nginx-test instead.\n\n"
        "Current user message:\nCreate the new one"
    )
    stored = repository.list_messages(conversation_id)
    assert stored[-2]["content"] == "Create the new one"
    assert stored[-1]["content"] == "Use nginx-test instead."


def test_conversation_context_excludes_delegated_agent_reports(tmp_path):
    repository, service = make_service(tmp_path, [])
    repository.create_conversation({
        "id": "conversation-auto", "agent_id": "multi-host", "title": "nginx",
        "type": "multi", "created_at": service._now(), "updated_at": service._now(),
        "message_count": 0,
    })
    service._add_message(conversation_id="conversation-auto", role="user", content="Create nginx", task_id="root", metadata={"run_id": "run-1", "mode": "auto"})
    service._add_message(conversation_id="conversation-auto", role="agent", content="very long security report", task_id="security", metadata={"run_id": "run-1", "mode": "auto", "source": "delegated-agent"})
    service._add_message(conversation_id="conversation-auto", role="agent", content="Use nginx-test. Do you agree?", task_id="root", metadata={"run_id": "run-1", "mode": "auto", "source": "unified-run"})

    context = service._conversation_context_message("conversation-auto", "Agree")

    assert "User: Create nginx" in context
    assert "Host: Use nginx-test. Do you agree?" in context
    assert "very long security report" not in context


@pytest.mark.anyio
async def test_auto_follow_up_inherits_clarification_checkpoint(tmp_path):
    from backend.orchestration.service import RunService

    class ContinuingAutoHost:
        def __init__(self):
            self.state = None

        def register_agents_from_db(self, agents):
            pass

        async def process_message_stream(self, text, session_id):
            raise AssertionError("clarification follow-up must resume structured Host state")
            yield

        async def resume_message_stream(self, text, session_id, *, state=None, **kwargs):
            self.state = state
            yield {"type": "text", "text": "Continuing the approved plan"}
            yield {"type": "done", "session_id": session_id}

    repository = create_test_repository()
    repository.initialize()
    repository.create_conversation({
        "id": "conversation-auto", "agent_id": "multi-host", "title": "nginx",
        "type": "multi", "created_at": "2026-09-02T00:00:00+00:00", "updated_at": "2026-09-02T00:00:00+00:00",
        "message_count": 0,
    })
    checkpoint = {
        "goal": "Create nginx", "round": 1,
        "decisions": [{"action": "clarify", "reason": "confirm name", "response": "Use nginx-test?", "tasks": []}],
        "observations": {}, "successful": [], "task_fingerprints": [],
        "pending_approval_task_id": None, "total_tasks": 0,
    }
    repository.create_run("run-previous", "conversation-auto", "completed", {"mode": "auto", "root_task_id": "run-previous:root", "host_state": checkpoint})
    auto_host = ContinuingAutoHost()
    service = RunService(repository, AgentRegistry(repository), FakeGateway([]), auto_host)
    service._add_message(conversation_id="conversation-auto", role="agent", content="Use nginx-test?", task_id="run-previous:root", metadata={"run_id": "run-previous", "mode": "auto", "source": "unified-run"})

    events = await collect(service.stream(RunCommand(conversation_id="conversation-auto", mode="auto", message="Agree")))

    assert auto_host.state is not None
    assert auto_host.state.round == 1
    assert auto_host.state.decisions[-1].action == "clarify"
    assert events[-1].type == RunEventType.RUN_COMPLETED


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


@pytest.mark.anyio
async def test_approved_auto_run_resumes_pending_verification_and_host_summary(
    tmp_path,
):
    repository, service = make_service(tmp_path, [])

    class ResumingHost:
        async def resume_message_stream(
            self, text, session_id, *, plan, results, successful
        ):
            yield {
                "type": "plan_created",
                "summary": plan.summary,
                "tasks": [
                    {
                        **task.model_dump(),
                        **(
                            {"checkpoint_state": results[task.id].state}
                            if task.id in results
                            else {}
                        ),
                    }
                    for task in plan.tasks
                ],
            }
            yield {
                "type": "routing",
                "task_id": "verify",
                "agent_id": "ops",
            }
            yield {
                "type": "task_started",
                "task_id": "verify",
                "agent_id": "ops",
            }
            yield {
                "type": "task_completed",
                "task_id": "verify",
                "agent_id": "ops",
                "result": "nginx Pod Ready",
                "delegation_result": {
                    "state": "completed",
                    "text": "nginx Pod Ready",
                },
            }
            yield {"type": "synthesis_started"}
            yield {"type": "text", "text": "部署和验证均已完成"}
            yield {"type": "done"}

    service.auto_host = ResumingHost()
    repository.create_run(
        "run-auto",
        "conv-auto",
        "approval_required",
        {
            "mode": "auto",
            "request": "部署 nginx",
            "root_task_id": "root",
            "host_plan": {
                "summary": "guarded deployment",
                "tasks": [
                    {
                        "id": "root:plan:security",
                        "logical_id": "security",
                        "logical_depends_on": [],
                        "agent_id": "security",
                        "objective": "security review",
                        "completion_criteria": ["review complete"],
                    },
                    {
                        "id": "root:plan:change",
                        "logical_id": "change",
                        "logical_depends_on": ["security"],
                        "agent_id": "orchestrator",
                        "objective": "create nginx",
                        "completion_criteria": ["resource created"],
                    },
                    {
                        "id": "root:plan:verify",
                        "logical_id": "verify",
                        "logical_depends_on": ["change"],
                        "agent_id": "ops",
                        "objective": "verify nginx",
                        "completion_criteria": ["Pod Ready"],
                    },
                ],
            },
        },
    )
    repository.create_task({
        "id": "root",
        "run_id": "run-auto",
        "parent_task_id": None,
        "agent_id": "host",
        "status": "approval_required",
    })
    for logical_id, agent_id, status, result in (
        ("security", "security", "completed", {
            "state": "completed", "text": "security passed"
        }),
        ("change", "orchestrator", "approval_required", {
            "state": "approval_required", "text": ""
        }),
        ("verify", "ops", "pending", None),
    ):
        repository.create_task({
            "id": f"root:plan:{logical_id}",
            "run_id": "run-auto",
            "parent_task_id": "root",
            "agent_id": agent_id,
            "status": status,
            "logical_id": logical_id,
            **({"delegation_result": result} if result else {}),
        })

    events = await service.resume_after_approval(
        {
            "id": "approval-1",
            "run_id": "run-auto",
            "agent_id": "orchestrator",
            "status": "approved",
        },
        {
            "state": "completed",
            "text": "nginx Deployment created",
            "specialist_output": {
                "summary": "nginx Deployment created",
                "continuation": {"allowed": True},
            },
        },
    )

    assert repository.get_run("run-auto")["status"] == "completed"
    assert repository.get_task("root:plan:change")["status"] == "completed"
    assert repository.get_task("root:plan:verify")["status"] == "completed"
    assert any(
        event.type == RunEventType.MESSAGE_COMPLETED
        and event.task_id == "root:plan:verify"
        and event.data["content"] == "nginx Pod Ready"
        for event in events
    )
    assert any(
        event.type == RunEventType.MESSAGE_COMPLETED
        and event.task_id == "root"
        and event.data["content"] == "部署和验证均已完成"
        for event in events
    )
