"""Application service for durable unified Agent runs."""

from __future__ import annotations

import uuid
import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEvent, RunEventType
from backend.orchestration.strategies import (
    AutoExecutionStrategy,
    DirectExecutionStrategy,
)
from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostPlan,
    HostRunState,
)


_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
_CONVERSATION_CONTEXT_MESSAGES = 12
_CONVERSATION_CONTEXT_CHARS = 12000


class RunService:
    """Own Run identity, persistence, lifecycle, messages, and replay."""

    def __init__(self, repository, registry, gateway, auto_host):
        self.repository = repository
        self.registry = registry
        self.gateway = gateway
        self.auto_host = auto_host
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._event_conditions: dict[str, asyncio.Condition] = {}
        self._event_generations: dict[str, int] = {}

    def _persist_event(self, event: RunEvent) -> RunEvent:
        persisted = self.repository.append_run_event(event)
        self._event_generations[persisted.run_id] = self._event_generations.get(persisted.run_id, 0) + 1
        condition = self._event_conditions.get(persisted.run_id)
        if condition is not None:
            async def notify():
                async with condition:
                    condition.notify_all()
            asyncio.get_running_loop().create_task(notify())
        return persisted

    async def wait_for_events(self, run_id: str, generation: int, timeout: float = 1.0) -> int:
        """Wait briefly for an event notification, then recheck durable storage.

        Notifications are only an optimization: approval execution can race with a
        reconnecting SSE subscriber, so the short timeout bounds how long already
        persisted events can remain invisible in the browser.
        """
        current = self._event_generations.get(run_id, 0)
        if current != generation:
            return current
        condition = self._event_conditions.setdefault(run_id, asyncio.Condition())
        async with condition:
            try:
                await asyncio.wait_for(condition.wait_for(lambda: self._event_generations.get(run_id, 0) != generation), timeout)
            except TimeoutError:
                pass
        return self._event_generations.get(run_id, 0)

    async def stream(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        run_id: str | None = None
        current = asyncio.current_task()
        try:
            async for event in self._stream(command):
                if run_id is None:
                    run_id = event.run_id
                    if current is not None:
                        self._active_tasks[run_id] = current
                yield event
        finally:
            if run_id is not None:
                run = self.repository.get_run(run_id)
                if run is not None and run["status"] == "running":
                    self.cancel(run_id)
            if run_id is not None and self._active_tasks.get(run_id) is current:
                self._active_tasks.pop(run_id, None)

    async def _stream(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        conversation_id = self._conversation_id(command)
        execution_message = self._conversation_context_message(
            conversation_id, command.message
        )
        continuation_state = self._conversation_host_state(
            conversation_id, command.mode
        )
        run_id = uuid.uuid4().hex
        root_task_id = f"{run_id}:root"
        root_agent_id = (
            command.target_agent_id if command.mode == "direct" else "host"
        )

        self.repository.create_run(
            run_id,
            conversation_id,
            "running",
            {
                "mode": command.mode,
                "target_agent_id": command.target_agent_id,
                "root_task_id": root_task_id,
                "title": command.message[:80],
                "request": command.message,
            },
        )
        self.repository.create_task(
            {
                "id": root_task_id,
                "run_id": run_id,
                "parent_task_id": None,
                "agent_id": root_agent_id,
                "status": "working",
            }
        )
        self._add_message(
            conversation_id=conversation_id,
            role="user",
            content=command.message,
            task_id=root_task_id,
            metadata={"run_id": run_id, "mode": command.mode},
        )

        started = self._event(
            RunEventType.RUN_STARTED,
            run_id=run_id,
            conversation_id=conversation_id,
            sequence=1,
            data={
                "mode": command.mode,
                "target_agent_id": command.target_agent_id,
            },
        )
        yield self._persist_event(started)

        if self._is_cancelled(run_id):
            return
        strategy = self._strategy(
            command,
            run_id=run_id,
            conversation_id=conversation_id,
            root_task_id=root_task_id,
            sequence_start=2,
            host_state=continuation_state,
        )
        partial_output = ""
        assistant_saved = False
        saved_child_messages: set[str] = set()
        failure: RunEvent | None = None
        awaiting_approval = False

        execution_command = command.model_copy(
            update={"message": execution_message}
        )
        async for candidate in strategy.execute(execution_command):
            if self._is_cancelled(run_id):
                return
            event = self._persist_event(candidate)
            self._apply_checkpoint_event(event)
            self._apply_task_event(event)

            if event.type == RunEventType.MESSAGE_DELTA:
                if event.parent_task_id is None:
                    partial_output += str(event.data.get("content") or "")
            elif event.type == RunEventType.MESSAGE_COMPLETED:
                content = str(event.data.get("content") or partial_output)
                if (
                    event.parent_task_id is not None
                    and event.task_id is not None
                    and content
                    and event.task_id not in saved_child_messages
                ):
                    self._add_assistant_message(
                        event,
                        content,
                        command.mode,
                        source="delegated-agent",
                    )
                    saved_child_messages.add(event.task_id)
                elif content and not assistant_saved:
                    self._add_assistant_message(
                        event,
                        content,
                        command.mode,
                    )
                    assistant_saved = True
            elif event.type == RunEventType.TASK_FAILED:
                failure = event
            elif (
                event.type == RunEventType.TASK_STATUS_CHANGED
                and event.data.get("state") == "approval_required"
            ):
                awaiting_approval = True
            elif event.type == RunEventType.APPROVAL_REQUIRED:
                awaiting_approval = True

            yield event

        if self._is_cancelled(run_id):
            return
        next_sequence = (
            self.repository.list_run_events(run_id)[-1].sequence + 1
        )
        if failure is not None:
            if partial_output and not assistant_saved:
                self._add_assistant_message(
                    failure,
                    partial_output,
                    command.mode,
                    partial=True,
                )
            self.repository.update_run_status(run_id, "failed")
            self.repository.update_task(
                root_task_id, {"status": "failed"}
            )
            terminal = self._event(
                RunEventType.RUN_FAILED,
                run_id=run_id,
                conversation_id=conversation_id,
                sequence=next_sequence,
                data={"error": str(failure.data.get("error") or "Run failed")},
                task_id=root_task_id,
            )
            yield self._persist_event(terminal)
            return

        if awaiting_approval:
            self.repository.update_run_status(run_id, "approval_required")
            self.repository.update_task(
                root_task_id, {"status": "approval_required"}
            )
            return

        self.repository.update_run_status(run_id, "completed")
        self.repository.update_task(root_task_id, {"status": "completed"})
        terminal = self._event(
            RunEventType.RUN_COMPLETED,
            run_id=run_id,
            conversation_id=conversation_id,
            sequence=next_sequence,
            data={},
            task_id=root_task_id,
        )
        yield self._persist_event(terminal)

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self.repository.get_run(run_id)
        if run is None:
            return None
        return {
            **run,
            "tasks": self.repository.list_tasks(run_id),
            "approvals": self.repository.list_approvals(run_id),
        }

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        return self.repository.list_runs(limit=limit, offset=offset)

    async def resume_after_approval(
        self, approval: dict[str, Any], execution: dict[str, Any]
    ) -> list[RunEvent]:
        run_id = approval["run_id"]
        lock = self._event_conditions.setdefault(run_id, asyncio.Condition())
        async with lock:
            run = self.repository.get_run(run_id)
            if run is None or run.get("mode") != "auto":
                return []

            tasks = self.repository.list_tasks(run_id)
            paused = next(
                (
                    task
                    for task in tasks
                    if task.get("status") == "approval_required"
                    and task.get("agent_id") == approval["agent_id"]
                ),
                None,
            )
            if paused is None:
                return []

            execution_state = str(execution.get("state") or "").lower()
            if execution_state == "input-required" and execution.get("approval"):
                return self._record_followup_approval(
                    run, paused, approval, execution["approval"]
                )
            if execution_state not in {"completed", "failed", "error"}:
                return []

            decision = approval.get("status", "")
            completed = (
                decision == "approved"
                and execution.get("state") not in {"failed", "error"}
            )
            execution_failed = (
                decision == "approved" and not completed
            )
            result = DelegationResult(
                state="completed" if completed else "failed",
                text=str(execution.get("text") or ""),
                output=execution.get("specialist_output"),
                error="" if completed else str(
                    execution.get("error")
                    or execution.get("text")
                    or "approval rejected"
                ),
            )
            self.repository.update_task_data(
                paused["id"],
                {
                    "status": (
                        "completed" if completed
                        else "failed" if execution_failed
                        else "blocked"
                    ),
                    "delegation_result": result.model_dump(),
                },
            )

            persisted = self.repository.list_run_events(run_id)
            sequence = persisted[-1].sequence + 1 if persisted else 1
            emitted: list[RunEvent] = []

            def persist(event: RunEvent) -> None:
                nonlocal sequence
                saved = self._persist_event(event)
                self._apply_checkpoint_event(saved)
                self._apply_task_event(saved)
                emitted.append(saved)
                sequence = saved.sequence + 1

            persist(RunEvent.create(
                event_type=RunEventType.APPROVAL_DECIDED,
                run_id=run_id,
                conversation_id=run["conversation_id"],
                sequence=sequence,
                task_id=paused["id"],
                parent_task_id=paused.get("parent_task_id"),
                data={
                    "agent_id": approval["agent_id"],
                    "approval_id": approval["id"],
                    "decision": decision,
                },
            ))
            completed_call_ids = {
                str(event.data.get("tool_call_id") or event.data.get("id") or "")
                for event in persisted
                if event.type == RunEventType.TOOL_COMPLETED
            }
            tool_call = next((
                event for event in reversed(persisted)
                if event.type == RunEventType.TOOL_CALLED
                and event.task_id == paused["id"]
                and str(event.data.get("tool_call_id") or event.data.get("id") or "")
                not in completed_call_ids
                and (event.data.get("tool") or event.data.get("tool_name"))
                == approval.get("tool_name")
                and (event.data.get("arguments") or event.data.get("args") or {})
                == approval.get("arguments", {})
            ), None)
            if tool_call is not None:
                tool_result = {
                    "agent_id": approval["agent_id"],
                    "tool_call_id": str(
                        tool_call.data.get("tool_call_id")
                        or tool_call.data.get("id") or ""
                    ),
                    "tool": approval.get("tool_name", ""),
                }
                if completed:
                    tool_result["result"] = result.text
                else:
                    tool_result["error"] = result.error
                persist(RunEvent.create(
                    event_type=RunEventType.TOOL_COMPLETED,
                    run_id=run_id,
                    conversation_id=run["conversation_id"],
                    sequence=sequence,
                    task_id=paused["id"],
                    parent_task_id=paused.get("parent_task_id"),
                    data=tool_result,
                ))
            if result.text:
                message_event = RunEvent.create(
                    event_type=RunEventType.MESSAGE_COMPLETED,
                    run_id=run_id,
                    conversation_id=run["conversation_id"],
                    sequence=sequence,
                    task_id=paused["id"],
                    parent_task_id=paused.get("parent_task_id"),
                    data={
                        "agent_id": approval["agent_id"],
                        "content": result.text,
                    },
                )
                persist(message_event)
                self._add_assistant_message(
                    message_event,
                    result.text,
                    "auto",
                    source="delegated-agent",
                )
            persist(RunEvent.create(
                event_type=(
                    RunEventType.TASK_COMPLETED
                    if completed
                    else (
                        RunEventType.TASK_FAILED
                        if execution_failed
                        else RunEventType.TASK_BLOCKED
                    )
                ),
                run_id=run_id,
                conversation_id=run["conversation_id"],
                sequence=sequence,
                task_id=paused["id"],
                parent_task_id=paused.get("parent_task_id"),
                data={
                    "agent_id": approval["agent_id"],
                    "result": result.text,
                    "reason": result.error,
                    "delegation_result": result.model_dump(),
                },
            ))

            if execution_failed:
                self.repository.update_run_status(run_id, "failed")
                self.repository.update_task(
                    run["root_task_id"], {"status": "failed"}
                )
                persist(RunEvent.create(
                    event_type=RunEventType.RUN_FAILED,
                    run_id=run_id,
                    conversation_id=run["conversation_id"],
                    sequence=sequence,
                    task_id=run["root_task_id"],
                    parent_task_id=None,
                    data={"error": result.error},
                ))
                return emitted

            checkpoint = self._host_checkpoint(run_id)
            self.repository.update_run_status(run_id, "running")

            class ResumeManager:
                def __init__(self, host, state):
                    self.host = host
                    self.state = state

                async def process_message_stream(self, text, session_id):
                    arguments = (
                        {"state": self.state["state"]}
                        if "state" in self.state
                        else {
                            "plan": self.state["plan"],
                            "results": self.state["results"],
                            "successful": self.state["successful"],
                        }
                    )
                    async for item in self.host.resume_message_stream(
                        text, session_id, **arguments
                    ):
                        yield item

            strategy = AutoExecutionStrategy(
                ResumeManager(self.auto_host, checkpoint),
                run_id=run_id,
                conversation_id=run["conversation_id"],
                root_task_id=run["root_task_id"],
                sequence_start=sequence,
            )
            root_output = ""
            failed = False
            awaiting_approval = False
            async for candidate in strategy.execute(RunCommand(
                mode="auto",
                conversation_id=run["conversation_id"],
                message=str(run.get("request") or run.get("title") or ""),
            )):
                persist(candidate)
                if (
                    candidate.type == RunEventType.MESSAGE_COMPLETED
                    and candidate.parent_task_id is None
                ):
                    root_output = str(candidate.data.get("content") or "")
                elif candidate.type == RunEventType.TASK_FAILED:
                    failed = True
                elif candidate.type == RunEventType.APPROVAL_REQUIRED:
                    awaiting_approval = True

            if root_output:
                root_event = emitted[-1]
                self._add_assistant_message(
                    root_event, root_output, "auto"
                )
            final_status = (
                "approval_required"
                if awaiting_approval
                else "failed"
                if failed
                else "completed"
            )
            self.repository.update_run_status(run_id, final_status)
            if final_status in {"completed", "failed"}:
                persist(RunEvent.create(
                    event_type=(
                        RunEventType.RUN_COMPLETED
                        if final_status == "completed"
                        else RunEventType.RUN_FAILED
                    ),
                    run_id=run_id,
                    conversation_id=run["conversation_id"],
                    sequence=sequence,
                    task_id=run["root_task_id"],
                    data={},
                ))
            return emitted

    def _record_followup_approval(
        self,
        run: dict[str, Any],
        paused: dict[str, Any],
        approval: dict[str, Any],
        followup: dict[str, Any],
    ) -> list[RunEvent]:
        """Close one approved call and expose the next call in its batch."""
        run_id = run["id"]
        persisted = self.repository.list_run_events(run_id)
        sequence = persisted[-1].sequence + 1 if persisted else 1
        emitted: list[RunEvent] = []

        def persist(event_type: RunEventType, data: dict[str, Any]) -> None:
            nonlocal sequence
            saved = self._persist_event(RunEvent.create(
                event_type=event_type,
                run_id=run_id,
                conversation_id=run["conversation_id"],
                sequence=sequence,
                task_id=paused["id"],
                parent_task_id=paused.get("parent_task_id"),
                data={"agent_id": approval["agent_id"], **data},
            ))
            self._apply_checkpoint_event(saved)
            self._apply_task_event(saved)
            emitted.append(saved)
            sequence = saved.sequence + 1

        persist(RunEventType.APPROVAL_DECIDED, {
            "approval_id": approval["id"],
            "decision": approval["status"],
        })
        completed_ids = {
            str(event.data.get("tool_call_id") or event.data.get("id") or "")
            for event in persisted if event.type == RunEventType.TOOL_COMPLETED
        }
        tool_call = next((
            event for event in reversed(persisted)
            if event.type == RunEventType.TOOL_CALLED
            and event.task_id == paused["id"]
            and str(event.data.get("tool_call_id") or event.data.get("id") or "") not in completed_ids
            and (event.data.get("tool") or event.data.get("tool_name")) == approval["tool_name"]
            and (event.data.get("arguments") or event.data.get("args") or {}) == approval["arguments"]
        ), None)
        if tool_call is not None:
            persist(RunEventType.TOOL_COMPLETED, {
                "tool_call_id": str(tool_call.data.get("tool_call_id") or tool_call.data.get("id") or ""),
                "tool": approval["tool_name"],
                "result": "已批准的操作执行完成，等待下一项审批。",
            })
        persist(RunEventType.APPROVAL_REQUIRED, {"approval": followup})
        persist(RunEventType.TASK_STATUS_CHANGED, {"state": "approval_required"})
        self.repository.update_task(paused["id"], {"status": "approval_required"})
        self.repository.update_run_status(run_id, "approval_required")
        return emitted

    def _host_checkpoint(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_run(run_id) or {}
        if run.get("host_state"):
            state = HostRunState.model_validate(run["host_state"])
            pending_id = state.pending_approval_task_id
            if pending_id:
                stored = next(
                    (
                        task
                        for task in self.repository.list_tasks(run_id)
                        if task.get("logical_id") == pending_id
                    ),
                    None,
                )
                raw_result = stored.get("delegation_result") if stored else None
                if raw_result and pending_id in state.observations:
                    result = DelegationResult.model_validate(raw_result)
                    completed = (
                        stored.get("status") == "completed"
                        and result.state == "completed"
                    )
                    observed = state.observations[pending_id]
                    observed.result = result
                    observed.evaluation = Evaluation(
                        outcome="sufficient" if completed else "blocked",
                        reason=(
                            "approved operation completed"
                            if completed
                            else result.error or "approval rejected"
                        ),
                    )
                    if completed:
                        state.successful.add(pending_id)
                    state.pending_approval_task_id = None
            return {"state": state}
        plan_data = run.get("host_plan") or {}
        planned_tasks = []
        for stored in plan_data.get("tasks", []):
            item = dict(stored)
            item["id"] = item.get("logical_id") or item["id"]
            item["depends_on"] = item.get(
                "logical_depends_on", item.get("depends_on", [])
            )
            planned_tasks.append(item)
        plan = HostPlan(
            summary=plan_data.get("summary") or "resumed Host plan",
            tasks=planned_tasks,
        )
        results: dict[str, DelegationResult] = {}
        successful: set[str] = set()
        for task in self.repository.list_tasks(run_id):
            logical_id = task.get("logical_id")
            raw_result = task.get("delegation_result")
            if not logical_id or not raw_result:
                continue
            result = DelegationResult.model_validate(raw_result)
            results[logical_id] = result
            if task.get("status") == "completed" and result.state == "completed":
                successful.add(logical_id)
        return {"plan": plan, "results": results, "successful": successful}

    def events(
        self, run_id: str, after_sequence: int = 0
    ) -> list[RunEvent]:
        return self.repository.list_run_events(run_id, after_sequence)

    def cancel(self, run_id: str) -> dict[str, Any] | None:
        run = self.repository.get_run(run_id)
        if run is None:
            return None
        if run["status"] in _TERMINAL_RUN_STATUSES:
            return run

        self.repository.update_run_status(run_id, "cancelled")
        for task in self.repository.list_tasks(run_id):
            if task["status"] not in _TERMINAL_RUN_STATUSES:
                self.repository.update_task(
                    task["id"], {"status": "cancelled"}
                )
        persisted = self.repository.list_run_events(run_id)
        sequence = persisted[-1].sequence + 1 if persisted else 1
        event = self._event(
            RunEventType.RUN_CANCELLED,
            run_id=run_id,
            conversation_id=run["conversation_id"],
            sequence=sequence,
            data={},
            task_id=run.get("root_task_id"),
        )
        self._persist_event(event)
        active = self._active_tasks.get(run_id)
        current = asyncio.current_task()
        if active is not None and active is not current and not active.done():
            active.cancel()
        return self.repository.get_run(run_id)

    def recover_interrupted_runs(self) -> int:
        recovered = 0
        for run in self.repository.list_runs():
            if run.get("status") not in {"running", "planning", "working", "retrying"}:
                continue
            self.repository.update_run_status(run["id"], "interrupted")
            for task in self.repository.list_tasks(run["id"]):
                if task.get("status") not in _TERMINAL_RUN_STATUSES and task.get("status") != "approval_required":
                    self.repository.update_task(task["id"], {"status": "interrupted"})
            persisted = self.repository.list_run_events(run["id"])
            sequence = persisted[-1].sequence + 1 if persisted else 1
            self._persist_event(self._event(
                RunEventType.RUN_FAILED, run_id=run["id"], conversation_id=run["conversation_id"], sequence=sequence,
                data={"error": "Backend restarted before this run completed", "reason": "backend_restarted"}, task_id=run.get("root_task_id"),
            ))
            recovered += 1
        return recovered

    def save_assistant_message(
        self,
        run_id: str,
        content: str,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        run = self.repository.get_run(run_id)
        if run is None or not content:
            return None
        return self._add_message(
            conversation_id=run["conversation_id"],
            role="agent",
            content=content,
            task_id=task_id,
            metadata={
                "run_id": run_id,
                "source": "unified-run",
                **(metadata or {}),
            },
        )

    def _conversation_id(self, command: RunCommand) -> str:
        if command.conversation_id:
            if self.repository.get_conversation(command.conversation_id) is None:
                raise ValueError("Conversation not found")
            return command.conversation_id

        conversation_id = uuid.uuid4().hex
        self.repository.create_conversation(
            {
                "id": conversation_id,
                "agent_id": (
                    command.target_agent_id
                    if command.mode == "direct"
                    else "multi-host"
                ),
                "title": command.message[:80],
                "type": "single" if command.mode == "direct" else "multi",
                "created_at": self._now(),
                "updated_at": self._now(),
                "message_count": 0,
            }
        )
        return conversation_id

    def _conversation_context_message(
        self, conversation_id: str, current_message: str
    ) -> str:
        messages = sorted(
            (
                message
                for message in self.repository.list_messages(conversation_id)
                if message.get("role") == "user"
                or message.get("metadata", {}).get("source")
                != "delegated-agent"
            ),
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("id") or ""),
            ),
        )[-_CONVERSATION_CONTEXT_MESSAGES:]
        if not messages:
            return current_message

        remaining = _CONVERSATION_CONTEXT_CHARS - len(current_message)
        history: list[str] = []
        for message in reversed(messages):
            metadata = message.get("metadata", {})
            role = (
                "User"
                if message.get("role") == "user"
                else (
                    "Host"
                    if metadata.get("source") == "unified-run"
                    and metadata.get("mode") == "auto"
                    else "Agent"
                )
            )
            content = str(message.get("content") or "").strip()
            line = f"{role}: {content}"
            if len(line) > remaining:
                line = line[:max(0, remaining)]
            if not line:
                break
            history.append(line)
            remaining -= len(line) + 1
            if remaining <= 0:
                break
        history.reverse()
        return (
            "Conversation history (oldest to newest):\n"
            f"{'\n'.join(history)}\n\n"
            "Current user message:\n"
            f"{current_message}"
        )

    def _conversation_host_state(
        self, conversation_id: str, mode: str
    ) -> HostRunState | None:
        if mode != "auto":
            return None
        messages = sorted(
            self.repository.list_messages(conversation_id),
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        for message in messages:
            metadata = message.get("metadata", {})
            if (
                message.get("role") != "agent"
                or metadata.get("source") != "unified-run"
                or metadata.get("mode") != "auto"
            ):
                continue
            run = self.repository.get_run(str(metadata.get("run_id") or ""))
            raw_state = run.get("host_state") if run else None
            if not raw_state:
                return None
            state = HostRunState.model_validate(raw_state)
            if state.decisions and state.decisions[-1].action == "clarify":
                return state
            return None
        return None

    def _is_cancelled(self, run_id: str) -> bool:
        run = self.repository.get_run(run_id)
        return run is not None and run["status"] == "cancelled"

    def _strategy(
        self,
        command: RunCommand,
        *,
        run_id: str,
        conversation_id: str,
        root_task_id: str,
        sequence_start: int,
        host_state: HostRunState | None = None,
    ):
        arguments = {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "root_task_id": root_task_id,
            "sequence_start": sequence_start,
        }
        if command.mode == "direct":
            return DirectExecutionStrategy(
                self.registry,
                self.gateway,
                **arguments,
            )
        if command.mode == "auto":
            self.auto_host.register_agents_from_db(self.registry.list())
            return AutoExecutionStrategy(
                self.auto_host, host_state=host_state, **arguments
            )
        raise ValueError("mode must be direct or auto")

    def _apply_task_event(self, event: RunEvent) -> None:
        if event.task_id is None:
            return
        existing = {
            task["id"]: task
            for task in self.repository.list_tasks(event.run_id)
        }.get(event.task_id)
        agent_id = str(event.data.get("agent_id") or "host")

        if existing is None:
            self.repository.create_task(
                {
                    "id": event.task_id,
                    "run_id": event.run_id,
                    "parent_task_id": event.parent_task_id,
                    "agent_id": agent_id,
                    "status": self._task_status(event),
                }
            )
            return

        changes: dict[str, Any] = {"status": self._task_status(event)}
        if event.data.get("agent_id"):
            changes["agent_id"] = agent_id
        self.repository.update_task(event.task_id, changes)

    def _apply_checkpoint_event(self, event: RunEvent) -> None:
        if event.type in {
            RunEventType.HOST_ROUND_STARTED,
            RunEventType.HOST_DECISION_CREATED,
            RunEventType.HOST_ROUND_COMPLETED,
        }:
            checkpoint = event.data.get("checkpoint")
            if isinstance(checkpoint, dict):
                self.repository.update_run_data(
                    event.run_id, {"host_state": checkpoint}
                )
            if event.type != RunEventType.HOST_DECISION_CREATED:
                return
            for task in event.data.get("tasks", []):
                if not isinstance(task, dict) or not task.get("id"):
                    continue
                if self.repository.get_task(task["id"]) is not None:
                    continue
                self.repository.create_task({
                    **task,
                    "run_id": event.run_id,
                    "parent_task_id": event.task_id,
                    "agent_id": task.get("agent_id", ""),
                    "status": "pending",
                })
            return

        if event.type == RunEventType.HOST_PLAN_CREATED:
            self.repository.update_run_data(
                event.run_id,
                {
                    "host_plan": {
                        "summary": event.data.get("summary", ""),
                        "tasks": event.data.get("tasks", []),
                    }
                },
            )
            for task in event.data.get("tasks", []):
                if not isinstance(task, dict) or not task.get("id"):
                    continue
                if self.repository.get_task(task["id"]) is not None:
                    continue
                self.repository.create_task({
                    **task,
                    "run_id": event.run_id,
                    "parent_task_id": event.task_id,
                    "agent_id": task.get("agent_id", ""),
                    "status": "pending",
                })
            return

        if event.task_id is None or event.parent_task_id is None:
            return
        checkpoint_fields = {
            key: event.data[key]
            for key in (
                "delegation_result",
                "evaluation",
                "approval",
            )
            if event.data.get(key) is not None
        }
        if checkpoint_fields:
            self.repository.update_task_data(
                event.task_id, checkpoint_fields
            )

    @staticmethod
    def _task_status(event: RunEvent) -> str:
        if event.type == RunEventType.TASK_COMPLETED:
            return "completed"
        if event.type == RunEventType.TASK_FAILED:
            return "failed"
        if event.type == RunEventType.TASK_BLOCKED:
            return "blocked"
        if event.type in {
            RunEventType.APPROVAL_REQUIRED,
            RunEventType.TASK_STATUS_CHANGED,
        }:
            return str(
                event.data.get("state")
                or (
                    "approval_required"
                    if event.type == RunEventType.APPROVAL_REQUIRED
                    else "working"
                )
            )
        return "working"

    def _add_assistant_message(
        self,
        event: RunEvent,
        content: str,
        mode: str,
        *,
        partial: bool = False,
        source: str = "unified-run",
    ) -> None:
        self._add_message(
            conversation_id=event.conversation_id,
            role="agent",
            content=content,
            task_id=event.task_id,
            metadata={
                "run_id": event.run_id,
                "mode": mode,
                "source": source,
                "partial": partial,
                **(
                    {"agent_id": event.data.get("agent_id")}
                    if event.data.get("agent_id")
                    else {}
                ),
            },
        )

    def _add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        task_id: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self.repository.add_message(
            {
                "id": uuid.uuid4().hex,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "parts": [],
                "task_id": task_id,
                "metadata": metadata,
                "created_at": self._now(),
            }
        )

    @staticmethod
    def _event(
        event_type: RunEventType,
        *,
        run_id: str,
        conversation_id: str,
        sequence: int,
        data: dict[str, Any],
        task_id: str | None = None,
    ) -> RunEvent:
        return RunEvent.create(
            event_type=event_type,
            run_id=run_id,
            conversation_id=conversation_id,
            sequence=sequence,
            task_id=task_id,
            data=data,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
