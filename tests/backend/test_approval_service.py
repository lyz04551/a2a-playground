from __future__ import annotations

import json
import pytest

from backend.approvals.service import ApprovalService
from backend.orchestration.events import RunEvent, RunEventType
from backend.persistence.repository import SQLiteRepository


class FakeGateway:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"state": "completed", "text": "executed"}

    async def delegate(self, run_id, agent, message):
        self.calls.append((run_id, agent["id"], message))
        return self.result


@pytest.mark.anyio
async def test_approval_service_resumes_same_agent_run_with_exact_digest(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.create_run(
        "run-1",
        "conv-1",
        "approval_required",
        {"mode": "direct", "root_task_id": "run-1:root"},
    )
    repository.create_task(
        {
            "id": "run-1:root",
            "run_id": "run-1",
            "parent_task_id": None,
            "agent_id": "k8s-orchestrator",
            "status": "approval_required",
        }
    )
    repository.upsert_agent(
        {
            "id": "k8s-orchestrator",
            "name": "Orchestrator",
            "url": "http://orchestrator",
        }
    )
    repository.upsert_remote_binding(
        run_id="run-1",
        agent_id="k8s-orchestrator",
        context_id="ctx-1",
        task_id="task-1",
    )
    repository.create_approval(
        approval_id="ap-1",
        run_id="run-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
        action_digest="b" * 64,
    )
    repository.append_run_event(
        RunEvent.create(
            event_type=RunEventType.TOOL_CALLED,
            run_id="run-1",
            conversation_id="conv-1",
            sequence=1,
            task_id="run-1:root",
            data={
                "agent_id": "k8s-orchestrator",
                "tool_call_id": "call-1",
                "tool": "scale_k8s_deployment",
                "arguments": {"name": "api", "replicas": 2},
            },
        )
    )
    gateway = FakeGateway()
    service = ApprovalService(repository, gateway)

    result = await service.decide("ap-1", "approved")

    assert result["approval"]["status"] == "approved"
    assert result["result"]["text"] == "executed"
    assert repository.get_run("run-1")["status"] == "completed"
    assert repository.get_task("run-1:root")["status"] == "completed"
    events = repository.list_run_events("run-1")
    assert [event.type for event in events[-4:]] == [
        RunEventType.APPROVAL_DECIDED,
        RunEventType.TOOL_COMPLETED,
        RunEventType.TASK_COMPLETED,
        RunEventType.RUN_COMPLETED,
    ]
    assert events[-3].data["tool_call_id"] == "call-1"
    assert events[-3].data["result"] == "executed"
    assert gateway.calls[0][0:2] == ("run-1", "k8s-orchestrator")
    assert '"action_digest": "bbbb' in gateway.calls[0][2]
    assert '"decision": "approved"' in gateway.calls[0][2]
    continuation = json.loads(gateway.calls[0][2])
    assert continuation["agent_id"] == "k8s-orchestrator"
    assert continuation["tool_name"] == "scale_k8s_deployment"
    assert continuation["arguments"] == {"name": "api", "replicas": 2}

    repeated = await service.decide("ap-1", "approved")
    assert len(gateway.calls) == 1
    assert repeated["result"]["state"] == "completed"
    assert "未重复执行" in repeated["result"]["text"]


def prepare_pending_run(repository):
    repository.create_run(
        "run-1",
        "conv-1",
        "approval_required",
        {"mode": "direct", "root_task_id": "run-1:root"},
    )
    repository.create_task(
        {
            "id": "run-1:root",
            "run_id": "run-1",
            "parent_task_id": None,
            "agent_id": "k8s-orchestrator",
            "status": "approval_required",
        }
    )
    repository.upsert_agent(
        {
            "id": "k8s-orchestrator",
            "name": "Orchestrator",
            "url": "http://orchestrator",
        }
    )
    repository.create_approval(
        approval_id="ap-1",
        run_id="run-1",
        agent_id="k8s-orchestrator",
        tool_name="apply_k8s_yaml",
        arguments={"yaml": "kind: Pod"},
        action_digest="b" * 64,
    )
    repository.append_run_event(
        RunEvent.create(
            event_type=RunEventType.TOOL_CALLED,
            run_id="run-1",
            conversation_id="conv-1",
            sequence=1,
            task_id="run-1:root",
            data={
                "agent_id": "k8s-orchestrator",
                "tool_call_id": "call-1",
                "tool": "apply_k8s_yaml",
                "arguments": {"yaml": "kind: Pod"},
            },
        )
    )


@pytest.mark.anyio
async def test_rejected_approval_closes_tool_and_blocks_task(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    prepare_pending_run(repository)
    service = ApprovalService(
        repository,
        FakeGateway(
            {
                "state": "completed",
                "text": "用户已拒绝该变更，未执行任何写操作。",
            }
        ),
    )

    await service.decide("ap-1", "rejected")

    events = repository.list_run_events("run-1")
    assert events[-3].type == RunEventType.TOOL_COMPLETED
    assert "未执行" in events[-3].data["error"]
    assert events[-2].type == RunEventType.TASK_BLOCKED
    assert events[-1].type == RunEventType.RUN_COMPLETED
    assert repository.get_task("run-1:root")["status"] == "blocked"


@pytest.mark.anyio
async def test_failed_approved_execution_marks_tool_task_and_run_failed(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    prepare_pending_run(repository)
    service = ApprovalService(
        repository,
        FakeGateway(
            {
                "state": "failed",
                "text": "MCP execution failed",
                "error": "MCP execution failed",
            }
        ),
    )

    await service.decide("ap-1", "approved")

    events = repository.list_run_events("run-1")
    assert events[-3].type == RunEventType.TOOL_COMPLETED
    assert events[-3].data["error"] == "MCP execution failed"
    assert events[-2].type == RunEventType.TASK_FAILED
    assert events[-1].type == RunEventType.RUN_FAILED
    assert repository.get_task("run-1:root")["status"] == "failed"
    assert repository.get_run("run-1")["status"] == "failed"
