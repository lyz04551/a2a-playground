from __future__ import annotations

import json

import pytest
from a2a.types import AgentCapabilities, AgentCard
from langchain_core.messages import AIMessage

from backend.host.adk.agent import HostAgent
from backend.host.adk.decisions import ADKDecisionPort
from backend.host.orchestration.models import DelegationResult, PlannedTask


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


class FakeModel:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def ainvoke(self, messages):
        return AIMessage(content=self.responses.pop(0))


def test_adk_host_keeps_duplicate_names_by_stable_id():
    host = HostAgent()

    host.register_agent_card("ops-a", card("K8s Agent", "http://ops"))
    host.register_agent_card(
        "security-a", card("K8s Agent", "http://security")
    )

    assert set(host.cards) == {"ops-a", "security-a"}
    assert set(host.remote_connections) == {"ops-a", "security-a"}


@pytest.mark.anyio
async def test_adk_decisions_use_shared_plan_and_evaluation_contracts():
    model = FakeModel(
        json.dumps({
            "summary": "inspect",
            "tasks": [{
                "id": "inspect",
                "agent_id": "ops",
                "objective": "inspect pod",
                "completion_criteria": ["evidence"],
            }],
        }),
        json.dumps({"outcome": "sufficient", "reason": "evidence"}),
    )
    port = ADKDecisionPort(model)
    agents = [{"id": "ops", "read_only": True, "skills": []}]

    plan = await port.create_plan("inspect", agents)
    evaluation = await port.evaluate(
        PlannedTask(
            id="inspect",
            agent_id="ops",
            objective="inspect",
            completion_criteria=["evidence"],
        ),
        DelegationResult(state="completed", text="healthy"),
    )

    assert plan.tasks[0].agent_id == "ops"
    assert evaluation.outcome == "sufficient"
