from __future__ import annotations

import pytest

from a2a_runtime.config import ToolPolicyConfig
from a2a_runtime.models import ApprovalRequired, PolicyAction
from a2a_runtime.tool_adapter import MCPToolAdapter, schema_to_model
from a2a_runtime.tool_policy import ToolPolicy


class FakeMCPClient:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return f"called:{name}"


def test_schema_model_enforces_required_and_accepts_nested_values():
    model = schema_to_model(
        "PatchArgs",
        {
            "type": "object",
            "required": ["name", "patch"],
            "properties": {
                "name": {"type": "string", "description": "Resource name"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "replicas": {"type": "integer"},
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                "force": {"type": "boolean"},
            },
        },
    )

    parsed = model(name="api", patch={"replicas": 2, "labels": ["blue"]})

    assert parsed.name == "api"
    assert parsed.patch == {"replicas": 2, "labels": ["blue"]}
    assert parsed.force is None

    with pytest.raises(Exception):
        model(patch={"replicas": 2})


@pytest.mark.anyio
async def test_allowed_tool_calls_real_client_boundary():
    client = FakeMCPClient()
    adapter = MCPToolAdapter(
        client,
        ToolPolicy(ToolPolicyConfig(allow=["get_k8s_*"])),
        agent_id="k8s-ops",
    )
    tools = adapter.build_tools(
        [
            {
                "name": "get_k8s_pod_logs",
                "description": "Read logs",
                "input_schema": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                },
            }
        ]
    )

    result = await tools[0].ainvoke({"name": "api"})

    assert result == "called:get_k8s_pod_logs"
    assert client.calls == [("get_k8s_pod_logs", {"name": "api"})]


@pytest.mark.anyio
async def test_approval_required_tool_never_calls_mcp():
    client = FakeMCPClient()
    adapter = MCPToolAdapter(
        client,
        ToolPolicy(
            ToolPolicyConfig(approval_required=["patch_k8s_resource"])
        ),
        agent_id="k8s-orchestrator",
    )
    tool = adapter.build_tools(
        [
            {
                "name": "patch_k8s_resource",
                "description": "Patch resource",
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            }
        ]
    )[0]

    with pytest.raises(ApprovalRequired) as captured:
        await tool.ainvoke({"name": "api"})

    assert captured.value.pending_action.agent_id == "k8s-orchestrator"
    assert captured.value.pending_action.arguments == {"name": "api"}
    assert client.calls == []


@pytest.mark.anyio
async def test_tool_budget_stops_mcp_calls_and_resets_for_next_task():
    client = FakeMCPClient()
    adapter = MCPToolAdapter(
        client,
        ToolPolicy(ToolPolicyConfig(allow=["get_k8s_*"])),
        agent_id="k8s-ops",
        max_calls=2,
    )
    tool = adapter.build_tools([{
        "name": "get_k8s_pod_logs",
        "description": "Read logs",
        "input_schema": {"type": "object", "properties": {}},
    }])[0]
    config = {"configurable": {"thread_id": "ctx"}}

    adapter.reset_budget("ctx")
    await tool.ainvoke({}, config=config)
    await tool.ainvoke({}, config=config)
    limited = await tool.ainvoke({}, config=config)

    assert len(client.calls) == 2
    assert "预算" in limited

    adapter.reset_budget("ctx")
    assert await tool.ainvoke({}, config=config) == "called:get_k8s_pod_logs"
    assert len(client.calls) == 3


@pytest.mark.anyio
async def test_soft_budget_asks_model_to_reassess_but_allows_more_calls():
    client = FakeMCPClient()
    adapter = MCPToolAdapter(
        client,
        ToolPolicy(ToolPolicyConfig(allow=["get_k8s_*"])),
        agent_id="k8s-ops",
        soft_budget_ratio=0.4,
        max_calls=5,
    )
    tool = adapter.build_tools([{
        "name": "get_k8s_resource",
        "description": "Read a resource",
        "input_schema": {"type": "object", "properties": {}},
    }])[0]
    config = {"configurable": {"thread_id": "ctx"}}

    first = await tool.ainvoke({}, config=config)
    second = await tool.ainvoke({}, config=config)
    third = await tool.ainvoke({}, config=config)

    assert first == "called:get_k8s_resource"
    assert second == "called:get_k8s_resource"
    assert "已调用 3 次工具" in third
    assert "证据是否已经足够" in third
    assert "仍可继续调用" in third
    assert len(client.calls) == 3


def test_denied_tools_are_not_exposed_to_the_model():
    adapter = MCPToolAdapter(
        FakeMCPClient(),
        ToolPolicy(
            ToolPolicyConfig(
                allow=["get_k8s_*"],
                deny=["get_k8s_pod_linked_env"],
            )
        ),
        agent_id="k8s-ops",
    )

    tools = adapter.build_tools(
        [
            {
                "name": "get_k8s_pod_logs",
                "description": "Read logs",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_k8s_pod_linked_env",
                "description": "Read environment",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]
    )

    assert [tool.name for tool in tools] == ["get_k8s_pod_logs"]


@pytest.mark.parametrize(
    "tool_name",
    [
        "drain_k8s_node",
        "register_k8s_cluster",
        "unregister_k8s_cluster",
        "helm_uninstall_release",
        "run_command_in_k8s_pod",
        "upload_file_to_k8s_pod",
        "delete_pod_file",
    ],
)
def test_agent_can_approval_gate_every_live_mutating_tool(tool_name):
    policy = ToolPolicy(
        ToolPolicyConfig(approval_required=[tool_name])
    )

    assert policy.classify(tool_name).action is PolicyAction.APPROVAL_REQUIRED
