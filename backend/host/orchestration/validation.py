from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.host.orchestration.models import HostPlan


class PlanValidationError(ValueError):
    """Raised when a model-created Host plan is unsafe or inconsistent."""


def validate_plan(
    plan: HostPlan,
    agents: Mapping[str, Mapping[str, Any]],
) -> HostPlan:
    task_ids = [task.id for task in plan.tasks]
    known_ids = set(task_ids)
    if len(known_ids) != len(task_ids):
        raise PlanValidationError("plan contains a duplicate task ID")

    for task in plan.tasks:
        agent = agents.get(task.agent_id)
        if agent is None:
            raise PlanValidationError(
                f"task '{task.id}' references an unknown agent"
            )
        if task.risk == "write" and agent.get("read_only", True):
            raise PlanValidationError(
                f"task '{task.id}' assigns write work to a read-only agent"
            )
        for dependency in task.depends_on:
            if dependency not in known_ids:
                raise PlanValidationError(
                    f"task '{task.id}' has an unknown dependency"
                )

    dependencies = {
        task.id: set(task.depends_on) for task in plan.tasks
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise PlanValidationError("plan contains a dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)
    return plan
