from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any, Iterable

from .config import ToolPolicyConfig
from .models import PolicyAction, PolicyDecision


DEFAULT_GLOBAL_DENY: tuple[str, ...] = ()


def _matches(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(name, pattern) for pattern in patterns)


class ToolPolicy:
    def __init__(
        self,
        config: ToolPolicyConfig,
        *,
        global_deny: Iterable[str] = DEFAULT_GLOBAL_DENY,
    ):
        self.config = config
        self.global_deny = tuple(global_deny)

    def classify(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> PolicyDecision:
        del arguments
        if _matches(tool_name, self.global_deny):
            return PolicyDecision(
                action=PolicyAction.DENY,
                reason="Denied by global policy",
            )
        if _matches(tool_name, self.config.deny):
            return PolicyDecision(
                action=PolicyAction.DENY,
                reason="Denied by agent policy",
            )
        if _matches(tool_name, self.config.approval_required):
            return PolicyDecision(
                action=PolicyAction.APPROVAL_REQUIRED,
                reason="Write operation requires explicit user approval",
            )
        if _matches(tool_name, self.config.allow):
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                reason="Allowed by agent policy",
            )
        return PolicyDecision(
            action=PolicyAction.DENY,
            reason="Denied by default",
        )
