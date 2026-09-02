from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostDecision,
    HostPlan,
    HostRunState,
    ObservedTask,
    PlannedTask,
)
from backend.host.orchestration.validation import (
    PlanValidationError,
    task_fingerprint,
    validate_decision,
    validate_plan,
)


AGENTS = {
    "k8s-ops": {
        "read_only": True,
        "skills": [{"id": "workload.verify", "tags": ["verify"]}],
    },
    "k8s-security": {
        "read_only": True,
        "skills": [{"id": "security.review", "tags": ["security"]}],
    },
    "k8s-orchestrator": {
        "read_only": False,
        "skills": [{"id": "resource.manage", "tags": ["resource"]}],
    },
}


def task(
    task_id: str,
    agent_id: str = "k8s-ops",
    *,
    depends_on: tuple[str, ...] = (),
    risk: str = "read",
    required_skill: str | None = None,
    workflow_role: str = "standard",
) -> PlannedTask:
    return PlannedTask(
        id=task_id,
        agent_id=agent_id,
        objective=f"Complete {task_id}",
        depends_on=list(depends_on),
        completion_criteria=["returns evidence"],
        risk=risk,
        required_skill=required_skill,
        workflow_role=workflow_role,
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


def test_validate_plan_rejects_agent_without_required_skill():
    plan = HostPlan(
        summary="misrouted mutation",
        tasks=[task(
            "change",
            "k8s-ops",
            required_skill="resource.manage",
        )],
    )

    with pytest.raises(PlanValidationError, match="required skill"):
        validate_plan(plan, AGENTS)


def test_validate_plan_accepts_guarded_kubernetes_mutation_workflow():
    plan = HostPlan(
        summary="guarded deployment",
        tasks=[
            task(
                "security",
                "k8s-security",
                required_skill="security.review",
                workflow_role="precheck",
            ),
            task(
                "change",
                "k8s-orchestrator",
                depends_on=("security",),
                risk="write",
                required_skill="resource.manage",
                workflow_role="mutation",
            ),
            task(
                "verify",
                "k8s-ops",
                depends_on=("change",),
                required_skill="workload.verify",
                workflow_role="verification",
            ),
        ],
    )

    assert validate_plan(plan, AGENTS) is plan


def test_validate_plan_rejects_mutation_marked_as_read():
    plan = HostPlan(
        summary="unsafe risk classification",
        tasks=[
            task("security", "k8s-security", workflow_role="precheck"),
            task(
                "change",
                "k8s-orchestrator",
                depends_on=("security",),
                risk="read",
                workflow_role="mutation",
            ),
            task(
                "verify",
                "k8s-ops",
                depends_on=("change",),
                workflow_role="verification",
            ),
        ],
    )

    with pytest.raises(PlanValidationError, match="risk write"):
        validate_plan(plan, AGENTS)


def test_validate_plan_rejects_non_security_deployment_precheck():
    plan = HostPlan(
        summary="wrong precheck agent",
        tasks=[
            task("conflict", "k8s-ops", workflow_role="precheck"),
            task(
                "change",
                "k8s-orchestrator",
                depends_on=("conflict",),
                risk="write",
                workflow_role="mutation",
            ),
            task(
                "verify",
                "k8s-ops",
                depends_on=("change",),
                workflow_role="verification",
            ),
        ],
    )

    with pytest.raises(PlanValidationError, match="security precheck"):
        validate_plan(plan, AGENTS)


@pytest.mark.parametrize("missing_role", ["precheck", "verification"])
def test_validate_plan_rejects_unguarded_kubernetes_mutation(missing_role):
    tasks = [
        task("security", "k8s-security", workflow_role="precheck"),
        task(
            "change",
            "k8s-orchestrator",
            depends_on=("security",),
            risk="write",
            workflow_role="mutation",
        ),
        task(
            "verify",
            "k8s-ops",
            depends_on=("change",),
            workflow_role="verification",
        ),
    ]
    tasks = [item for item in tasks if item.workflow_role != missing_role]
    if missing_role == "precheck":
        mutation = next(
            item for item in tasks if item.workflow_role == "mutation"
        )
        mutation.depends_on = []

    with pytest.raises(PlanValidationError, match=missing_role):
        validate_plan(HostPlan(summary="unsafe", tasks=tasks), AGENTS)


def test_host_only_plan_requires_response_and_forbids_tasks():
    plan = HostPlan(action="direct_response", summary="greeting", response="你好", tasks=[])
    assert validate_plan(plan, AGENTS) is plan

    with pytest.raises(ValidationError):
        HostPlan(action="clarification", summary="ask", tasks=[])
    with pytest.raises(ValidationError):
        HostPlan(action="direct_response", summary="mixed", response="hello", tasks=[task("unexpected")])


def test_delegate_plan_requires_tasks_and_forbids_direct_response():
    with pytest.raises(ValidationError):
        HostPlan(action="delegate", summary="empty", tasks=[])
    with pytest.raises(ValidationError):
        HostPlan(action="delegate", summary="mixed", response="hello", tasks=[task("work")])


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


def observed(
    planned: PlannedTask,
    *,
    outcome: str = "sufficient",
    allowed: bool | None = True,
) -> ObservedTask:
    return ObservedTask(
        task=planned,
        result=DelegationResult(
            state="completed",
            output={
                "summary": "evidence",
                "continuation": {"allowed": allowed},
            },
        ),
        evaluation=Evaluation(outcome=outcome, reason="evaluated"),
        actual_agent_id=planned.agent_id,
    )


def test_react_accepts_parallel_read_checks_in_one_round():
    decision = HostDecision(
        action="delegate",
        reason="Independent preflight checks",
        tasks=[
            task("security", "k8s-security", workflow_role="precheck"),
            task("capacity", "k8s-ops"),
        ],
    )

    assert validate_decision(
        decision, AGENTS, HostRunState(goal="deploy nginx")
    ) is decision


def test_react_rejects_duplicate_semantic_task_from_later_round():
    repeated = task("security-new-id", "k8s-security", workflow_role="precheck")
    state = HostRunState(
        goal="deploy nginx",
        task_fingerprints={task_fingerprint(repeated)},
    )
    decision = HostDecision(
        action="delegate",
        reason="Repeat the same check",
        tasks=[repeated],
    )

    with pytest.raises(PlanValidationError, match="duplicate semantic task"):
        validate_decision(decision, AGENTS, state)


def test_react_rejects_mutation_without_successful_security_observation():
    decision = HostDecision(
        action="delegate",
        reason="Create the workload",
        tasks=[task(
            "change",
            "k8s-orchestrator",
            risk="write",
            workflow_role="mutation",
        )],
    )

    with pytest.raises(PlanValidationError, match="security precheck"):
        validate_decision(decision, AGENTS, HostRunState(goal="deploy nginx"))


def test_react_accepts_mutation_after_security_allows_continuation():
    security = task(
        "security", "k8s-security", workflow_role="precheck"
    )
    state = HostRunState(
        goal="deploy nginx",
        observations={security.id: observed(security)},
        successful={security.id},
    )
    decision = HostDecision(
        action="delegate",
        reason="Security review passed",
        tasks=[task(
            "change",
            "k8s-orchestrator",
            risk="write",
            workflow_role="mutation",
        )],
    )

    assert validate_decision(decision, AGENTS, state) is decision


def test_react_rejects_verification_in_same_round_as_unfinished_mutation():
    security = task(
        "security", "k8s-security", workflow_role="precheck"
    )
    state = HostRunState(
        goal="deploy nginx",
        observations={security.id: observed(security)},
        successful={security.id},
    )
    decision = HostDecision(
        action="delegate",
        reason="Create and verify",
        tasks=[
            task(
                "change", "k8s-orchestrator", risk="write",
                workflow_role="mutation",
            ),
            task("verify", "k8s-ops", workflow_role="verification"),
        ],
    )

    with pytest.raises(PlanValidationError, match="successful mutation"):
        validate_decision(decision, AGENTS, state)


def test_react_accepts_verification_after_mutation_completed():
    mutation = task(
        "change", "k8s-orchestrator", risk="write",
        workflow_role="mutation",
    )
    state = HostRunState(
        goal="deploy nginx",
        observations={mutation.id: observed(mutation)},
        successful={mutation.id},
    )
    decision = HostDecision(
        action="delegate",
        reason="Verify the created workload",
        tasks=[task("verify", "k8s-ops", workflow_role="verification")],
    )

    assert validate_decision(decision, AGENTS, state) is decision


def test_react_accepts_sufficient_security_when_legacy_continuation_is_unknown():
    security = task(
        "security", "k8s-security", workflow_role="precheck"
    )
    state = HostRunState(
        goal="deploy nginx",
        observations={security.id: observed(security, allowed=None)},
        successful={security.id},
    )
    decision = HostDecision(
        action="delegate",
        reason="Security review was sufficient and did not explicitly block",
        tasks=[task(
            "change",
            "k8s-orchestrator",
            risk="write",
            workflow_role="mutation",
        )],
    )

    assert validate_decision(decision, AGENTS, state) is decision


def test_react_rejects_complete_after_mutation_without_verification():
    mutation = task(
        "change",
        "k8s-orchestrator",
        risk="write",
        workflow_role="mutation",
    )
    state = HostRunState(
        goal="deploy nginx",
        observations={mutation.id: observed(mutation)},
        successful={mutation.id},
    )
    decision = HostDecision(
        action="complete",
        reason="Deployment created",
        response="Deployment completed",
    )

    with pytest.raises(PlanValidationError, match="verification"):
        validate_decision(decision, AGENTS, state)
