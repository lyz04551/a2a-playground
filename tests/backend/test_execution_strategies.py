from __future__ import annotations

import pytest
from pydantic import ValidationError
from a2a.types import TaskState

from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEvent, RunEventType
from backend.orchestration.strategies import (
    AutoExecutionStrategy,
    DirectExecutionStrategy,
)
from backend.a2a_client import A2ATransportError


class FakeRegistry:
    def __init__(self, agents: dict[str, dict]):
        self.agents = agents

    def get(self, agent_id: str) -> dict | None:
        return self.agents.get(agent_id)


class FakeGateway:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def delegate(self, run_id, agent, message):
        self.calls.append((run_id, agent, message))

        async def stream():
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                yield event

        return stream()


class PublicTraceGateway(FakeGateway):
    def delegate_stream(self, run_id, agent, message):
        return self.delegate(run_id, agent, message)


class FakeHostManager:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def process_message_stream(self, text, session_id):
        self.calls.append((text, session_id))
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


def _direct_strategy(gateway: FakeGateway) -> DirectExecutionStrategy:
    registry = FakeRegistry(
        {
            "ops": {
                "id": "ops",
                "name": "Operations",
                "url": "http://ops.test",
            }
        }
    )
    return DirectExecutionStrategy(
        registry,
        gateway,
        run_id="run-direct",
        conversation_id="conversation-direct",
        root_task_id="task-direct",
    )


def _auto_strategy(host: FakeHostManager) -> AutoExecutionStrategy:
    return AutoExecutionStrategy(
        host,
        run_id="run-auto",
        conversation_id="conversation-auto",
        root_task_id="task-host",
    )


async def _collect(strategy, command):
    return [event async for event in strategy.execute(command)]


@pytest.mark.anyio
async def test_direct_transport_failure_exposes_only_safe_message():
    events = await _collect(
        _direct_strategy(
            FakeGateway([
                A2ATransportError(
                    "connection failed with token secret-value",
                    public_message="Agent is unavailable",
                )
            ])
        ),
        RunCommand(mode="direct", target_agent_id="ops", message="inspect"),
    )

    failed = next(event for event in events if event.type == RunEventType.TASK_FAILED)
    assert failed.data["error"] == "Agent is unavailable"
    assert "secret-value" not in str(failed.data)


def test_direct_command_requires_a_target_with_stable_validation_message():
    with pytest.raises(ValidationError, match="target_agent_id is required"):
        RunCommand(mode="direct", message="Inspect the cluster")


def test_auto_command_discards_an_accidental_target():
    command = RunCommand(
        mode="auto",
        target_agent_id="ops",
        message="Inspect the cluster",
    )

    assert command.target_agent_id is None


def test_direct_command_trims_its_target():
    command = RunCommand(
        mode="direct",
        target_agent_id="  ops  ",
        message="Inspect the cluster",
    )

    assert command.target_agent_id == "ops"


@pytest.mark.anyio
async def test_direct_normalizes_one_agent_stream_under_the_root_task():
    gateway = FakeGateway(
        [
            {
                "type": "tool_call",
                "id": "call-1",
                "tool": "list_clusters",
                "args": {"region": "east"},
                "task_id": "remote-1",
            },
            {
                "type": "tool_result",
                "id": "call-1",
                "tool": "list_clusters",
                "result": "cluster-a",
                "task_id": "remote-1",
            },
            {
                "type": "text",
                "text": "Found cluster-a",
                "task_id": "remote-1",
            },
            {
                "type": "done",
                "text": "Found cluster-a",
                "task_id": "remote-1",
            },
        ]
    )

    events = await _collect(
        _direct_strategy(gateway),
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        ),
    )

    assert all(isinstance(event, RunEvent) for event in events)
    assert [event.type for event in events] == [
        RunEventType.TASK_DELEGATED,
        RunEventType.TOOL_CALLED,
        RunEventType.TOOL_COMPLETED,
        RunEventType.MESSAGE_DELTA,
        RunEventType.MESSAGE_COMPLETED,
        RunEventType.TASK_COMPLETED,
    ]
    assert {event.task_id for event in events} == {"task-direct"}
    assert all(event.parent_task_id is None for event in events)
    assert [event.sequence for event in events] == list(
        range(1, len(events) + 1)
    )
    assert events[1].data == {
        "agent_id": "ops",
        "tool_call_id": "call-1",
        "tool": "list_clusters",
        "arguments": {"region": "east"},
        "remote_task_id": "remote-1",
    }
    assert events[-2].data["content"] == "Found cluster-a"
    assert events[-1].data["remote_task_id"] == "remote-1"
    assert gateway.calls == [
        (
            "run-direct",
            {
                "id": "ops",
                "name": "Operations",
                "url": "http://ops.test",
            },
            "Inspect the cluster",
        )
    ]


