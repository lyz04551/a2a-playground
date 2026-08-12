from __future__ import annotations

import asyncio
import pytest
import httpx
from langchain_core.messages import AIMessage, ToolMessage

from a2a_runtime.mcp_client import K8sMCPClient
from a2a_runtime.agent import RuntimeMCPAgent
from a2a_runtime.config import AgentRuntimeConfig
from a2a_runtime.streaming import RuntimeEventType


class FakeSession:
    async def list_tools(self):
        class Tool:
            name = "list_k8s_pod"
            description = "List pods"
            inputSchema = {"type": "object", "properties": {}}

        class Response:
            tools = [Tool()]

        return Response()

    async def call_tool(self, name, arguments):
        class Text:
            text = f"{name}:{arguments['namespace']}"

        class Response:
            content = [Text()]

        return Response()


@pytest.mark.anyio
async def test_client_normalizes_tool_catalog_and_text_result():
    client = K8sMCPClient(
        "http://mcp.invalid/sse",
        session_factory=lambda: FakeSession(),
    )

    tools = await client.list_tools()
    result = await client.call_tool("list_k8s_pod", {"namespace": "default"})

    assert tools == [
        {
            "name": "list_k8s_pod",
            "description": "List pods",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    assert result == "list_k8s_pod:default"


@pytest.mark.anyio
async def test_client_reconnects_once_after_stale_sse_timeout():
    class StaleSession(FakeSession):
        async def call_tool(self, name, arguments):
            raise httpx.ReadTimeout("stale SSE connection")

    sessions = iter([StaleSession(), FakeSession()])
    client = K8sMCPClient(
        "http://mcp.invalid/sse",
        session_factory=lambda: next(sessions),
    )

    result = await client.call_tool("list_k8s_pod", {"namespace": "default"})

    assert result == "list_k8s_pod:default"


@pytest.mark.anyio
async def test_agent_warm_up_degrades_when_mcp_is_temporarily_unavailable():
    class UnavailableMCP:
        async def list_tools(self):
            raise TimeoutError("MCP unavailable")

    config = AgentRuntimeConfig(
        agent_id="ops", name="Ops", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=UnavailableMCP())

    assert await agent.warm_up() is False
    readiness = agent.readiness()
    assert readiness["state"] == "degraded"
    assert readiness["checks"]["mcp"]["state"] == "error"
    assert "MCP unavailable" in readiness["checks"]["mcp"]["detail"]


@pytest.mark.anyio
async def test_client_bounds_a_hung_tool_call():
    class HungSession(FakeSession):
        async def call_tool(self, name, arguments):
            await asyncio.Event().wait()

    client = K8sMCPClient(
        "http://mcp.invalid/sse",
        session_factory=lambda: HungSession(),
        tool_timeout=0.01,
    )

    with pytest.raises(TimeoutError, match="timed out"):
        await client.call_tool("list_k8s_pod", {"namespace": "default"})


@pytest.mark.anyio
async def test_agent_bounds_a_hung_graph_execution():
    class HungGraph:
        async def astream(self, *_args, **_kwargs):
            await asyncio.Event().wait()
            yield {}

    config = AgentRuntimeConfig(
        agent_id="ops", name="Ops", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(
        config, "prompt", mcp_client=FakeSession(), run_timeout=0.01,
    )
    agent._tools_loaded = True
    agent._graph = HungGraph()

    events = [event async for event in agent.stream("check cluster", "ctx")]

    assert len(events) == 1
    assert events[0].is_task_complete is True
    assert "timed out" in events[0].content


@pytest.mark.anyio
async def test_agent_stream_emits_every_result_from_parallel_tool_batch():
    calls = [
        {"id": "call-1", "name": "list_k8s_node", "args": {}},
        {"id": "call-2", "name": "list_k8s_namespace", "args": {}},
    ]
    tool_request = AIMessage(content="", tool_calls=calls)
    results = [
        ToolMessage(content="nodes", tool_call_id="call-1"),
        ToolMessage(content="namespaces", tool_call_id="call-2"),
    ]

    class ParallelGraph:
        received_config = None

        async def astream(self, *_args, **_kwargs):
            self.received_config = _args[1]
            yield {"messages": [tool_request]}
            yield {"messages": [tool_request, *results]}

        def get_state(self, _config):
            class State:
                values = {"messages": [AIMessage(content="complete")]}
            return State()

    config = AgentRuntimeConfig(
        agent_id="ops", name="Ops", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())
    agent._tools_loaded = True
    graph = ParallelGraph()
    agent._graph = graph

    events = [event async for event in agent.stream("check", "ctx")]
    result_ids = [
        event.data["tool_call_id"]
        for event in events
        if event.type is RuntimeEventType.TOOL_RESULT
    ]

    assert result_ids == ["call-1", "call-2"]
    assert graph.received_config["recursion_limit"] == 30


@pytest.mark.anyio
async def test_agent_stream_does_not_replay_tools_from_existing_context():
    old_call = AIMessage(content="", tool_calls=[
        {"id": "old", "name": "list_k8s_node", "args": {}},
    ])
    old_result = ToolMessage(content="old nodes", tool_call_id="old")
    new_call = AIMessage(content="", tool_calls=[
        {"id": "new", "name": "list_k8s_pod", "args": {}},
    ])
    new_result = ToolMessage(content="new pods", tool_call_id="new")

    class ContinuedGraph:
        state_reads = 0

        def get_state(self, _config):
            self.state_reads += 1
            messages = (
                [old_call, old_result]
                if self.state_reads == 1
                else [AIMessage(content="complete")]
            )
            class State:
                values = {"messages": messages}
            return State()

        async def astream(self, *_args, **_kwargs):
            yield {"messages": [old_call, old_result, new_call]}
            yield {"messages": [old_call, old_result, new_call, new_result]}

    config = AgentRuntimeConfig(
        agent_id="ops", name="Ops", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())
    agent._tools_loaded = True
    agent._graph = ContinuedGraph()

    events = [event async for event in agent.stream("continue", "ctx")]
    public_ids = [
        event.data.get("id") or event.data.get("tool_call_id")
        for event in events
        if event.type in {RuntimeEventType.TOOL_CALL, RuntimeEventType.TOOL_RESULT}
    ]

    assert public_ids == ["new", "new"]
