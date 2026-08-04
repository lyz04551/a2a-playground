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


_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}


class RunService:
    """Own Run identity, persistence, lifecycle, messages, and replay."""

    def __init__(self, repository, registry, gateway, auto_host):
        self.repository = repository
        self.registry = registry
        self.gateway = gateway
        self.auto_host = auto_host
        self._active_tasks: dict[str, asyncio.Task] = {}

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
            if run_id is not None and self._active_tasks.get(run_id) is current:
                self._active_tasks.pop(run_id, None)

    async def _stream(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        conversation_id = self._conversation_id(command)
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
        yield self.repository.append_run_event(started)

        if self._is_cancelled(run_id):
            return
        strategy = self._strategy(
            command,
            run_id=run_id,
            conversation_id=conversation_id,
            root_task_id=root_task_id,
            sequence_start=2,
        )
        partial_output = ""
        assistant_saved = False
        failure: RunEvent | None = None
        awaiting_approval = False

        async for candidate in strategy.execute(command):
            if self._is_cancelled(run_id):
                return
            event = self.repository.append_run_event(candidate)
            self._apply_task_event(event)

            if event.type == RunEventType.MESSAGE_DELTA:
                partial_output += str(event.data.get("content") or "")
            elif event.type == RunEventType.MESSAGE_COMPLETED:
                content = str(event.data.get("content") or partial_output)
                if content and not assistant_saved:
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
            yield self.repository.append_run_event(terminal)
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
        yield self.repository.append_run_event(terminal)

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self.repository.get_run(run_id)
        if run is None:
            return None
        return {
            **run,
            "tasks": self.repository.list_tasks(run_id),
            "approvals": self.repository.list_approvals(run_id),
        }

    def list(self) -> list[dict[str, Any]]:
        return self.repository.list_runs()

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
        self.repository.append_run_event(event)
        active = self._active_tasks.get(run_id)
        current = asyncio.current_task()
        if active is not None and active is not current and not active.done():
            active.cancel()
        return self.repository.get_run(run_id)

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
            return AutoExecutionStrategy(self.auto_host, **arguments)
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

    @staticmethod
    def _task_status(event: RunEvent) -> str:
        if event.type == RunEventType.TASK_COMPLETED:
            return "completed"
        if event.type == RunEventType.TASK_FAILED:
            return "failed"
        if event.type in {
            RunEventType.APPROVAL_REQUIRED,
            RunEventType.TASK_STATUS_CHANGED,
        }:
            return str(event.data.get("state") or "working")
        return "working"

    def _add_assistant_message(
        self,
        event: RunEvent,
        content: str,
        mode: str,
        *,
        partial: bool = False,
    ) -> None:
        self._add_message(
            conversation_id=event.conversation_id,
            role="agent",
            content=content,
            task_id=event.task_id,
            metadata={
                "run_id": event.run_id,
                "mode": mode,
                "source": "unified-run",
                "partial": partial,
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