@pytest.mark.anyio
async def test_direct_prefers_the_public_trace_stream_when_available():
    gateway = PublicTraceGateway([
        {"type": "tool_call", "id": "call-1", "tool": "get_nodes"},
        {"type": "done", "text": "healthy"},
    ])

    events = await _collect(
        _direct_strategy(gateway),
        RunCommand(mode="direct", target_agent_id="ops", message="Inspect"),
    )

    assert any(event.type == RunEventType.TOOL_CALLED for event in events)
    assert len(gateway.calls) == 1


@pytest.mark.anyio
async def test_direct_turns_remote_errors_into_a_failed_task_event():
    gateway = FakeGateway(
        [
            {
                "type": "error",
                "text": "remote unavailable",
                "task_id": "remote-2",
            }
        ]
    )

    events = await _collect(
        _direct_strategy(gateway),
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        ),
    )

    assert [event.type for event in events] == [
        RunEventType.TASK_DELEGATED,
        RunEventType.TASK_FAILED,
    ]
    assert events[-1].task_id == "task-direct"
    assert events[-1].data == {
        "agent_id": "ops",
        "error": "remote unavailable",
        "remote_task_id": "remote-2",
    }


@pytest.mark.anyio
async def test_direct_accepts_sdk_task_state_enum_as_completed():
    events = await _collect(
        _direct_strategy(FakeGateway([
            {"type": "status", "state": TaskState.completed, "final": True},
        ])),
        RunCommand(mode="direct", target_agent_id="ops", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_COMPLETED


@pytest.mark.anyio
@pytest.mark.parametrize(
    "upstream",
    [
        [],
        [{"type": "text", "text": "partial", "task_id": "remote-3"}],
        ["not-an-event", 7, {"type": "unknown"}],
        [{"type": "unknown"}],
    ],
)
async def test_direct_requires_an_explicit_valid_terminal_event(upstream):
    events = await _collect(
        _direct_strategy(FakeGateway(upstream)),
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        ),
    )

    assert events[-1].type == RunEventType.TASK_FAILED
    assert not any(
        event.type == RunEventType.TASK_COMPLETED for event in events
    )


@pytest.mark.anyio
async def test_direct_ignores_benign_unknown_events_before_done():
    events = await _collect(
        _direct_strategy(
            FakeGateway(
                [
                    {"type": "heartbeat"},
                    {"type": "done", "text": "complete"},
                ]
            )
        ),
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect the cluster",
        ),
    )

    assert events[-1].type == RunEventType.TASK_COMPLETED


@pytest.mark.anyio
async def test_direct_strategy_instances_are_single_use():
    strategy = _direct_strategy(
        FakeGateway([{"type": "done", "text": "complete"}])
    )
    command = RunCommand(
        mode="direct",
        target_agent_id="ops",
        message="Inspect the cluster",
    )

    await _collect(strategy, command)

    with pytest.raises(RuntimeError, match="single-use"):
        await _collect(strategy, command)


@pytest.mark.anyio
async def test_direct_wrong_mode_does_not_consume_single_use_strategy():
    strategy = _direct_strategy(
        FakeGateway([{"type": "done", "text": "complete"}])
    )

    with pytest.raises(ValueError, match="requires direct mode"):
        await _collect(
            strategy,
            RunCommand(mode="auto", message="Inspect"),
        )

    events = await _collect(
        strategy,
        RunCommand(
            mode="direct",
            target_agent_id="ops",
            message="Inspect",
        ),
    )
    assert events[-1].type == RunEventType.TASK_COMPLETED


