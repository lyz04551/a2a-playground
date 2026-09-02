from __future__ import annotations

import pytest

from backend.host.langgraph.manager import LangGraphHostManager


class FakeRegistry:
    def get(self, agent_id):
        return {"id": agent_id, "name": agent_id}


class FailedStreamGateway:
    async def delegate_stream(self, run_id, agent, message):
        yield {
            "type": "error",
            "state": "failed",
            "text": "Agent execution timed out after 180s",
        }
        yield {
            "type": "done",
            "task_id": "remote-1",
            "text": "Agent execution timed out after 180s",
        }


class ApprovalStreamGateway:
    async def delegate_stream(self, run_id, agent, message):
        yield {
            "type": "approval_required",
            "state": "pending",
            "text": "Approval required",
            "approval": {
                "id": "ap-1",
                "tool_name": "apply_k8s_yaml",
                "arguments": {"yaml": "kind: Deployment"},
            },
        }
        yield {"type": "done", "text": "Approval required"}


@pytest.mark.anyio
async def test_delegate_task_does_not_let_done_overwrite_remote_failure():
    manager = LangGraphHostManager.__new__(LangGraphHostManager)
    manager._registry = FakeRegistry()
    manager._gateway = FailedStreamGateway()

    result = await manager._delegate_task(
        "run-1", "orchestrator", "deploy nginx", lambda event: None
    )

    assert result.state == "failed"
    assert result.error == "Agent execution timed out after 180s"


@pytest.mark.anyio
async def test_delegate_task_preserves_approval_request_through_done():
    manager = LangGraphHostManager.__new__(LangGraphHostManager)
    manager._registry = FakeRegistry()
    manager._gateway = ApprovalStreamGateway()

    result = await manager._delegate_task(
        "run-1", "orchestrator", "deploy nginx", lambda event: None
    )

    assert result.state == "approval_required"
    assert result.approval["id"] == "ap-1"
    assert result.approval["arguments"] == {"yaml": "kind: Deployment"}
