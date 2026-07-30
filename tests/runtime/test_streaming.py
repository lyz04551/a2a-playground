from __future__ import annotations

from a2a_runtime.models import PendingAction
from a2a_runtime.streaming import RuntimeEvent, RuntimeEventType


def test_pending_action_event_keeps_structured_artifact():
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"namespace": "default", "name": "api", "replicas": 2},
    )

    event = RuntimeEvent.approval_required(pending)

    assert event.type is RuntimeEventType.APPROVAL_REQUIRED
    assert event.require_user_input is True
    assert event.artifact_name == "pending_action"
    assert event.data["action_digest"] == pending.action_digest


def test_completed_event_has_named_artifact_and_terminal_state():
    event = RuntimeEvent.completed(
        content="Diagnosis complete",
        artifact_name="diagnosis",
        data={"severity": "high"},
    )

    assert event.is_task_complete is True
    assert event.require_user_input is False
    assert event.artifact_name == "diagnosis"
