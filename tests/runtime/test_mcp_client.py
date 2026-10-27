from __future__ import annotations

import asyncio
from types import SimpleNamespace
from contextlib import asynccontextmanager
import pytest
import httpx
from langchain_core.messages import AIMessage, ToolMessage

from a2a_runtime.mcp_client import K8sMCPClient
import a2a_runtime.mcp_client as mcp_client_module
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


class FakeClientSession:
    initialized = []

    def __init__(self, read, write):
        self.read = read
        self.write = write

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def initialize(self):
        self.initialized.append((self.read, self.write))


@pytest.mark.anyio
async def test_client_uses_legacy_sse_transport(monkeypatch):
    calls = []

    @asynccontextmanager
    async def fake_sse_client(**kwargs):
        calls.append(kwargs)
        yield "sse-read", "sse-write"

    @asynccontextmanager
    async def unexpected_streamable_client(**_kwargs):
        raise AssertionError("streamable transport must not be selected")
        yield

    FakeClientSession.initialized.clear()
    monkeypatch.setattr(mcp_client_module, "sse_client", fake_sse_client)
    monkeypatch.setattr(
        mcp_client_module,
        "streamablehttp_client",
        unexpected_streamable_client,
        raising=False,
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", FakeClientSession)
    client = K8sMCPClient("http://mcp.invalid/sse", transport="sse")

    await client.connect()

    assert calls[0]["url"] == "http://mcp.invalid/sse"
    assert FakeClientSession.initialized == [("sse-read", "sse-write")]
    await client.disconnect()


@pytest.mark.anyio
async def test_client_uses_streamable_http_transport(monkeypatch):
    calls = []

    @asynccontextmanager
    async def unexpected_sse_client(**_kwargs):
        raise AssertionError("legacy SSE transport must not be selected")
        yield

    @asynccontextmanager
    async def fake_streamable_client(**kwargs):
        calls.append(kwargs)
        yield "http-read", "http-write", lambda: "session-id"

    FakeClientSession.initialized.clear()
    monkeypatch.setattr(mcp_client_module, "sse_client", unexpected_sse_client)
    monkeypatch.setattr(
        mcp_client_module,
        "streamablehttp_client",
        fake_streamable_client,
        raising=False,
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", FakeClientSession)
    client = K8sMCPClient(
        "http://mcp.invalid/mcp", transport="streamable_http"
    )

    await client.connect()

    assert calls[0]["url"] == "http://mcp.invalid/mcp"
    assert FakeClientSession.initialized == [("http-read", "http-write")]
    await client.disconnect()


@pytest.mark.anyio
async def test_each_operation_enters_and_exits_transport_in_same_task(monkeypatch):
    lifecycle = []

    class LifecycleSession(FakeClientSession):
        async def list_tools(self):
            return await FakeSession().list_tools()

    @asynccontextmanager
    async def fake_streamable_client(**_kwargs):
        lifecycle.append(("enter", asyncio.current_task()))
        try:
            yield "http-read", "http-write", lambda: "session-id"
        finally:
            lifecycle.append(("exit", asyncio.current_task()))

    monkeypatch.setattr(
        mcp_client_module, "streamablehttp_client", fake_streamable_client
    )
    monkeypatch.setattr(mcp_client_module, "ClientSession", LifecycleSession)
    client = K8sMCPClient(
        "http://mcp.invalid/mcp", transport="streamable_http"
    )

    await asyncio.create_task(client.list_tools())

    assert [event for event, _task in lifecycle] == ["enter", "exit"]
    assert lifecycle[0][1] is lifecycle[1][1]

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
async def test_client_raises_when_mcp_marks_tool_result_as_error():
    class ErrorSession(FakeSession):
        async def call_tool(self, name, arguments):
            class Text:
                text = 'update Pod error: immutable field'

            class Response:
                isError = True
                content = [Text()]

            return Response()

    client = K8sMCPClient(
        "http://mcp.invalid/sse",
        session_factory=lambda: ErrorSession(),
    )

    with pytest.raises(RuntimeError, match="immutable field"):
        await client.call_tool("apply_k8s_yaml", {"yaml": "kind: Pod"})


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
async def test_client_serializes_parallel_calls_on_one_session():
    class ConcurrencySensitiveSession(FakeSession):
        def __init__(self):
            self.active = 0
            self.max_active = 0

        async def call_tool(self, name, arguments):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return await super().call_tool(name, arguments)

    session = ConcurrencySensitiveSession()
    client = K8sMCPClient(
        "http://mcp.invalid/mcp",
        session_factory=lambda: session,
    )

    results = await asyncio.gather(*(
        client.call_tool("list_k8s_pod", {"namespace": namespace})
        for namespace in ("default", "kube-system", "mcp")
    ))

    assert session.max_active == 1
    assert results == [
        "list_k8s_pod:default",
        "list_k8s_pod:kube-system",
        "list_k8s_pod:mcp",
    ]


@pytest.mark.anyio
async def test_client_reconnects_after_timeout_invalidates_session():
    class HungSession(FakeSession):
        async def call_tool(self, name, arguments):
            await asyncio.Event().wait()

    healthy = FakeSession()
    sessions = iter([HungSession(), healthy])
    client = K8sMCPClient(
        "http://mcp.invalid/mcp",
        session_factory=lambda: next(sessions),
        tool_timeout=0.01,
    )

    with pytest.raises(TimeoutError, match="timed out"):
        await client.call_tool("list_k8s_pod", {"namespace": "default"})

    result = await client.call_tool(
        "list_k8s_pod", {"namespace": "kube-system"}
    )
    assert result == "list_k8s_pod:kube-system"


@pytest.mark.anyio
async def test_agent_returns_deterministic_partial_result_when_summary_model_is_unavailable():
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

    assert events[-1].is_task_complete is True
    assert events[-1].type is RuntimeEventType.COMPLETED
    assert events[-1].data["status"] == "partial"
    assert "预算" in events[-1].content
    assert "没有已完成的工具结果" in events[-1].content


@pytest.mark.anyio
async def test_deterministic_partial_summary_reports_generic_tool_inventory():
    config = AgentRuntimeConfig(
        agent_id="security", name="Security", port=8053,
        public_url="http://security", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())

    summary = await agent._deterministic_partial_summary(
        {
            "cluster": '[{"name":"default","version":"v1.33.4"}]',
            "namespaces": '[{"name":"default"},{"name":"kube-system"}]',
            "rbac": '[{"name":"tools-cluster-admin-rolebinding"},{"name":"reader"}]',
        },
        "总结模型超时",
        {
            "cluster": "list_k8s_cluster",
            "namespaces": "list_k8s_namespace",
            "rbac": "list_k8s_cluster_rolebinding",
        },
    )

    assert "list_k8s_namespace {}：返回 2 项" in summary
    assert "tools-cluster-admin-rolebinding" in summary
    assert "roleRef 与 subjects" not in summary
    assert "调用 rbac" in summary


@pytest.mark.anyio
async def test_budget_fallback_reports_actual_pod_enumeration_and_missing_reads():
    config = AgentRuntimeConfig(
        agent_id="ops", name="K8s Ops Agent", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())
    summary = await agent._deterministic_partial_summary(
        {
            "list-1": '[{"name":"pod-a","namespace":"default"},{"name":"pod-b","namespace":"default"}]',
            "read-1": "Name: pod-a\nStatus: Pending",
        },
        "工具调用预算已用尽",
        {
            "list-1": "list_k8s_pod", "read-1": "describe_k8s_pod",
        },
        {
            "list-1": {"tool": "list_k8s_pod", "arguments": {"namespace": "default"}},
            "read-1": {"tool": "describe_k8s_pod", "arguments": {"namespace": "default", "name": "pod-a"}},
        },
    )
    assert "本轮部分检查报告" in summary
    assert "返回 2 项：pod-a, pod-b" in summary
    assert '"name": "pod-a"' in summary
    assert "Pod/default/pod-b" in summary
    assert "调用 list-1" in summary


def test_current_run_summary_evidence_is_deduplicated_and_bounded():
    evidence = RuntimeMCPAgent._current_run_evidence({
        "call-1": "a" * 5_000,
        "call-2": "b" * 5_000,
        "call-3": "c" * 20_000,
        "call-4": "d" * 20_000,
        "call-5": "e" * 20_000,
        "call-6": "f" * 20_000,
        "call-7": "g" * 20_000,
    })

    assert evidence.count("工具调用 call-1") == 1
    assert "a" * 2_001 not in evidence
    assert len(evidence) < 12_500
    assert "工具调用 call-7" in evidence


def test_current_run_evidence_includes_tool_and_resource_arguments():
    evidence = RuntimeMCPAgent._current_run_evidence(
        {"list-1": '[{"name":"app"}]'},
        {"list-1": {"tool": "list_k8s_resource", "arguments": {"kind": "Deployment", "namespace": "default"}}},
    )
    assert "list_k8s_resource" in evidence
    assert "Deployment" in evidence
    assert "default" in evidence


def test_agent_bounds_model_output_and_disables_thinking_by_default(
    monkeypatch,
):
    monkeypatch.delenv("AGENT_ENABLE_THINKING", raising=False)
    monkeypatch.delenv("AGENT_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("AGENT_SUMMARY_MAX_TOKENS", raising=False)
    config = AgentRuntimeConfig(
        agent_id="ops", name="Ops", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )

    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())

    assert agent.enable_thinking is False
    assert agent.max_output_tokens == 8192
    assert agent.summary_max_tokens == 4096


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

        async def aget_state(self, _config):
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
    assert graph.received_config["recursion_limit"] == 82


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

        async def aget_state(self, _config):
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


@pytest.mark.anyio
async def test_agent_converts_step_limit_message_into_partial_evidence():
    call = AIMessage(content="", tool_calls=[
        {"id": "check", "name": "list_k8s_resource", "args": {}},
    ])
    result = ToolMessage(
        content='[{"name":"nginx"}]', tool_call_id="check"
    )

    class StepLimitedGraph:
        async def astream(self, *_args, **_kwargs):
            yield {"messages": [call]}
            yield {"messages": [call, result]}

        async def aget_state(self, _config):
            class State:
                values = {"messages": [AIMessage(
                    content="Sorry, need more steps to process this request."
                )]}
            return State()

    config = AgentRuntimeConfig(
        agent_id="ops", name="K8s Ops Agent", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())
    agent._tools_loaded = True
    agent._graph = StepLimitedGraph()

    events = [event async for event in agent.stream("verify", "ctx")]
    completed = events[-1]

    assert completed.data["status"] == "partial"
    assert "返回 1 项：nginx" in completed.content
    assert "nginx" in completed.content
    assert "Sorry" not in completed.content


@pytest.mark.anyio
async def test_agent_rejects_empty_structured_result_as_completed_report():
    class EmptyResultGraph:
        async def astream(self, *_args, **_kwargs):
            yield {"messages": []}

        async def aget_state(self, _config):
            class State:
                values = {"messages": [AIMessage(content=(
                    '{"status":"completed","summary":"","findings":[],"evidence":[]}'
                ))]}
            return State()

    config = AgentRuntimeConfig(
        agent_id="ops", name="K8s Ops Agent", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())
    agent._tools_loaded = True
    agent._graph = EmptyResultGraph()

    events = [event async for event in agent.stream("查看所有 Pod", "ctx")]
    completed = events[-1]

    assert completed.data["status"] == "partial"
    assert "没有已完成的工具结果" in completed.content


@pytest.mark.anyio
async def test_agent_turns_blank_final_text_into_partial_evidence_report():
    class BlankResultGraph:
        async def astream(self, *_args, **_kwargs):
            yield {"messages": []}

        async def aget_state(self, _config):
            class State:
                values = {"messages": [AIMessage(content="")]}
            return State()

    config = AgentRuntimeConfig(
        agent_id="ops", name="K8s Ops Agent", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession())
    agent._tools_loaded = True
    agent._graph = BlankResultGraph()

    events = [event async for event in agent.stream("审查 Deployment", "ctx")]
    completed = events[-1]
    assert completed.data["status"] == "partial"
    assert completed.data["summary"].strip()
    assert "本轮部分检查报告" in completed.content
    assert any(event.type is RuntimeEventType.TEXT for event in events)


@pytest.mark.anyio
async def test_blank_first_round_asks_model_to_summarize_observed_evidence():
    class BlankResultGraph:
        async def astream(self, *_args, **_kwargs):
            yield {"messages": []}

        async def aget_state(self, _config):
            return SimpleNamespace(values={"messages": [AIMessage(content="")]})

    class SummaryModel:
        def __init__(self):
            self.prompt = ""

        def bind(self, **_kwargs):
            return self

        async def astream(self, messages):
            self.prompt = messages[0].content
            yield SimpleNamespace(content="已枚举 Deployment；副本状态")
            yield SimpleNamespace(content="尚未逐项读取。")

    config = AgentRuntimeConfig(
        agent_id="ops", name="K8s Ops Agent", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    model = SummaryModel()
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=FakeSession(), model=model)
    agent._tools_loaded = True
    agent._graph = BlankResultGraph()

    events = [event async for event in agent.stream("审查 Deployment", "ctx")]
    assert events[-1].data["status"] == "partial"
    assert events[-1].data["summary"] == "已枚举 Deployment；副本状态尚未逐项读取。"
    assert "禁止调用任何工具" in model.prompt
    assert "本轮正式的部分检查报告" in model.prompt
    assert [event.content for event in events if event.type is RuntimeEventType.TEXT]


@pytest.mark.anyio
async def test_agent_diagnostics_probe_model_and_mcp_independently():
    class ProbeMCP:
        async def list_tools(self):
            return [{"name": "list_k8s_pod"}]

    class ProbeModel:
        async def ainvoke(self, _messages):
            return AIMessage(content="OK")

        def bind(self, **_kwargs):
            return self

    config = AgentRuntimeConfig(
        agent_id="ops", name="K8s Ops Agent", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(
        config, "prompt", mcp_client=ProbeMCP(), model=ProbeModel()
    )

    result = await agent.probe_connections(timeout=1)

    assert result["agent_id"] == "ops"
    assert result["model"]["state"] == "ok"
    assert result["mcp"]["state"] == "ok"
    assert result["mcp"]["tool_count"] == 1
    assert "response" not in result["model"]


@pytest.mark.anyio
async def test_agent_diagnostics_keeps_mcp_result_when_model_fails():
    class ProbeMCP:
        async def list_tools(self):
            return [{"name": "list_k8s_pod"}]

    class FailingModel:
        async def ainvoke(self, _messages):
            raise RuntimeError("local model unavailable")

        def bind(self, **_kwargs):
            return self

    config = AgentRuntimeConfig(
        agent_id="security", name="Security", port=8053,
        public_url="http://security", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(
        config, "prompt", mcp_client=ProbeMCP(), model=FailingModel()
    )

    result = await agent.probe_connections(timeout=1)

    assert result["model"] == {
        "state": "error", "latency_ms": result["model"]["latency_ms"],
        "error": "local model unavailable",
    }
    assert result["mcp"]["state"] == "ok"


@pytest.mark.anyio
async def test_agent_mcp_only_diagnostic_does_not_call_model():
    class ForbiddenModel:
        def bind(self, **_kwargs):
            raise AssertionError("MCP-only diagnostics must not touch the model")

    class ProbeMCP:
        async def list_tools(self):
            return [{"name": "list_k8s_pod"}]

    config = AgentRuntimeConfig(
        agent_id="ops", name="Ops", port=8052,
        public_url="http://ops", mcp_url="http://mcp/sse",
    )
    agent = RuntimeMCPAgent(
        config, "prompt", mcp_client=ProbeMCP(), model=ForbiddenModel()
    )

    result = await agent.probe_connections(timeout=1, target="mcp")

    assert result["mcp"]["state"] == "ok"
    assert "model" not in result


@pytest.mark.anyio
async def test_mcp_diagnostic_reports_actual_tools_and_policy_access():
    class ProbeMCP:
        async def list_tools(self):
            return [
                {"name": "inspect_item", "description": "Read one item"},
                {"name": "change_item", "description": "Update one item"},
                {"name": "unknown_item", "description": "Unavailable to this agent"},
            ]

    config = AgentRuntimeConfig(
        agent_id="inspector", name="Inspector", port=8052,
        public_url="http://inspector", mcp_url="http://mcp/sse",
        tool_policy={"allow": ["inspect_*"], "approval_required": ["change_*"], "deny": []},
    )
    agent = RuntimeMCPAgent(config, "prompt", mcp_client=ProbeMCP())

    result = await agent.probe_connections(timeout=1, target="mcp")

    assert result["mcp"]["tool_count"] == 3
    assert [(item["name"], item["access"]) for item in result["mcp"]["tools"]] == [
        ("change_item", "approval_required"),
        ("inspect_item", "allow"),
        ("unknown_item", "deny"),
    ]
    assert result["mcp"]["callable_count"] == 2
