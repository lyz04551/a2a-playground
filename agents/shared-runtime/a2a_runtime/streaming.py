from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .models import PendingAction


class RuntimeEventType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    ERROR = "error"


class RuntimeEvent(BaseModel):
    type: RuntimeEventType
    content: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    artifact_name: str | None = None
    is_task_complete: bool = False
    require_user_input: bool = False

    @classmethod
    def approval_required(cls, pending: PendingAction) -> "RuntimeEvent":
        return cls(
            type=RuntimeEventType.APPROVAL_REQUIRED,
            content=f"Approval required for {pending.tool_name}",
            data=pending.model_dump(),
            artifact_name="pending_action",
            require_user_input=True,
        )

    @classmethod
    def completed(
        cls,
        *,
        content: str,
        artifact_name: str,
        data: dict[str, Any] | None = None,
    ) -> "RuntimeEvent":
        return cls(
            type=RuntimeEventType.COMPLETED,
            content=content,
            data=data or {"text": content},
            artifact_name=artifact_name,
            is_task_complete=True,
        )

