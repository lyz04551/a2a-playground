from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage

from backend.host.langgraph.decisions import LangGraphDecisionPort
from backend.host.orchestration.engine import _terminal_response
from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostRunState,
    ObservedTask,
    PlannedTask,
)


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


class HangingModel:
    async def ainvoke(self, _messages):
        await asyncio.Event().wait()


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
async def test_narrow_task_can_complete_with_incomplete_incidental_enumeration():
    model = FakeModel('{"outcome":"sufficient","reason":"named Pod was inspected"}')
    port = LangGraphDecisionPort(model=model)
    task = PlannedTask(id="pod", agent_id="ops", objective="Inspect pod-a", completion_criteria=["pod-a inspected"])
    result = DelegationResult(state="completed", output={
        "summary": "pod-a inspected",
        "coverage": {
            "scope": "observed MCP resources", "expected_targets": ["Pod/default/pod-a", "Pod/default/pod-b"],
            "inspected_targets": ["Pod/default/pod-a"], "enumeration_complete": True,
            "evidence_call_ids": ["list-1", "read-1"],
        },
    })
    evaluation = await port.evaluate(task, result)
    assert evaluation.outcome == "sufficient"


@pytest.mark.anyio
async def test_required_coverage_reports_runtime_evidence_gap_without_model_call():
    port = LangGraphDecisionPort(model=FakeModel())
    task = PlannedTask(id="audit", agent_id="ops", objective="Inspect all Pods", completion_criteria=["all Pods inspected"], coverage_required=True)
    result = DelegationResult(state="completed", output={
        "summary": "checked one Pod", "coverage": {
            "scope": "observed MCP resources", "expected_targets": ["Pod/default/a", "Pod/default/b"],
            "inspected_targets": ["Pod/default/a"], "enumeration_complete": True,
            "evidence_call_ids": ["list-1", "read-1"],
        },
    })
    evaluation = await port.evaluate(task, result)
    assert evaluation.outcome == "insufficient"
    assert "Pod/default/b" in evaluation.reason


@pytest.mark.anyio
async def test_model_evaluates_task_specific_criteria_from_tool_evidence():
    model = FakeModel('{"outcome":"insufficient","reason":"status and events were not observed"}')
    port = LangGraphDecisionPort(model=model)
    task = PlannedTask(id="pod", agent_id="ops", objective="Diagnose Pending Pod", completion_criteria=["status and events reviewed"])
    result = DelegationResult(state="completed", output={
        "summary": "likely NFS issue",
        "evidence": [{"tool": "describe_k8s_pod", "resource_ids": ["Pod/default/pod-a"], "result_state": "returned", "call_id": "read-1"}],
    })
    evaluation = await port.evaluate(task, result)
    assert evaluation.outcome == "insufficient"
    assert "status and events" in evaluation.reason
    assert "describe_k8s_pod" in str(model.calls[0])


def test_host_final_response_cannot_claim_full_coverage_after_insufficient_evaluation():
    task = PlannedTask(
        id="audit", agent_id="ops", objective="检查全部对象",
        completion_criteria=["逐一验证"], coverage_required=True,
    )
    state = HostRunState(goal="检查全部对象", observations={
        task.id: ObservedTask(
            task=task,
            result=DelegationResult(state="completed", text="声称全部检查完毕"),
            evaluation=Evaluation(outcome="insufficient", reason="runtime tool evidence is unavailable"),
            actual_agent_id="ops",
        ),
    })

    final = _terminal_response("检查全部对象", state, "全部对象已检查，任务完成")

    assert final.startswith("本次任务部分完成")
    assert "runtime tool evidence is unavailable" in final
    assert "全部对象已检查，任务完成" not in final


@pytest.mark.anyio
async def test_decide_next_receives_prior_structured_observations():
    security_task = PlannedTask(
        id="security-1",
        agent_id="security",
        objective="Review nginx",
        completion_criteria=["Return continuation decision"],
        workflow_role="precheck",
    )
    state = HostRunState(
        goal="deploy nginx",
        round=1,
        observations={
            security_task.id: ObservedTask(
                task=security_task,
                result=DelegationResult(
                    state="completed",
                    text="production namespace does not exist",
                    output={
                        "summary": "namespace missing",
                        "continuation": {
                            "allowed": False,
                            "reason": "production namespace does not exist",
                        },
                    },
                ),
                evaluation=Evaluation(
                    outcome="blocked", reason="namespace missing"
                ),
                actual_agent_id="security",
            )
        },
    )
    model = FakeModel(json.dumps({
        "action": "clarify",
        "reason": "Creating the namespace needs authorization",
        "response": "是否允许创建 production namespace？",
        "tasks": [],
    }))

    decision = await LangGraphDecisionPort(model).decide_next(
        "deploy nginx", AGENTS, state
    )

    assert decision.action == "clarify"
    sent = str(model.calls[0])
    assert "production namespace does not exist" in sent
    assert '"round": 1' in sent
    assert "one to three independent tasks" in sent
    assert "Do not reveal hidden chain-of-thought" in sent


@pytest.mark.anyio
async def test_decide_next_wraps_invalid_output_with_decision_error():
    model = FakeModel("bad", "still bad")

    with pytest.raises(
        RuntimeError, match="Unable to create a valid Host decision"
    ):
        await LangGraphDecisionPort(model).decide_next(
            "inspect", AGENTS, HostRunState(goal="inspect")
        )


