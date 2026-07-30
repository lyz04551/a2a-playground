from __future__ import annotations

import pytest

from backend.approvals.service import ApprovalService
from backend.persistence.repository import SQLiteRepository


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def delegate(self, run_id, agent, message):
        self.calls.append((run_id, agent["id"], message))
        return {"state": "completed", "text": "executed"}


@pytest.mark.anyio
async def test_approval_service_resumes_same_agent_run_with_exact_digest(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.create_run("run-1", "conv-1", "approval_required")
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
    gateway = FakeGateway()
    service = ApprovalService(repository, gateway)

    result = await service.decide("ap-1", "approved")

    assert result["approval"]["status"] == "approved"
    assert result["result"]["text"] == "executed"
    assert repository.get_run("run-1")["status"] == "completed"
    assert gateway.calls[0][0:2] == ("run-1", "k8s-orchestrator")
    assert '"action_digest": "bbbb' in gateway.calls[0][2]
    assert '"decision": "approved"' in gateway.calls[0][2]
