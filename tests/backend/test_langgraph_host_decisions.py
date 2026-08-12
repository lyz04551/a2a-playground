from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from backend.host.langgraph.decisions import LangGraphDecisionPort
from backend.host.orchestration.models import DelegationResult, PlannedTask


class FakeModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.responses.pop(0))


class SchemaAwareModel:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        request = str(messages)
        if "completion_criteria" not in request or '"summary"' not in request:
            return AIMessage(content=json.dumps({
                "tasks": [{
                    "id": "task_001",
                    "agent_id": "ops",
                    "intent": "inspect",
                    "prompt": "inspect",
                    "dependencies": [],
                }],
            }))
        return AIMessage(content=json.dumps({
            "summary": "inspect",
            "tasks": [{
                "id": "inspect",
                "agent_id": "ops",
                "objective": "inspect pod",
                "completion_criteria": ["evidence returned"],
            }],
        }))


AGENTS = [
    {
        "id": "ops",
        "name": "Ops",
        "skills": [{"id": "pod.diagnose", "tags": ["logs"]}],
        "read_only": True,
        "risk_level": "read_only",
        "limitations": ["cannot mutate"],
    }
]


@pytest.mark.anyio
async def test_langgraph_decision_port_parses_structured_plan():
    model = FakeModel(json.dumps({
        "summary": "inspect",
        "tasks": [{
            "id": "inspect",
            "agent_id": "ops",
            "objective": "inspect pod",
            "completion_criteria": ["evidence returned"],
        }],
    }))

    plan = await LangGraphDecisionPort(model).create_plan("inspect", AGENTS)

    assert plan.tasks[0].agent_id == "ops"
    sent = str(model.calls[0])
    assert "pod.diagnose" in sent
    assert "cannot mutate" in sent
    assert "Host performs the final synthesis" in sent


@pytest.mark.anyio
async def test_langgraph_decision_port_repairs_malformed_json_once():
    valid = json.dumps({
        "summary": "inspect",
        "tasks": [{
            "id": "inspect",
            "agent_id": "ops",
            "objective": "inspect pod",
            "completion_criteria": ["evidence returned"],
        }],
    })
    model = FakeModel("not json", valid)

    plan = await LangGraphDecisionPort(model).create_plan("inspect", AGENTS)

    assert plan.summary == "inspect"
    assert len(model.calls) == 2


@pytest.mark.anyio
async def test_langgraph_decision_port_supplies_schema_to_model():
    model = SchemaAwareModel()

    plan = await LangGraphDecisionPort(model).create_plan("inspect", AGENTS)

    assert plan.summary == "inspect"
    assert len(model.calls) == 1


@pytest.mark.anyio
async def test_langgraph_decision_port_accepts_fenced_json():
    payload = json.dumps({
        "summary": "inspect",
        "tasks": [{
            "id": "inspect",
            "agent_id": "ops",
            "objective": "inspect pod",
            "completion_criteria": ["evidence returned"],
        }],
    })
    model = FakeModel(f"```json\n{payload}\n```")

    plan = await LangGraphDecisionPort(model).create_plan("inspect", AGENTS)

    assert plan.tasks[0].id == "inspect"
    assert len(model.calls) == 1


@pytest.mark.anyio
async def test_langgraph_decision_port_stops_after_one_failed_repair():
    model = FakeModel("bad", "still bad")

    with pytest.raises(RuntimeError, match="Unable to create a valid Host plan"):
        await LangGraphDecisionPort(model).create_plan("inspect", AGENTS)

    assert len(model.calls) == 2


@pytest.mark.anyio
async def test_langgraph_decision_port_evaluates_and_synthesizes_normalized_results():
    model = FakeModel(
        json.dumps({"outcome": "sufficient", "reason": "has evidence"}),
        "综合结论",
    )
    port = LangGraphDecisionPort(model)
    task = PlannedTask(
        id="inspect",
        agent_id="ops",
        objective="inspect",
        completion_criteria=["evidence"],
    )
    result = DelegationResult(state="completed", text="pod healthy")

    evaluation = await port.evaluate(task, result)
    answer = await port.synthesize(
        "inspect",
        await LangGraphDecisionPort(FakeModel(json.dumps({
            "summary": "inspect",
            "tasks": [task.model_dump()],
        }))).create_plan("inspect", AGENTS),
        {"inspect": result},
    )

    assert evaluation.outcome == "sufficient"
    assert answer == "综合结论"
    synthesis_payload = str(model.calls[1])
    assert "pod healthy" in synthesis_payload
    assert "tool transcript" not in synthesis_payload
