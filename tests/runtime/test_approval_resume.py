from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

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


class FakeGraph:
    def __init__(self, messages):
        self.messages = list(messages)

    async def aget_state(self, config):
        return type("State", (), {"values": {"messages": self.messages}})()

    async def aupdate_state(self, config, values, **kwargs):
        self.messages.extend(values["messages"])


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
    message = json.dumps(
        {
            "type": "approval_decision",
            "approval_id": "ap-1",
            "decision": "approved",
            "action_digest": pending.action_digest,
        }
    )

    events = [event async for event in agent.stream(message, "ctx-1")]

    assert events[-1].type is RuntimeEventType.COMPLETED
    assert events[-1].artifact_name == "specialist_result"
    assert events[-1].data["continuation"]["allowed"] is True
    assert client.calls == [("scale_k8s_deployment", {"name": "api", "replicas": 2})]
    assert "ctx-1" not in agent._pending_by_context


@pytest.mark.anyio
async def test_approved_action_reports_mcp_failure_as_terminal_error():
    class FailingMCPClient(FakeMCPClient):
        async def call_tool(self, name, arguments):
            raise RuntimeError("immutable Pod update")

    client = FailingMCPClient()
    agent = make_agent(client)
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="apply_k8s_yaml",
        arguments={"yaml": "kind: Pod"},
    )
    agent._pending_by_context["ctx-1"] = pending
    message = json.dumps({
        "type": "approval_decision",
        "approval_id": pending.approval_id,
        "decision": "approved",
        "action_digest": pending.action_digest,
    })

    events = [event async for event in agent.stream(message, "ctx-1")]

    assert events[-1].type is RuntimeEventType.ERROR
    assert "immutable Pod update" in events[-1].content
    assert "ctx-1" not in agent._pending_by_context


@pytest.mark.anyio
async def test_approved_action_closes_checkpoint_tool_call_history():
    client = FakeMCPClient()
    agent = make_agent(client)
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
    )
    agent._pending_by_context["ctx-1"] = pending
    agent._graph = FakeGraph(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": pending.tool_name,
                        "args": pending.arguments,
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    message = json.dumps(
        {
            "type": "approval_decision",
            "approval_id": pending.approval_id,
            "decision": "approved",
            "action_digest": pending.action_digest,
        }
    )

    _ = [event async for event in agent.stream(message, "ctx-1")]

    assert isinstance(agent._graph.messages[-1], ToolMessage)
    assert agent._graph.messages[-1].tool_call_id == "call-1"
    assert agent._graph.messages[-1].content == "scaled"


@pytest.mark.anyio
async def test_rejected_action_also_closes_checkpoint_tool_call_history():
    client = FakeMCPClient()
    agent = make_agent(client)
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
    )
    agent._pending_by_context["ctx-1"] = pending
    agent._graph = FakeGraph(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": pending.tool_name,
                        "args": pending.arguments,
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    message = json.dumps(
        {
            "type": "approval_decision",
            "approval_id": pending.approval_id,
            "decision": "rejected",
            "action_digest": pending.action_digest,
        }
    )

    _ = [event async for event in agent.stream(message, "ctx-1")]

    assert client.calls == []
    assert isinstance(agent._graph.messages[-1], ToolMessage)
    assert agent._graph.messages[-1].tool_call_id == "call-1"
    assert "未执行" in agent._graph.messages[-1].content


@pytest.mark.parametrize("query", ["1", "true", "null", "[]", '"approve"'])
def test_approval_parser_ignores_valid_non_object_json(query):
    assert RuntimeMCPAgent._parse_approval(query) is None


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
            json.dumps(
                {
                    "type": "approval_decision",
                    "approval_id": "ap-1",
                    "decision": "approved",
                    "action_digest": "0" * 64,
                }
            ),
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
    message = json.dumps(
        {
            "type": "approval_decision",
            "approval_id": pending.approval_id,
            "agent_id": pending.agent_id,
            "decision": "approved",
            "tool_name": pending.tool_name,
            "arguments": pending.arguments,
            "action_digest": pending.action_digest,
        }
    )

    events = [event async for event in restarted_agent.stream(message, "ctx-1")]

    assert events[-1].type is RuntimeEventType.COMPLETED
    assert client.calls == [("scale_k8s_deployment", {"name": "api", "replicas": 2})]
