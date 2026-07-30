from __future__ import annotations

import pytest
from a2a.types import AgentCard, AgentCapabilities

from backend.host.langgraph.agent import LangGraphHostAgent


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def delegate(self, run_id, agent, message):
        self.calls.append((run_id, agent["id"], message))
        return {"text": f"{agent['id']} result"}


def card(name, url):
    return AgentCard(
        name=name,
        description="",
        url=url,
        version="1.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[],
    )


def test_registering_unchanged_agent_keeps_host_graph_memory():
    host = LangGraphHostAgent(gateway=FakeGateway())
    agent_card = card("K8s Agent", "http://ops")
    host.register_agent_card("ops-a", agent_card)
    graph = object()
    host._graph = graph

    host.register_agent_card("ops-a", agent_card)

    assert host._graph is graph


@pytest.mark.anyio
async def test_host_routes_duplicate_names_by_stable_agent_id():
    gateway = FakeGateway()
    host = LangGraphHostAgent(gateway=gateway)
    host.register_agent_card("ops-a", card("K8s Agent", "http://ops"))
    host.register_agent_card(
        "orchestrator-a",
        card("K8s Agent", "http://orchestrator"),
    )
    host.set_current_run("run-1")
    tools = {tool.name: tool for tool in host._make_tools()}

    listed = await tools["list_remote_agents"].ainvoke({})
    result = await tools["send_task"].ainvoke(
        {"agent_id": "orchestrator-a", "message": "scale api"}
    )

    assert {item["id"] for item in listed} == {
        "ops-a",
        "orchestrator-a",
    }
    assert result == "orchestrator-a result"
    assert gateway.calls == [
        ("run-1", "orchestrator-a", "scale api")
    ]
