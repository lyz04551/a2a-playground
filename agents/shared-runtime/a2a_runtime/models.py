from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason: str


def canonical_action_digest(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool_name": tool_name, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PendingAction(BaseModel):
    approval_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    action_digest: str = Field(min_length=64, max_length=64)
    risk: str = "write"
    reason: str = ""

    @classmethod
    def from_call(
        cls,
        *,
        approval_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk: str = "write",
        reason: str = "",
    ) -> "PendingAction":
        copied_arguments = dict(arguments)
        return cls(
            approval_id=approval_id,
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=copied_arguments,
            action_digest=canonical_action_digest(tool_name, copied_arguments),
            risk=risk,
            reason=reason,
        )

    def matches(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        return self.action_digest == canonical_action_digest(tool_name, arguments)


class ApprovalRequired(RuntimeError):
    def __init__(self, pending_action: PendingAction):
        self.pending_action = pending_action
        super().__init__(f"Approval required for {pending_action.tool_name}")


class ToolDenied(PermissionError):
    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool '{tool_name}' denied: {reason}")