@pytest.mark.anyio
async def test_auto_normalizes_two_routings_as_children_of_the_host_task():
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {
                "type": "routing",
                "agent": "Operations",
                "agent_id": "ops",
            },
            {
                "type": "tool_result",
                "id": "send-ops",
                "tool": "send_task",
                "result": "healthy",
            },
            {
                "type": "tool_call",
                "id": "send-security",
                "tool": "send_task",
                "args": {"agent_id": "security", "message": "audit"},
            },
            {
                "type": "routing",
                "agent": "Security",
                "agent_id": "security",
            },
            {
                "type": "approval_required",
                "agent_id": "security",
                "approval": {"id": "approval-1", "tool_name": "rotate_key"},
            },
            {"type": "text", "text": "Review complete"},
            {"type": "done", "session_id": "run-auto"},
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(
            mode="auto",
            target_agent_id="ignored",
            message="Inspect and audit",
        ),
    )

    delegated = [
        event for event in events
        if event.type == RunEventType.TASK_DELEGATED
    ]
    assert len(delegated) == 2
    assert len({event.task_id for event in delegated}) == 2
    assert all(event.parent_task_id == "task-host" for event in delegated)
    assert [event.data["agent_id"] for event in delegated] == ["ops", "security"]
    completed_children = [event for event in events if event.type == RunEventType.TASK_COMPLETED and event.parent_task_id == "task-host"]
    assert [event.task_id for event in completed_children] == [delegated[0].task_id]
    approval = next(event for event in events if event.type == RunEventType.APPROVAL_REQUIRED)
    assert approval.task_id == delegated[1].task_id
    assert approval.parent_task_id == "task-host"
    assert approval.data["approval"]["id"] == "approval-1"
    host_events = [event for event in events if event.task_id == "task-host"]
    assert [event.type for event in host_events] == [RunEventType.HOST_PLANNING, RunEventType.MESSAGE_DELTA, RunEventType.MESSAGE_COMPLETED, RunEventType.TASK_STATUS_CHANGED]
    assert host_events[-1].data["state"] == "approval_required"
    for tool_call_id in ("send-ops", "send-security"):
        lifecycle = [event for event in events if event.data.get("host_tool_call_id") == tool_call_id or event.data.get("tool_call_id") == tool_call_id]
        assert lifecycle[0].type == RunEventType.TASK_DELEGATED
        assert lifecycle[1].type == RunEventType.TOOL_CALLED
        assert len({event.task_id for event in lifecycle}) == 1
        assert all(event.parent_task_id == "task-host" for event in lifecycle)
    assert all(isinstance(event, RunEvent) for event in events)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert host.calls == [("Inspect and audit", "run-auto")]


@pytest.mark.anyio
async def test_auto_places_remote_tool_events_under_the_planned_agent_task():
    host = FakeHostManager([
        {
            "type": "plan_created",
            "summary": "inspect",
            "tasks": [{
                "id": "inspect",
                "agent_id": "ops",
                "objective": "Inspect nodes",
                "depends_on": [],
            }],
        },
        {"type": "routing", "task_id": "inspect", "agent_id": "ops"},
        {
            "type": "tool_call",
            "task_id": "inspect",
            "agent_id": "ops",
            "id": "call-1",
            "tool": "get_nodes",
            "args": {"wide": True},
        },
        {
            "type": "tool_result",
            "task_id": "inspect",
            "agent_id": "ops",
            "id": "call-1",
            "tool": "get_nodes",
            "result": "master Ready",
        },
        {"type": "task_completed", "task_id": "inspect", "agent_id": "ops", "result": "healthy"},
        {"type": "text", "text": "complete"},
        {"type": "done", "session_id": "run-auto"},
    ])

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    tool_events = [event for event in events if event.type in {
        RunEventType.TOOL_CALLED, RunEventType.TOOL_COMPLETED,
    }]
    assert [event.task_id for event in tool_events] == [
        "task-host:plan:inspect", "task-host:plan:inspect",
    ]
    assert tool_events[0].data["agent_id"] == "ops"


