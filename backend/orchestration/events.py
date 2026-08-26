"""Versioned events emitted while a unified agent run is in progress."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RunEventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    HOST_PLANNING = "host.planning"
    HOST_ROUND_STARTED = "host.round_started"
    HOST_DECISION_CREATED = "host.decision_created"
    HOST_ROUND_COMPLETED = "host.round_completed"
    HOST_PLAN_CREATED = "host.plan_created"
    HOST_PLAN_REVISED = "host.plan_revised"
    HOST_SYNTHESIS_STARTED = "host.synthesis_started"
    TASK_DELEGATED = "task.delegated"
    TASK_STARTED = "task.started"
    TASK_CONTEXT_PREPARED = "task.context_prepared"
    TASK_RETRY_SCHEDULED = "task.retry_scheduled"
    TASK_EVALUATED = "task.evaluated"
    TASK_BLOCKED = "task.blocked"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_DECIDED = "approval.decided"
    ARTIFACT_CREATED = "artifact.created"


class RunEvent(BaseModel):
    """A single ordered, serializable event in a run's event stream."""

    version: Literal[1] = 1
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    sequence: int = Field(ge=1)
    run_id: str
    conversation_id: str
    task_id: str | None = None
    parent_task_id: str | None = None
    type: RunEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        return value.astimezone(timezone.utc)

    @classmethod
    def create(
        cls,
        *,
        event_type: RunEventType,
        run_id: str,
        conversation_id: str,
        sequence: int,
        data: dict[str, Any],
        task_id: str | None = None,
        parent_task_id: str | None = None,
    ) -> Self:
        return cls(
            type=event_type,
            run_id=run_id,
            conversation_id=conversation_id,
            sequence=sequence,
            task_id=task_id,
            parent_task_id=parent_task_id,
            data=data,
        )
