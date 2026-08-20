"""Persistence-free Direct and Auto execution strategies.

Strategy instances are bound to one Run and are deliberately single-use.
``RunService`` owns creating them with authoritative IDs and sequence starts,
then persists the normalized :class:`RunEvent` objects they yield.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEvent, RunEventType
from backend.a2a_client import public_error_message


class ExecutionStrategy(Protocol):
    def execute(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        """Execute one bound Run and yield normalized, unpersisted events."""


class _UpstreamProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class _RunContext:
    run_id: str
    conversation_id: str
    root_task_id: str
    sequence_start: int


class _EventBuilder:
    def __init__(self, context: _RunContext):
        self._context = context
        self._next_sequence = context.sequence_start

    def create(
        self,
        event_type: RunEventType,
        *,
        task_id: str,
        parent_task_id: str | None,
        data: dict[str, Any],
    ) -> RunEvent:
        event = RunEvent.create(
            event_type=event_type,
            run_id=self._context.run_id,
            conversation_id=self._context.conversation_id,
            sequence=self._next_sequence,
            task_id=task_id,
            parent_task_id=parent_task_id,
            data=data,
        )
        self._next_sequence += 1
        return event


class _RunBoundStrategy:
    def __init__(
        self,
        *,
        run_id: str,
        conversation_id: str,
        root_task_id: str,
        sequence_start: int = 1,
    ):
        values = {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "root_task_id": root_task_id,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(f"{missing[0]} is required")
        if sequence_start < 1:
            raise ValueError("sequence_start must be positive")
        self._context = _RunContext(
            run_id=run_id,
            conversation_id=conversation_id,
            root_task_id=root_task_id,
            sequence_start=sequence_start,
        )
        self._execution_started = False

    def _begin_execution(self) -> None:
        if self._execution_started:
            raise RuntimeError("execution strategy instances are single-use")
        self._execution_started = True


def _require_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _UpstreamProtocolError(
            "upstream stream produced a malformed event"
        )
    return value


async def _iterate_gateway_output(value: Any) -> AsyncIterator[Mapping[str, Any]]:
    if inspect.isawaitable(value):
        value = await value

    if isinstance(value, AsyncIterable):
        async for item in value:
            yield _require_mapping(item)
        return

    if isinstance(value, Mapping):
        if "events" not in value:
            yield value
            return
        nested = value["events"]
        if not isinstance(nested, Iterable) or isinstance(
            nested, (str, bytes, Mapping)
        ):
            raise _UpstreamProtocolError(
                "gateway events must be an iterable of event mappings"
            )
        for item in nested:
            yield _require_mapping(item)
        final_value = {
            key: item for key, item in value.items() if key != "events"
        }
        if final_value:
            yield final_value
        return

    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            yield _require_mapping(item)
        return

    raise _UpstreamProtocolError("gateway returned a malformed stream")


def _failure_text(event: Mapping[str, Any]) -> str:
    return str(
        event.get("error")
        or event.get("text")
        or event.get("message")
        or "remote execution failed"
    )


def _normalized_state(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").replace("_", "-").lower()


def _is_failed_state(value: Any) -> bool:
    return _normalized_state(value) in {
        "failed",
        "error",
        "rejected",
        "canceled",
        "cancelled",
    }


class DirectExecutionStrategy(_RunBoundStrategy):
    """Delegate a Run to exactly one explicitly selected Agent."""

    def __init__(
        self,
        registry,
        gateway,
        *,
        run_id: str,
        conversation_id: str,
        root_task_id: str,
        sequence_start: int = 1,
    ):
        super().__init__(
            run_id=run_id,
            conversation_id=conversation_id,
            root_task_id=root_task_id,
            sequence_start=sequence_start,
        )
        self._registry = registry
        self._gateway = gateway

    async def execute(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        if command.mode != "direct":
            raise ValueError("DirectExecutionStrategy requires direct mode")
        self._begin_execution()

        builder = _EventBuilder(self._context)
        task_id = self._context.root_task_id
        agent_id = command.target_agent_id or ""
        agent = self._registry.get(agent_id)
        if agent is None:
            yield builder.create(
                RunEventType.TASK_FAILED,
                task_id=task_id,
                parent_task_id=None,
                data={
                    "agent_id": agent_id,
                    "error": f"Agent '{agent_id}' not found",
                },
            )
            return

        yield builder.create(
            RunEventType.TASK_DELEGATED,
            task_id=task_id,
            parent_task_id=None,
            data={
                "agent_id": agent_id,
                "agent_name": agent.get("name", agent_id),
            },
        )

        accumulated = ""
        remote_task_id = ""
        awaiting_approval = False

        def common_data() -> dict[str, Any]:
            data: dict[str, Any] = {"agent_id": agent_id}
            if remote_task_id:
                data["remote_task_id"] = remote_task_id
            return data

        def failed(error: str, **extra: Any) -> RunEvent:
            return builder.create(
                RunEventType.TASK_FAILED,
                task_id=task_id,
                parent_task_id=None,
                data={**common_data(), "error": error, **extra},
            )

        try:
            delegate = getattr(
                self._gateway, "delegate_stream", self._gateway.delegate
            )
            output = delegate(
                self._context.run_id,
                agent,
                command.message,
            )
            async for upstream in _iterate_gateway_output(output):
                event_type = str(upstream.get("type") or "")
                if upstream.get("task_id"):
                    remote_task_id = str(upstream["task_id"])

                if event_type == "tool_call":
                    yield builder.create(
                        RunEventType.TOOL_CALLED,
                        task_id=task_id,
                        parent_task_id=None,
                        data={
                            **common_data(),
                            "tool_call_id": upstream.get("id", ""),
                            "tool": upstream.get("tool", ""),
                            "arguments": upstream.get("args", {}),
                        },
                    )
                elif event_type == "tool_result":
                    yield builder.create(
                        RunEventType.TOOL_COMPLETED,
                        task_id=task_id,
                        parent_task_id=None,
                        data={
                            **common_data(),
                            "tool_call_id": upstream.get("id", ""),
                            "tool": upstream.get("tool", ""),
                            "result": upstream.get("result", ""),
                        },
                    )
                elif event_type == "text":
                    content = str(upstream.get("text") or "")
                    if content:
                        accumulated += content
                        yield builder.create(
                            RunEventType.MESSAGE_DELTA,
                            task_id=task_id,
                            parent_task_id=None,
                            data={**common_data(), "content": content},
                        )
                elif event_type == "approval_required":
                    awaiting_approval = True
                    yield builder.create(
                        RunEventType.APPROVAL_REQUIRED,
                        task_id=task_id,
                        parent_task_id=None,
                        data={
                            **common_data(),
                            "approval": upstream.get("approval", {}),
                        },
                    )
                elif event_type == "status":
                    state = upstream.get("state", "")
                    if _is_failed_state(state):
                        yield failed(
                            _failure_text(upstream), state=state
                        )
                        return
                    if upstream.get("final"):
                        if _normalized_state(state) != "completed":
                            yield failed(
                                "upstream final status was not completed",
                                state=state,
                            )
                            return
                        if accumulated:
                            yield builder.create(
                                RunEventType.MESSAGE_COMPLETED,
                                task_id=task_id,
                                parent_task_id=None,
                                data={
                                    **common_data(),
                                    "content": accumulated,
                                },
                            )
                        yield builder.create(
                            RunEventType.TASK_COMPLETED,
                            task_id=task_id,
                            parent_task_id=None,
                            data=common_data(),
                        )
                        return
                    yield builder.create(
                        RunEventType.TASK_STATUS_CHANGED,
                        task_id=task_id,
                        parent_task_id=None,
                        data={**common_data(), "state": state},
                    )
                elif event_type == "error":
                    yield failed(_failure_text(upstream))
                    return
                elif event_type == "done":
                    content = str(upstream.get("text") or accumulated)
                    if content:
                        yield builder.create(
                            RunEventType.MESSAGE_COMPLETED,
                            task_id=task_id,
                            parent_task_id=None,
                            data={**common_data(), "content": content},
                        )
                    if awaiting_approval:
                        yield builder.create(
                            RunEventType.TASK_STATUS_CHANGED,
                            task_id=task_id,
                            parent_task_id=None,
                            data={
                                **common_data(),
                                "state": "approval_required",
                            },
                        )
                    else:
                        yield builder.create(
                            RunEventType.TASK_COMPLETED,
                            task_id=task_id,
                            parent_task_id=None,
                            data=common_data(),
                        )
                    return
                elif not event_type:
                    state = _normalized_state(upstream.get("state"))
                    content = str(upstream.get("text") or "")
                    if content:
                        yield builder.create(
                            RunEventType.MESSAGE_COMPLETED,
                            task_id=task_id,
                            parent_task_id=None,
                            data={**common_data(), "content": content},
                        )
                    if _is_failed_state(state):
                        yield failed(
                            _failure_text(upstream),
                            state=upstream.get("state"),
                        )
                        return
                    if state == "input-required":
                        approval = upstream.get("approval")
                        if not approval:
                            yield failed(
                                "input-required result omitted approval"
                            )
                            return
                        yield builder.create(
                            RunEventType.APPROVAL_REQUIRED,
                            task_id=task_id,
                            parent_task_id=None,
                            data={
                                **common_data(),
                                "approval": approval,
                            },
                        )
                        yield builder.create(
                            RunEventType.TASK_STATUS_CHANGED,
                            task_id=task_id,
                            parent_task_id=None,
                            data={
                                **common_data(),
                                "state": "approval_required",
                            },
                        )
                        return
                    if state == "completed":
                        yield builder.create(
                            RunEventType.TASK_COMPLETED,
                            task_id=task_id,
                            parent_task_id=None,
                            data=common_data(),
                        )
                        return
                    yield failed(
                        "gateway result omitted a valid terminal state"
                    )
                    return
                # Unknown typed events are benign extensions. They do not
                # count as terminal and cannot turn exhaustion into success.
        except Exception as exc:
            yield failed(public_error_message(exc))
            return

        yield failed("upstream stream ended without a terminal event")


@dataclass
class _Delegation:
    task_id: str
    agent_id: str
    tool_call_id: str = ""
    buffered_tool_call: Mapping[str, Any] | None = None
    announced: bool = False
    routed: bool = False
    terminal: bool = False
    awaiting_approval: bool = False
    output: str = ""


class AutoExecutionStrategy(_RunBoundStrategy):
    """Normalize the existing LangGraph Host stream into Run events."""

    def __init__(
        self,
        host_manager,
        *,
        run_id: str,
        conversation_id: str,
        root_task_id: str,
        sequence_start: int = 1,
    ):
        super().__init__(
            run_id=run_id,
            conversation_id=conversation_id,
            root_task_id=root_task_id,
            sequence_start=sequence_start,
        )
        self._host_manager = host_manager

    async def execute(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        if command.mode != "auto":
            raise ValueError("AutoExecutionStrategy requires auto mode")
        self._begin_execution()

        builder = _EventBuilder(self._context)
        root_task_id = self._context.root_task_id
        child_number = 0
        by_call_id: dict[str, _Delegation] = {}
        by_task_id: dict[str, _Delegation] = {}
        by_logical_id: dict[str, _Delegation] = {}
        by_agent: defaultdict[str, list[_Delegation]] = defaultdict(list)
        accumulated = ""
        awaiting_approval = False

        def new_delegation(
            agent_id: str,
            *,
            tool_call_id: str = "",
            tool_call: Mapping[str, Any] | None = None,
            logical_task_id: str = "",
        ) -> _Delegation:
            nonlocal child_number
            child_number += 1
            delegation = _Delegation(
                task_id=(
                    f"{root_task_id}:plan:{logical_task_id}"
                    if logical_task_id
                    else f"{root_task_id}:delegation:{child_number}"
                ),
                agent_id=agent_id,
                tool_call_id=tool_call_id,
                buffered_tool_call=tool_call,
            )
            by_agent[agent_id].append(delegation)
            by_task_id[delegation.task_id] = delegation
            if logical_task_id:
                by_logical_id[logical_task_id] = delegation
            if tool_call_id:
                by_call_id[tool_call_id] = delegation
            return delegation

        def unrouted_for_agent(agent_id: str) -> _Delegation | None:
            return next(
                (
                    candidate
                    for candidate in by_agent.get(agent_id, [])
                    if not candidate.routed
                ),
                None,
            )

        def announce(
            delegation: _Delegation,
            upstream: Mapping[str, Any],
        ) -> list[RunEvent]:
            if delegation.announced:
                return []
            delegation.announced = True
            events = [
                builder.create(
                    RunEventType.TASK_DELEGATED,
                    task_id=delegation.task_id,
                    parent_task_id=root_task_id,
                    data={
                        "agent_id": delegation.agent_id,
                        "agent_name": upstream.get(
                            "agent", delegation.agent_id
                        ),
                        **(
                            {
                                "host_tool_call_id":
                                    delegation.tool_call_id
                            }
                            if delegation.tool_call_id
                            else {}
                        ),
                    },
                )
            ]
            if delegation.buffered_tool_call is not None:
                tool_call = delegation.buffered_tool_call
                events.append(
                    builder.create(
                        RunEventType.TOOL_CALLED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": delegation.agent_id,
                            "tool_call_id": delegation.tool_call_id,
                            "tool": tool_call.get("tool", ""),
                            "arguments": tool_call.get("args", {}),
                        },
                    )
                )
                delegation.buffered_tool_call = None
            return events

        def active_delegations() -> list[_Delegation]:
            return [
                item
                for items in by_agent.values()
                for item in items
                if item.announced and not item.terminal
            ]

        def resolve_approval_delegation(
            upstream: Mapping[str, Any],
            approval: Mapping[str, Any],
        ) -> _Delegation:
            agent_id = str(upstream.get("agent_id") or "")
            tool_call_id = str(
                upstream.get("id")
                or upstream.get("tool_call_id")
                or approval.get("tool_call_id")
                or ""
            )
            task_id = str(
                upstream.get("task_id")
                or upstream.get("delegated_task_id")
                or approval.get("task_id")
                or approval.get("delegated_task_id")
                or ""
            )

            explicit_matches: list[_Delegation] = []
            if tool_call_id:
                match = by_call_id.get(tool_call_id)
                if match is None:
                    raise _UpstreamProtocolError(
                        "approval references an unknown tool call"
                    )
                explicit_matches.append(match)
            if task_id:
                match = by_task_id.get(task_id) or by_logical_id.get(task_id)
                if match is None:
                    raise _UpstreamProtocolError(
                        "approval references an unknown delegated task"
                    )
                explicit_matches.append(match)
            if explicit_matches:
                delegation = explicit_matches[0]
                if any(
                    match is not delegation
                    for match in explicit_matches[1:]
                ):
                    raise _UpstreamProtocolError(
                        "approval metadata identifies different tasks"
                    )
                candidates = [delegation]
            else:
                candidates = [
                    item
                    for items in by_agent.values()
                    for item in items
                    if not item.terminal
                    and not item.awaiting_approval
                    and (not agent_id or item.agent_id == agent_id)
                ]

            if len(candidates) != 1:
                raise _UpstreamProtocolError(
                    "approval could not be linked to one active delegation"
                )
            delegation = candidates[0]
            if delegation.terminal or delegation.awaiting_approval:
                raise _UpstreamProtocolError(
                    "approval references an inactive delegation"
                )
            if agent_id and delegation.agent_id != agent_id:
                raise _UpstreamProtocolError(
                    "approval agent does not match its delegation"
                )
            return delegation

        def failure_events(error: str) -> list[RunEvent]:
            events = []
            for delegation in active_delegations():
                delegation.terminal = True
                events.append(
                    builder.create(
                        RunEventType.TASK_FAILED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": delegation.agent_id,
                            "error": error,
                        },
                    )
                )
            events.append(
                builder.create(
                    RunEventType.TASK_FAILED,
                    task_id=root_task_id,
                    parent_task_id=None,
                    data={"error": error},
                )
            )
            return events

        def register_structured_tasks(
            items: object,
        ) -> list[dict[str, Any]]:
            normalized = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, Mapping):
                    continue
                logical_id = str(item.get("id") or "")
                agent_id = str(item.get("agent_id") or "")
                if logical_id and logical_id not in by_logical_id:
                    delegation = new_delegation(
                        agent_id,
                        logical_task_id=logical_id,
                    )
                    if item.get("checkpoint_state") in {
                        "completed", "failed"
                    }:
                        delegation.terminal = True
                normalized.append({
                    **dict(item),
                    "logical_id": logical_id,
                    "logical_depends_on": list(item.get("depends_on", [])),
                    "id": f"{root_task_id}:plan:{logical_id}",
                    "depends_on": [
                        f"{root_task_id}:plan:{dependency}"
                        for dependency in item.get("depends_on", [])
                    ],
                })
            return normalized

        yield builder.create(
            RunEventType.HOST_PLANNING,
            task_id=root_task_id,
            parent_task_id=None,
            data={"message": command.message},
        )

        try:
            stream = self._host_manager.process_message_stream(
                command.message,
                self._context.run_id,
            )
            async for raw_upstream in stream:
                upstream = _require_mapping(raw_upstream)
                event_type = str(upstream.get("type") or "")

                if event_type == "tool_call":
                    tool_call_id = str(upstream.get("id") or "")
                    tool = str(upstream.get("tool") or "")
                    arguments = upstream.get("args", {})
                    if tool == "send_task":
                        agent_id = str(
                            arguments.get("agent_id", "")
                            if isinstance(arguments, Mapping)
                            else ""
                        )
                        if not tool_call_id or not agent_id:
                            raise _UpstreamProtocolError(
                                "send_task call omitted its ID or agent"
                            )
                        if tool_call_id in by_call_id:
                            raise _UpstreamProtocolError(
                                "duplicate send_task tool-call ID"
                            )
                        new_delegation(
                            agent_id,
                            tool_call_id=tool_call_id,
                            tool_call=upstream,
                        )
                    else:
                        logical_task_id = str(upstream.get("task_id") or "")
                        delegation = by_logical_id.get(logical_task_id)
                        yield builder.create(
                            RunEventType.TOOL_CALLED,
                            task_id=(delegation.task_id if delegation else root_task_id),
                            parent_task_id=(root_task_id if delegation else None),
                            data={
                                **({"agent_id": delegation.agent_id} if delegation else {}),
                                "tool_call_id": tool_call_id,
                                "tool": tool,
                                "arguments": arguments,
                            },
                        )
                elif event_type == "routing":
                    agent_id = str(upstream.get("agent_id") or "")
                    if not agent_id:
                        raise _UpstreamProtocolError(
                            "routing event omitted agent_id"
                        )
                    logical_task_id = str(upstream.get("task_id") or "")
                    delegation = by_logical_id.get(logical_task_id)
                    if delegation is None:
                        delegation = unrouted_for_agent(agent_id)
                    if delegation is None:
                        delegation = new_delegation(
                            agent_id, logical_task_id=logical_task_id
                        )
                    delegation.routed = True
                    for event in announce(delegation, upstream):
                        yield event
                elif event_type == "tool_result":
                    tool_call_id = str(upstream.get("id") or "")
                    delegation = by_call_id.get(tool_call_id)
                    if delegation is not None:
                        if not delegation.routed:
                            raise _UpstreamProtocolError(
                                "send_task result arrived before routing"
                            )
                        yield builder.create(
                            RunEventType.TOOL_COMPLETED,
                            task_id=delegation.task_id,
                            parent_task_id=root_task_id,
                            data={
                                "agent_id": delegation.agent_id,
                                "tool_call_id": tool_call_id,
                                "tool": upstream.get("tool", ""),
                                "result": upstream.get("result", ""),
                            },
                        )
                        if delegation.awaiting_approval:
                            yield builder.create(
                                RunEventType.TASK_STATUS_CHANGED,
                                task_id=delegation.task_id,
                                parent_task_id=root_task_id,
                                data={
                                    "agent_id": delegation.agent_id,
                                    "state": "approval_required",
                                },
                            )
                        else:
                            delegation.terminal = True
                            yield builder.create(
                                RunEventType.TASK_COMPLETED,
                                task_id=delegation.task_id,
                                parent_task_id=root_task_id,
                                data={"agent_id": delegation.agent_id},
                            )
                    elif upstream.get("tool") == "send_task":
                        raise _UpstreamProtocolError(
                            "send_task result has no matching call"
                        )
                    else:
                        logical_task_id = str(upstream.get("task_id") or "")
                        logical_delegation = by_logical_id.get(logical_task_id)
                        yield builder.create(
                            RunEventType.TOOL_COMPLETED,
                            task_id=(logical_delegation.task_id if logical_delegation else root_task_id),
                            parent_task_id=(root_task_id if logical_delegation else None),
                            data={
                                **({"agent_id": logical_delegation.agent_id} if logical_delegation else {}),
                                "tool_call_id": tool_call_id,
                                "tool": upstream.get("tool", ""),
                                "result": upstream.get("result", ""),
                            },
                        )
                elif event_type == "round_started":
                    yield builder.create(
                        RunEventType.HOST_ROUND_STARTED,
                        task_id=root_task_id,
                        parent_task_id=None,
                        data={
                            "round": upstream.get("round"),
                            "checkpoint": upstream.get("checkpoint"),
                        },
                    )
                elif event_type == "decision_created":
                    decision_tasks = register_structured_tasks(
                        upstream.get("tasks", [])
                    )
                    yield builder.create(
                        RunEventType.HOST_DECISION_CREATED,
                        task_id=root_task_id,
                        parent_task_id=None,
                        data={
                            "round": upstream.get("round"),
                            "action": upstream.get("action", ""),
                            "reason": upstream.get("reason", ""),
                            "tasks": decision_tasks,
                            "checkpoint": upstream.get("checkpoint"),
                        },
                    )
                elif event_type == "round_completed":
                    yield builder.create(
                        RunEventType.HOST_ROUND_COMPLETED,
                        task_id=root_task_id,
                        parent_task_id=None,
                        data={
                            "round": upstream.get("round"),
                            "task_ids": upstream.get("task_ids", []),
                            "checkpoint": upstream.get("checkpoint"),
                        },
                    )
                elif event_type == "plan_created":
                    plan_tasks = register_structured_tasks(
                        upstream.get("tasks", [])
                    )
                    yield builder.create(
                        RunEventType.HOST_PLAN_CREATED,
                        task_id=root_task_id,
                        parent_task_id=None,
                        data={
                            "summary": upstream.get("summary", ""),
                            "tasks": plan_tasks,
                        },
                    )
                elif event_type == "context_prepared":
                    logical_task_id = str(upstream.get("task_id") or "")
                    agent_id = str(upstream.get("agent_id") or "")
                    delegation = by_logical_id.get(logical_task_id)
                    if delegation is None:
                        delegation = new_delegation(
                            agent_id, logical_task_id=logical_task_id
                        )
                    yield builder.create(
                        RunEventType.TASK_CONTEXT_PREPARED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": agent_id,
                            "depends_on": upstream.get("depends_on", []),
                        },
                    )
                elif event_type == "task_started":
                    delegation = by_logical_id.get(
                        str(upstream.get("task_id") or "")
                    )
                    if delegation is None:
                        raise _UpstreamProtocolError(
                            "task_started references an unknown plan task"
                        )
                    yield builder.create(
                        RunEventType.TASK_STARTED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={"agent_id": delegation.agent_id},
                    )
                elif event_type == "task_retry_scheduled":
                    delegation = by_logical_id.get(
                        str(upstream.get("task_id") or "")
                    )
                    if delegation is None:
                        raise _UpstreamProtocolError(
                            "retry references an unknown plan task"
                        )
                    yield builder.create(
                        RunEventType.TASK_RETRY_SCHEDULED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": delegation.agent_id,
                            "attempt": upstream.get("attempt"),
                            "reason": upstream.get("reason", ""),
                        },
                    )
                elif event_type == "plan_revised":
                    delegation = by_logical_id.get(
                        str(upstream.get("task_id") or "")
                    )
                    if delegation is None:
                        raise _UpstreamProtocolError(
                            "plan revision references an unknown task"
                        )
                    replacement = str(
                        upstream.get("replacement_agent_id") or ""
                    )
                    delegation.agent_id = replacement or delegation.agent_id
                    yield builder.create(
                        RunEventType.HOST_PLAN_REVISED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": delegation.agent_id,
                            "replacement_agent_id": replacement,
                            "reason": upstream.get("reason", ""),
                        },
                    )
                elif event_type == "task_evaluated":
                    delegation = by_logical_id.get(
                        str(upstream.get("task_id") or "")
                    )
                    if delegation is None:
                        raise _UpstreamProtocolError(
                            "evaluation references an unknown plan task"
                        )
                    yield builder.create(
                        RunEventType.TASK_EVALUATED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": upstream.get(
                                "agent_id", delegation.agent_id
                            ),
                            "outcome": upstream.get("outcome", ""),
                            "reason": upstream.get("reason", ""),
                        },
                    )
                elif event_type in {"task_completed", "task_failed", "task_blocked"}:
                    delegation = by_logical_id.get(
                        str(upstream.get("task_id") or "")
                    )
                    if delegation is None:
                        raise _UpstreamProtocolError(
                            "terminal event references an unknown plan task"
                        )
                    delegation.terminal = True
                    normalized_type = {
                        "task_completed": RunEventType.TASK_COMPLETED,
                        "task_failed": RunEventType.TASK_FAILED,
                        "task_blocked": RunEventType.TASK_BLOCKED,
                    }[event_type]
                    result_text = str(
                        upstream.get("result") or delegation.output or ""
                    )
                    if result_text:
                        yield builder.create(
                            RunEventType.MESSAGE_COMPLETED,
                            task_id=delegation.task_id,
                            parent_task_id=root_task_id,
                            data={
                                "agent_id": delegation.agent_id,
                                "content": result_text,
                            },
                        )
                    yield builder.create(
                        normalized_type,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": upstream.get(
                                "agent_id", delegation.agent_id
                            ),
                            "result": upstream.get("result", ""),
                            "error": upstream.get("error", ""),
                            "reason": upstream.get("reason", ""),
                            "delegation_result": upstream.get(
                                "delegation_result"
                            ),
                            "evaluation": upstream.get("evaluation"),
                        },
                    )
                elif event_type == "synthesis_started":
                    yield builder.create(
                        RunEventType.HOST_SYNTHESIS_STARTED,
                        task_id=root_task_id,
                        parent_task_id=None,
                        data={},
                    )
                elif event_type == "approval_required":
                    approval = upstream.get("approval")
                    if not isinstance(approval, Mapping):
                        raise _UpstreamProtocolError(
                            "approval event omitted approval data"
                        )
                    awaiting_approval = True
                    delegation = resolve_approval_delegation(
                        upstream, approval
                    )
                    delegation.awaiting_approval = True
                    for event in announce(delegation, upstream):
                        yield event
                    yield builder.create(
                        RunEventType.APPROVAL_REQUIRED,
                        task_id=delegation.task_id,
                        parent_task_id=root_task_id,
                        data={
                            "agent_id": delegation.agent_id,
                            "approval": dict(approval),
                            "delegation_result": upstream.get(
                                "delegation_result"
                            ),
                            "evaluation": upstream.get("evaluation"),
                        },
                    )
                elif event_type == "text":
                    content = str(upstream.get("text") or "")
                    if content:
                        logical_task_id = str(
                            upstream.get("task_id") or ""
                        )
                        delegation = by_logical_id.get(logical_task_id)
                        if delegation is not None:
                            delegation.output += content
                            yield builder.create(
                                RunEventType.MESSAGE_DELTA,
                                task_id=delegation.task_id,
                                parent_task_id=root_task_id,
                                data={
                                    "agent_id": delegation.agent_id,
                                    "content": content,
                                },
                            )
                        else:
                            accumulated += content
                            yield builder.create(
                                RunEventType.MESSAGE_DELTA,
                                task_id=root_task_id,
                                parent_task_id=None,
                                data={"content": content},
                            )
                elif event_type == "error":
                    for event in failure_events(
                        _failure_text(upstream)
                    ):
                        yield event
                    return
                elif event_type == "done":
                    if any(
                        not item.routed and not item.terminal
                        for items in by_agent.values()
                        for item in items
                    ):
                        raise _UpstreamProtocolError(
                            "Host finished before routing send_task"
                        )
                    incomplete = [
                        item
                        for item in active_delegations()
                        if not item.awaiting_approval
                    ]
                    if incomplete:
                        raise _UpstreamProtocolError(
                            "Host finished before delegated task result"
                        )
                    if accumulated:
                        yield builder.create(
                            RunEventType.MESSAGE_COMPLETED,
                            task_id=root_task_id,
                            parent_task_id=None,
                            data={"content": accumulated},
                        )
                    if awaiting_approval:
                        yield builder.create(
                            RunEventType.TASK_STATUS_CHANGED,
                            task_id=root_task_id,
                            parent_task_id=None,
                            data={"state": "approval_required"},
                        )
                    else:
                        yield builder.create(
                            RunEventType.TASK_COMPLETED,
                            task_id=root_task_id,
                            parent_task_id=None,
                            data={},
                        )
                    return
                # Unknown typed events are benign extensions. They do not
                # count as terminal and cannot turn exhaustion into success.
        except Exception as exc:
            for event in failure_events(
                public_error_message(exc)
            ):
                yield event
            return

        for event in failure_events(
            "upstream stream ended without a terminal event"
        ):
            yield event