@pytest.mark.anyio
async def test_auto_uses_pending_delegation_for_approval_before_routing():
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "change replicas"},
            },
            {
                "type": "approval_required",
                "agent_id": "ops",
                "approval": {"id": "approval-2"},
            },
            {
                "type": "routing",
                "agent": "Operations",
                "agent_id": "ops",
            },
            {
                "type": "tool_result",
                "id": "send-ops",
                "tool": "send_task",
                "result": "approval required",
            },
            {"type": "done", "session_id": "run-auto"},
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Scale the service"),
    )

    delegated = next(
        event for event in events
        if event.type == RunEventType.TASK_DELEGATED
    )
    assert sum(
        event.type == RunEventType.TASK_DELEGATED for event in events
    ) == 1
    approval = next(
        event for event in events
        if event.type == RunEventType.APPROVAL_REQUIRED
    )
    assert approval.task_id == delegated.task_id
    assert approval.parent_task_id == "task-host"
    assert not any(
        event.type == RunEventType.TASK_COMPLETED
        and event.task_id == delegated.task_id
        for event in events
    )
    child_status = next(
        event for event in events
        if event.type == RunEventType.TASK_STATUS_CHANGED
        and event.task_id == delegated.task_id
    )
    assert child_status.data["state"] == "approval_required"
    assert events[-1].type == RunEventType.TASK_STATUS_CHANGED
    assert events[-1].task_id == "task-host"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        {"type": "error", "text": "host failed"},
        RuntimeError("host crashed"),
    ],
)
async def test_auto_failure_closes_each_active_delegated_child(failure):
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {
                "type": "routing",
                "agent": "Operations",
                "agent_id": "ops",
            },
            {
                "type": "tool_call",
                "id": "send-security",
                "tool": "send_task",
                "args": {"agent_id": "security", "message": "audit"},
            },
            {
                "type": "routing",
                "agent": "Security",
                "agent_id": "security",
            },
            failure,
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    delegated = [
        event for event in events
        if event.type == RunEventType.TASK_DELEGATED
    ]
    failed = [
        event for event in events if event.type == RunEventType.TASK_FAILED
    ]
    assert [event.task_id for event in failed] == [
        *(event.task_id for event in delegated),
        "task-host",
    ]
    assert all(
        event.parent_task_id == "task-host" for event in failed[:-1]
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "upstream",
    [
        [],
        [{"type": "text", "text": "partial"}],
        ["not-an-event"],
        [{"type": "unknown"}],
    ],
)
async def test_auto_requires_an_explicit_valid_terminal_event(upstream):
    events = await _collect(
        _auto_strategy(FakeHostManager(upstream)),
        RunCommand(mode="auto", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_FAILED
    assert not any(
        event.type == RunEventType.TASK_COMPLETED for event in events
    )


@pytest.mark.anyio
async def test_auto_ignores_benign_unknown_events_before_done():
    events = await _collect(
        _auto_strategy(
            FakeHostManager(
                [{"type": "heartbeat"}, {"type": "done"}]
            )
        ),
        RunCommand(mode="auto", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_COMPLETED


@pytest.mark.anyio
async def test_auto_fails_send_task_result_without_routing():
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {
                "type": "tool_result",
                "id": "send-ops",
                "tool": "send_task",
                "result": "healthy",
            },
            {"type": "done"},
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_FAILED
    assert not any(
        event.type in {
            RunEventType.TOOL_COMPLETED,
            RunEventType.TASK_COMPLETED,
        }
        for event in events
    )


@pytest.mark.anyio
async def test_auto_fails_malformed_routing_without_child_tool_events():
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {"type": "routing", "agent": "Operations"},
            {
                "type": "tool_result",
                "id": "send-ops",
                "tool": "send_task",
                "result": "healthy",
            },
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_FAILED
    assert not any(
        event.parent_task_id == "task-host" for event in events
    )


@pytest.mark.anyio
async def test_auto_strategy_instances_are_single_use():
    strategy = _auto_strategy(FakeHostManager([{"type": "done"}]))
    command = RunCommand(mode="auto", message="Inspect")

    await _collect(strategy, command)

    with pytest.raises(RuntimeError, match="single-use"):
        await _collect(strategy, command)


@pytest.mark.anyio
async def test_auto_wrong_mode_does_not_consume_single_use_strategy():
    strategy = _auto_strategy(FakeHostManager([{"type": "done"}]))

    with pytest.raises(ValueError, match="requires auto mode"):
        await _collect(
            strategy,
            RunCommand(
                mode="direct",
                target_agent_id="ops",
                message="Inspect",
            ),
        )

    events = await _collect(
        strategy,
        RunCommand(mode="auto", message="Inspect"),
    )
    assert events[-1].type == RunEventType.TASK_COMPLETED


@pytest.mark.anyio
@pytest.mark.parametrize("approval_agent", ["security", "ops"])
async def test_auto_rejects_approval_after_only_candidate_completed(
    approval_agent,
):
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {
                "type": "routing",
                "agent": "Operations",
                "agent_id": "ops",
            },
            {
                "type": "tool_result",
                "id": "send-ops",
                "tool": "send_task",
                "result": "complete",
            },
            {
                "type": "approval_required",
                "agent_id": approval_agent,
                "approval": {"id": "approval-late"},
            },
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_FAILED
    assert events[-1].task_id == "task-host"
    assert not any(
        event.type == RunEventType.APPROVAL_REQUIRED for event in events
    )


@pytest.mark.anyio
async def test_auto_uses_explicit_task_metadata_over_current_child():
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {
                "type": "routing",
                "agent": "Operations",
                "agent_id": "ops",
            },
            {
                "type": "tool_call",
                "id": "send-security",
                "tool": "send_task",
                "args": {"agent_id": "security", "message": "audit"},
            },
            {
                "type": "routing",
                "agent": "Security",
                "agent_id": "security",
            },
            {
                "type": "approval_required",
                "task_id": "task-host:delegation:1",
                "approval": {"id": "approval-explicit"},
            },
            {"type": "error", "text": "stop"},
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    approval = next(
        event for event in events
        if event.type == RunEventType.APPROVAL_REQUIRED
    )
    assert approval.task_id == "task-host:delegation:1"


@pytest.mark.anyio
async def test_auto_rejects_explicit_call_with_mismatched_agent():
    host = FakeHostManager(
        [
            {
                "type": "tool_call",
                "id": "send-ops",
                "tool": "send_task",
                "args": {"agent_id": "ops", "message": "inspect"},
            },
            {
                "type": "routing",
                "agent": "Operations",
                "agent_id": "ops",
            },
            {
                "type": "approval_required",
                "id": "send-ops",
                "agent_id": "security",
                "approval": {"id": "approval-mismatch"},
            },
        ]
    )

    events = await _collect(
        _auto_strategy(host),
        RunCommand(mode="auto", message="Inspect"),
    )

    assert events[-1].type == RunEventType.TASK_FAILED
    assert not any(
        event.type == RunEventType.APPROVAL_REQUIRED for event in events
    )


@pytest.mark.anyio
async def test_auto_normalizes_structured_orchestration_lifecycle():
    host = FakeHostManager(
        [
            {
                "type": "plan_created",
                "summary": "inspect",
                "tasks": [{"id": "inspect", "agent_id": "ops"}],
            },
            {
                "type": "context_prepared",
                "task_id": "inspect",
                "agent_id": "ops",
                "depends_on": [],
            },
            {
                "type": "routing",
                "task_id": "inspect",
                "agent_id": "ops",
                "agent": "Operations",
            },
            {"type": "task_started", "task_id": "inspect", "agent_id": "ops"},
            {
                "type": "task_evaluated",
                "task_id": "inspect",
                "agent_id": "ops",
                "outcome": "sufficient",
                "reason": "has evidence",
            },
            {
                "type": "task_completed",
                "task_id": "inspect",
                "agent_id": "ops",
                "result": "healthy",
            },
            {"type": "synthesis_started"},
            {"type": "text", "text": "Pod is healthy"},
            {"type": "done"},
        ]
    )

    events = await _collect(
        _auto_strategy(host), RunCommand(mode="auto", message="Inspect")
    )

    assert [event.type for event in events] == [
        RunEventType.HOST_PLANNING,
        RunEventType.HOST_PLAN_CREATED,
        RunEventType.TASK_CONTEXT_PREPARED,
        RunEventType.TASK_DELEGATED,
        RunEventType.TASK_STARTED,
        RunEventType.TASK_EVALUATED,
        RunEventType.TASK_COMPLETED,
        RunEventType.HOST_SYNTHESIS_STARTED,
        RunEventType.MESSAGE_DELTA,
        RunEventType.MESSAGE_COMPLETED,
        RunEventType.TASK_COMPLETED,
    ]
    child = next(
        event for event in events
        if event.type == RunEventType.TASK_DELEGATED
    )
    assert child.task_id == "task-host:plan:inspect"


@pytest.mark.anyio
async def test_auto_keeps_logical_task_id_across_retry_and_replacement():
    host = FakeHostManager(
        [
            {"type": "routing", "task_id": "inspect", "agent_id": "ops"},
            {
                "type": "task_retry_scheduled",
                "task_id": "inspect",
                "agent_id": "ops",
                "attempt": 2,
                "reason": "temporary",
            },
            {
                "type": "plan_revised",
                "task_id": "inspect",
                "agent_id": "ops",
                "replacement_agent_id": "fallback",
                "reason": "offline",
            },
            {
                "type": "task_completed",
                "task_id": "inspect",
                "agent_id": "fallback",
                "result": "healthy",
            },
            {"type": "done"},
        ]
    )

    events = await _collect(
        _auto_strategy(host), RunCommand(mode="auto", message="Inspect")
    )
    child_events = [
        event for event in events if event.parent_task_id == "task-host"
    ]

    assert {event.task_id for event in child_events} == {
        "task-host:plan:inspect"
    }
    assert any(
        event.type == RunEventType.HOST_PLAN_REVISED
        and event.data["replacement_agent_id"] == "fallback"
        for event in child_events
    )


@pytest.mark.anyio
async def test_auto_links_structured_plan_approval_to_logical_child():
    host = FakeHostManager(
        [
            {
                "type": "routing",
                "task_id": "change",
                "agent_id": "orchestrator",
            },
            {
                "type": "approval_required",
                "task_id": "change",
                "agent_id": "orchestrator",
                "approval": {"id": "approval-1"},
            },
            {"type": "done"},
        ]
    )

    events = await _collect(
        _auto_strategy(host), RunCommand(mode="auto", message="Change")
    )

    approval = next(
        event for event in events
        if event.type == RunEventType.APPROVAL_REQUIRED
    )
    assert approval.task_id == "task-host:plan:change"


@pytest.mark.anyio
async def test_auto_accepts_blocked_plan_task_that_was_never_routed():
    host = FakeHostManager([
        {"type": "plan_created", "summary": "parallel", "tasks": [
            {"id": "ops", "agent_id": "ops", "objective": "inspect", "completion_criteria": ["result"]},
            {"id": "summary", "agent_id": "ops", "objective": "combine", "depends_on": ["ops"], "completion_criteria": ["summary"]},
        ]},
        {"type": "context_prepared", "task_id": "ops", "agent_id": "ops", "depends_on": []},
        {"type": "routing", "task_id": "ops", "agent_id": "ops"},
        {"type": "task_started", "task_id": "ops", "agent_id": "ops"},
        {"type": "task_failed", "task_id": "ops", "agent_id": "ops", "error": "unavailable"},
        {"type": "task_blocked", "task_id": "summary", "agent_id": "ops", "reason": "dependency failed"},
        {"type": "synthesis_started"},
        {"type": "text", "text": "partial conclusion"},
        {"type": "done"},
    ])

    events = await _collect(
        _auto_strategy(host), RunCommand(mode="auto", message="Inspect")
    )

    assert any(event.type == RunEventType.TASK_BLOCKED for event in events)
    assert any(event.type == RunEventType.MESSAGE_COMPLETED for event in events)
    assert events[-1].type == RunEventType.TASK_COMPLETED