@pytest.mark.anyio
async def test_partial_specialist_result_is_deterministically_insufficient():
    model = FakeModel()
    result = DelegationResult(
        state="completed",
        text="time budget reached",
        output={
            "status": "partial",
            "summary": "only some checks completed",
            "continuation": {
                "allowed": True,
                "reason": "investigation time budget reached",
            },
        },
    )

    evaluation = await LangGraphDecisionPort(model).evaluate(
        PlannedTask(
            id="verify",
            agent_id="ops",
            objective="verify resource health",
            completion_criteria=["health conclusively established"],
            workflow_role="verification",
        ),
        result,
    )

    assert evaluation.outcome == "insufficient"
    assert "partial" in evaluation.reason
    assert model.calls == []


@pytest.mark.anyio
async def test_partial_diagnostic_with_summary_remains_insufficient():
    model = FakeModel()
    result = DelegationResult(
        state="completed",
        text="time budget reached",
        output={
            "status": "partial",
            "summary": "memory-hog restarted repeatedly; remaining checks were not run",
            "continuation": {
                "allowed": True,
                "reason": "investigation time budget reached",
            },
        },
    )

    evaluation = await LangGraphDecisionPort(model).evaluate(
        PlannedTask(
            id="inspect",
            agent_id="ops",
            objective="inspect cluster health",
            completion_criteria=["report confirmed findings and limitations"],
            workflow_role="standard",
            risk="read",
        ),
        result,
    )

    assert evaluation.outcome == "insufficient"
    assert "missing coverage" in evaluation.reason
    assert model.calls == []


@pytest.mark.anyio
async def test_decide_next_retries_semantically_invalid_decision_with_feedback():
    agents = [
        *AGENTS,
        {
            "id": "orchestrator",
            "name": "Orchestrator",
            "read_only": False,
            "skills": [{"id": "resource.manage", "tags": ["resource"]}],
        },
    ]
    model = FakeModel(
        json.dumps({
            "action": "delegate",
            "reason": "Create the workload",
            "tasks": [{
                "id": "change",
                "agent_id": "orchestrator",
                "objective": "Create nginx",
                "completion_criteria": ["Deployment created"],
                "risk": "write",
                "workflow_role": "mutation",
            }],
        }),
        json.dumps({
            "action": "stop",
            "reason": "Security continuation was not explicitly allowed",
            "response": "安全检查没有明确允许继续，已停止部署。",
            "tasks": [],
        }),
    )

    decision = await LangGraphDecisionPort(model).decide_next(
        "deploy nginx", agents, HostRunState(goal="deploy nginx")
    )

    assert decision.action == "stop"
    assert len(model.calls) == 2
    assert "successful security precheck" in str(model.calls[1])


@pytest.mark.anyio
async def test_first_round_rejects_invented_previous_round_history():
    model = FakeModel(
        json.dumps({
            "action": "delegate",
            "reason": "上一轮因缺少安全预检结果而失败，本轮先执行安全预检。",
            "tasks": [{
                "id": "security",
                "agent_id": "ops",
                "objective": "执行安全预检",
                "completion_criteria": ["返回预检结果"],
                "workflow_role": "precheck",
            }],
        }, ensure_ascii=False),
        json.dumps({
            "action": "delegate",
            "reason": "创建 Pod 前需要先完成安全预检。",
            "tasks": [{
                "id": "security",
                "agent_id": "ops",
                "objective": "执行安全预检",
                "completion_criteria": ["返回预检结果"],
                "workflow_role": "precheck",
            }],
        }, ensure_ascii=False),
    )

    decision = await LangGraphDecisionPort(model).decide_next(
        "创建 nginx Pod", AGENTS, HostRunState(goal="创建 nginx Pod")
    )

    assert decision.reason == "创建 Pod 前需要先完成安全预检。"
    assert len(model.calls) == 2
    assert "current decision" in str(model.calls[1])


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["direct_response", "clarification"])
async def test_langgraph_decision_port_accepts_host_only_decisions(action):
    model = FakeModel(json.dumps({
        "action": action,
        "summary": "Host handles this request",
        "response": "你好！有什么可以帮助你的？" if action == "direct_response" else "请问你希望检查哪个集群？",
        "tasks": [],
    }))

    plan = await LangGraphDecisionPort(model).create_plan("你好", AGENTS)

    assert plan.action == action
    assert plan.response
    assert plan.tasks == []
    assert "do not classify by fixed keywords" in str(model.calls[0])


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


@pytest.mark.anyio
async def test_langgraph_decision_port_honors_explicit_structured_block_without_model():
    model = FakeModel()
    port = LangGraphDecisionPort(model)
    task = PlannedTask(
        id="security",
        agent_id="security",
        objective="review manifest",
        completion_criteria=["blocking findings identified"],
    )
    result = DelegationResult(
        state="completed",
        text="privileged container detected",
        output={
            "summary": "privileged container detected",
            "continuation": {
                "allowed": False,
                "reason": "privileged container",
            },
        },
    )

    evaluation = await port.evaluate(task, result)

    assert evaluation.outcome == "blocked"
    assert evaluation.reason == "privileged container"
    assert model.calls == []


@pytest.mark.anyio
async def test_structured_host_decision_has_hard_total_timeout(monkeypatch):
    monkeypatch.setenv("HOST_DECISION_TIMEOUT_SECONDS", "0.01")
    port = LangGraphDecisionPort(HangingModel())
    task = PlannedTask(
        id="inspect",
        agent_id="ops",
        objective="inspect",
        completion_criteria=["evidence"],
    )

    with pytest.raises(TimeoutError):
        await port.evaluate(
            task,
            DelegationResult(state="completed", text="incomplete"),
        )
