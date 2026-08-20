from __future__ import annotations

import json

import pytest

from a2a_runtime.agent import RuntimeMCPAgent
from a2a_runtime.config import AgentRuntimeConfig
from a2a_runtime.models import PendingAction
from a2a_runtime.streaming import RuntimeEventType


class FakeMCPClient:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return "scaled"

    async def disconnect(self):
        return None


def make_agent(client):
    config = AgentRuntimeConfig(
        agent_id="k8s-orchestrator",
        name="Orchestrator",
        port=8051,
        public_url="http://orchestrator:8051",
        mcp_url="http://mcp/sse",
        tool_policy={},
    )
    return RuntimeMCPAgent(config, "prompt", mcp_client=client)


@pytest.mark.anyio
async def test_approved_exact_action_executes_once_and_clears_pending():
    client = FakeMCPClient()
    agent = make_agent(client)
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
    )
    agent._pending_by_context["ctx-1"] = pending
    message = json.dumps({
        "type": "approval_decision",
        "approval_id": "ap-1",
        "decision": "approved",
        "action_digest": pending.action_digest,
    })

    events = [event async for event in agent.stream(message, "ctx-1")]

    assert events[-1].type is RuntimeEventType.COMPLETED
    assert events[-1].artifact_name == "specialist_result"
    assert events[-1].data["continuation"]["allowed"] is True
    assert client.calls == [
        ("scale_k8s_deployment", {"name": "api", "replicas": 2})
    ]
    assert "ctx-1" not in agent._pending_by_context


@pytest.mark.anyio
async def test_changed_digest_never_executes_tool():
    client = FakeMCPClient()
    agent = make_agent(client)
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
    )
    agent._pending_by_context["ctx-1"] = pending

    events = [
        event
        async for event in agent.stream(
            json.dumps({
                "type": "approval_decision",
                "approval_id": "ap-1",
                "decision": "approved",
                "action_digest": "0" * 64,
            }),
            "ctx-1",
        )
    ]

    assert events[-1].type is RuntimeEventType.ERROR
    assert client.calls == []


@pytest.mark.anyio
async def test_approved_action_recovers_after_agent_restart_from_signed_payload():
    client = FakeMCPClient()
    restarted_agent = make_agent(client)
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
    )
    message = json.dumps({
        "type": "approval_decision",
        "approval_id": pending.approval_id,
        "agent_id": pending.agent_id,
        "decision": "approved",
        "tool_name": pending.tool_name,
        "arguments": pending.arguments,
        "action_digest": pending.action_digest,
    })

    events = [event async for event in restarted_agent.stream(message, "ctx-1")]

    assert events[-1].type is RuntimeEventType.COMPLETED
    assert client.calls == [("scale_k8s_deployment", {"name": "api", "replicas": 2})]
