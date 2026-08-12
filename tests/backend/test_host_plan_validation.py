from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.host.orchestration.models import HostPlan, PlannedTask
from backend.host.orchestration.validation import (
    PlanValidationError,
    validate_plan,
)


AGENTS = {
    "k8s-ops": {"read_only": True},
    "k8s-orchestrator": {"read_only": False},
}


def task(
    task_id: str,
    agent_id: str = "k8s-ops",
    *,
    depends_on: tuple[str, ...] = (),
    risk: str = "read",
) -> PlannedTask:
    return PlannedTask(
        id=task_id,
        agent_id=agent_id,
        objective=f"Complete {task_id}",
        depends_on=list(depends_on),
        completion_criteria=["returns evidence"],
        risk=risk,
        max_attempts=2,
    )


def test_validate_plan_accepts_dependency_graph():
    plan = HostPlan(
        summary="diagnose then remediate",
        tasks=[
            task("diagnose"),
            task(
                "remediate",
                "k8s-orchestrator",
                depends_on=("diagnose",),
                risk="write",
            ),
        ],
    )

    assert validate_plan(plan, AGENTS) is plan


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        ([task("same"), task("same")], "duplicate"),
        ([task("child", depends_on=("missing",))], "unknown dependency"),
        (
            [task("a", depends_on=("b",)), task("b", depends_on=("a",))],
            "cycle",
        ),
        ([task("work", "missing-agent")], "unknown agent"),
        ([task("write", risk="write")], "read-only"),
    ],
)
def test_validate_plan_rejects_unsafe_graphs(tasks, message):
    plan = HostPlan(summary="invalid", tasks=tasks)

    with pytest.raises(PlanValidationError, match=message):
        validate_plan(plan, AGENTS)


def test_plan_rejects_more_than_six_tasks():
    with pytest.raises(ValidationError):
        HostPlan(summary="too large", tasks=[task(str(i)) for i in range(7)])


@pytest.mark.parametrize(
    "changes",
    [
        {"completion_criteria": []},
        {"max_attempts": 0},
        {"max_attempts": 3},
        {"id": "   "},
    ],
)
def test_planned_task_rejects_invalid_boundaries(changes):
    values = {
        "id": "diagnose",
        "agent_id": "k8s-ops",
        "objective": "Find the cause",
        "completion_criteria": ["Evidence is returned"],
        "max_attempts": 2,
    }
    values.update(changes)

    with pytest.raises(ValidationError):
        PlannedTask(**values)
