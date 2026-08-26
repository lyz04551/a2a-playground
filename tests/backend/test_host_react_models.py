from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostDecision,
    HostRunState,
    ObservedTask,
    PlannedTask,
)


def planned_task(task_id: str = "inspect") -> PlannedTask:
    return PlannedTask(
        id=task_id,
        agent_id="ops",
        objective="Inspect the workload",
        completion_criteria=["Return workload evidence"],
    )


def test_delegate_decision_requires_tasks():
    with pytest.raises(ValidationError):
        HostDecision(action="delegate", reason="Inspect current state", tasks=[])


@pytest.mark.parametrize("action", ["clarify", "complete", "stop"])
def test_non_delegate_decision_rejects_tasks(action):
    with pytest.raises(ValidationError):
        HostDecision(
            action=action,
            reason="No delegation is needed",
            response="Host response",
            tasks=[planned_task()],
        )


@pytest.mark.parametrize("action", ["clarify", "complete", "stop"])
def test_non_delegate_decision_requires_response(action):
    with pytest.raises(ValidationError):
        HostDecision(action=action, reason="Explain the decision")


def test_host_decision_rejects_text_only_approval_requests():
    with pytest.raises(ValidationError):
        HostDecision(
            action="request_approval",
            reason="The next operation is a write",
            response="Please approve the deployment",
        )


def test_delegate_decision_rejects_duplicate_task_ids():
    with pytest.raises(ValidationError):
        HostDecision(
            action="delegate",
            reason="Run independent checks",
            tasks=[planned_task("same"), planned_task("same")],
        )


def test_react_state_round_trips_structured_observations():
    task = planned_task("security-1").model_copy(
        update={"agent_id": "security", "workflow_role": "precheck"}
    )
    observation = ObservedTask(
        task=task,
        result=DelegationResult(
            state="completed",
            text="Namespace is missing",
            output={
                "summary": "Namespace is missing",
                "continuation": {
                    "allowed": False,
                    "reason": "production namespace does not exist",
                },
            },
        ),
        evaluation=Evaluation(
            outcome="blocked",
            reason="production namespace does not exist",
        ),
        actual_agent_id="security",
    )
    state = HostRunState(
        goal="deploy nginx",
        round=1,
        observations={task.id: observation},
        task_fingerprints={"security-fingerprint"},
        total_tasks=1,
    )

    restored = HostRunState.model_validate(state.model_dump(mode="json"))

    assert restored == state
    assert restored.observations[task.id].result.output is not None
    assert restored.observations[task.id].result.output.continuation.allowed is False
