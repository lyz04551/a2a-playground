from __future__ import annotations

import asyncio

import pytest

from backend.host.orchestration.engine import HostOrchestrationEngine
from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostDecision,
    HostPlan,
    HostRunState,
    PlannedTask,
)


def test_delegation_result_accepts_structured_specialist_output():
    result = DelegationResult(
        state="completed",
        text="安全检查通过",
        output={
            "status": "completed",
            "summary": "安全检查通过",
            "continuation": {
                "allowed": True,
                "reason": "no blockers",
            },
        },
    )

    assert result.output is not None
    assert result.output.summary == "安全检查通过"
    assert result.output.continuation.allowed is True
    assert result.output.findings == []


@pytest.mark.anyio
async def test_explicit_structured_block_prevents_dependent_task():
    plan = HostPlan(
        summary="guarded change",
        tasks=[
            planned("security", "security"),
            planned("change", "orchestrator", depends_on=("security",)),
        ],
    )

    class StructuredDecisions(FakeDecisions):
        async def evaluate(self, task, result):
            if (
                result.output is not None
                and result.output.continuation.allowed is False
            ):
                return Evaluation(
                    outcome="blocked",
                    reason=result.output.continuation.reason,
                )
            return await super().evaluate(task, result)

    calls = []

    async def delegate(run_id, agent_id, prompt):
        calls.append(agent_id)
        return DelegationResult(
            state="completed",
            text="发现高风险配置",
            output={
                "summary": "发现高风险配置",
                "continuation": {
                    "allowed": False,
                    "reason": "privileged container",
                },
            },
        )

    events = await collect(HostOrchestrationEngine(
        FakeRegistry("security", "orchestrator"),
        StructuredDecisions(plan),
        delegate,
    ))

    assert calls == ["security"]
    assert any(
        event["type"] == "task_blocked"
        and event["task_id"] == "change"
        for event in events
    )


def planned(
    task_id: str,
    agent_id: str,
    *,
    depends_on: tuple[str, ...] = (),
) -> PlannedTask:
    return PlannedTask(
        id=task_id,
        agent_id=agent_id,
        objective=f"Complete {task_id}",
        depends_on=list(depends_on),
        completion_criteria=[f"{task_id} has evidence"],
    )


class FakeRegistry:
    def __init__(self, *agent_ids: str):
        self.profiles = {
            agent_id: {
                "id": agent_id,
                "name": agent_id,
                "read_only": True,
                "health": {"online": True},
            }
            for agent_id in agent_ids
        }

    def list(self):
        return list(self.profiles.values())

    def capability_profile(self, agent_id):
        return self.profiles.get(agent_id)

    def rank_candidates(self, *, skill, tags, risk, exclude=None):
        excluded = exclude or set()
        return [
            profile
            for agent_id, profile in self.profiles.items()
            if agent_id not in excluded
            and (risk != "write" or not profile["read_only"])
        ]


class NoReplacementRegistry(FakeRegistry):
    def rank_candidates(self, *, skill, tags, risk, exclude=None):
        return []


class FakeDecisions:
    def __init__(self, plan: HostPlan):
        self.plan = plan
        self.synthesis_results = None

    async def create_plan(self, request, agents):
        return self.plan

    async def evaluate(self, task, result):
        return Evaluation(outcome="sufficient", reason="criteria met")

    async def synthesize(self, request, plan, results):
        self.synthesis_results = results
        return "combined answer"


class ResultAwareDecisions(FakeDecisions):
    async def evaluate(self, task, result):
        if result.state == "approval_required":
            return Evaluation(outcome="blocked", reason="approval required")
        if result.state == "failed":
            return Evaluation(outcome="failed", reason=result.error)
        if result.text == "insufficient":
            return Evaluation(outcome="insufficient", reason="missing evidence")
        return Evaluation(outcome="sufficient", reason="criteria met")


async def collect(engine):
    return [event async for event in engine.stream("user request", "run-1")]


def test_mutation_prompt_requires_immediate_write_tool_after_precheck():
    task = planned("deploy-nginx", "orchestrator").model_copy(
        update={"risk": "write", "workflow_role": "mutation"}
    )

    prompt = HostOrchestrationEngine._react_task_prompt(
        "deploy nginx", task, HostRunState(goal="deploy nginx")
    )

    assert "immediately call the exact write tool" in prompt
    assert "Do not repeat cluster health, capacity, or security prechecks" in prompt


@pytest.mark.anyio
async def test_react_next_round_observes_results_before_deciding_again():
    class ReactDecisions:
        def __init__(self):
            self.states = []

        async def decide_next(self, request, agents, state):
            self.states.append(state.model_copy(deep=True))
            if state.round == 1:
                return HostDecision(
                    action="delegate",
                    reason="Run independent preflight checks",
                    tasks=[
                        planned("security-1", "security"),
                        planned("capacity-1", "capacity"),
                    ],
                )
            return HostDecision(
                action="clarify",
                reason="The target namespace is missing",
                response="是否允许创建 production namespace？",
            )

        async def evaluate(self, task, result):
            if result.output and result.output.continuation.allowed is False:
                return Evaluation(
                    outcome="blocked",
                    reason=result.output.continuation.reason,
                )
            return Evaluation(outcome="sufficient", reason="evidence returned")

    decisions = ReactDecisions()
    calls = []

    async def delegate(run_id, agent_id, prompt):
        calls.append(agent_id)
        if agent_id == "security":
            return DelegationResult(
                state="completed",
                text="production namespace does not exist",
                output={
                    "summary": "namespace missing",
                    "continuation": {
                        "allowed": False,
                        "reason": "production namespace does not exist",
                    },
                },
            )
        return DelegationResult(state="completed", text="capacity available")

    events = await collect(HostOrchestrationEngine(
        FakeRegistry("security", "capacity", "orchestrator"),
        decisions,
        delegate,
    ))

    assert set(calls) == {"security", "capacity"}
    assert set(decisions.states[1].observations) == {
        "security-1", "capacity-1"
    }
    assert [event["type"] for event in events if "round" in event["type"]] == [
        "round_started", "round_completed", "round_started"
    ]
    assert not any(event["type"] == "task_blocked" for event in events)
    assert any(
        event["type"] == "task_completed"
        and event["task_id"] == "security-1"
        and event["evaluation"]["outcome"] == "blocked"
        for event in events
    )
    assert not any(
        event["type"] == "task_failed"
        and event["task_id"] == "security-1"
        for event in events
    )
    assert events[-2] == {
        "type": "text",
        "text": "是否允许创建 production namespace？",
        "host_action": "clarify",
    }
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_react_tasks_in_one_round_execute_concurrently():
    both_started = asyncio.Event()
    started = 0

    class ReactDecisions:
        async def decide_next(self, request, agents, state):
            if state.round == 1:
                return HostDecision(
                    action="delegate",
                    reason="Parallel checks",
                    tasks=[planned("one", "one"), planned("two", "two")],
                )
            return HostDecision(
                action="complete",
                reason="Both checks completed",
                response="All checks completed",
            )

        async def evaluate(self, task, result):
            return Evaluation(outcome="sufficient", reason="complete")

    async def delegate(run_id, agent_id, prompt):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        return DelegationResult(state="completed", text=agent_id)

    events = await collect(HostOrchestrationEngine(
        FakeRegistry("one", "two"), ReactDecisions(), delegate
    ))

    assert sum(event["type"] == "task_completed" for event in events) == 2
    assert events[-2]["text"] == "All checks completed"


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["direct_response", "clarification"])
async def test_host_only_decision_never_delegates_evaluates_or_synthesizes(action):
    class HostOnlyDecisions(FakeDecisions):
        async def evaluate(self, task, result):
            raise AssertionError("host-only decisions must not evaluate child work")

        async def synthesize(self, request, plan, results):
            raise AssertionError("the planned Host response is already final")

    response = "你好！有什么可以帮助你的？" if action == "direct_response" else "请问你希望检查哪个集群？"
    decisions = HostOnlyDecisions(HostPlan(action=action, summary="host handles request", response=response, tasks=[]))

    async def delegate(*args):
        raise AssertionError("host-only decisions must not delegate")

    events = await collect(HostOrchestrationEngine(FakeRegistry("ops"), decisions, delegate))

    assert [event["type"] for event in events] == ["plan_created", "text", "done"]
    assert events[0]["action"] == action
    assert events[1]["text"] == response


@pytest.mark.anyio
async def test_one_node_plan_delegates_once_and_synthesizes():
    decisions = FakeDecisions(
        HostPlan(summary="inspect", tasks=[planned("inspect", "ops")])
    )
    calls = []

    async def delegate(run_id, agent_id, prompt):
        calls.append((run_id, agent_id, prompt))
        return DelegationResult(state="completed", text="healthy")

    events = await collect(
        HostOrchestrationEngine(FakeRegistry("ops"), decisions, delegate)
    )

    assert calls[0][:2] == ("run-1", "ops")
    assert [event["type"] for event in events] == [
        "plan_created",
        "context_prepared",
        "routing",
        "task_started",
        "task_evaluated",
        "task_completed",
        "synthesis_started",
        "text",
        "done",
    ]
    assert events[-2]["text"] == "combined answer"


@pytest.mark.anyio
async def test_independent_tasks_execute_concurrently():
    plan = HostPlan(
        summary="parallel",
        tasks=[planned("ops", "ops"), planned("security", "security")],
    )
    both_started = asyncio.Event()
    started = 0

    async def delegate(agent_id, prompt):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        return DelegationResult(state="completed", text=agent_id)

    events = await collect(
        HostOrchestrationEngine(
            FakeRegistry("ops", "security"), FakeDecisions(plan), delegate
        )
    )

    assert sum(event["type"] == "task_completed" for event in events) == 2


@pytest.mark.anyio
async def test_delegate_progress_is_streamed_before_task_completion():
    plan = HostPlan(summary="trace", tasks=[planned("inspect", "ops")])
    release = asyncio.Event()

    async def delegate(run_id, agent_id, prompt, on_event):
        await on_event({
            "type": "tool_call",
            "id": "call-1",
            "tool": "get_nodes",
            "args": {"token": "secret", "wide": True},
        })
        await release.wait()
        return DelegationResult(state="completed", text="healthy")

    engine = HostOrchestrationEngine(
        FakeRegistry("ops"), FakeDecisions(plan), delegate
    )
    stream = engine.stream("user request", "run-1")
    seen = []
    while True:
        event = await anext(stream)
        seen.append(event)
        if event["type"] == "tool_call":
            break

    assert seen[-1] == {
        "type": "tool_call",
        "task_id": "inspect",
        "agent_id": "ops",
        "id": "call-1",
        "tool": "get_nodes",
        "args": {"token": "secret", "wide": True},
    }
    assert not any(event["type"] == "task_completed" for event in seen)

    release.set()
    remaining = [event async for event in stream]
    assert any(event["type"] == "task_completed" for event in remaining)


@pytest.mark.anyio
async def test_unexpected_agent_exception_fails_only_that_parallel_task():
    plan = HostPlan(
        summary="partial",
        tasks=[planned("ops", "ops"), planned("security", "security")],
    )
    decisions = ResultAwareDecisions(plan)

    async def delegate(agent_id, prompt):
        if agent_id == "ops":
            raise TimeoutError("ops agent timed out")
        return DelegationResult(state="completed", text="security evidence")

    events = await collect(HostOrchestrationEngine(
        NoReplacementRegistry("ops", "security"), decisions, delegate,
    ))

    assert any(
        event["type"] == "task_failed"
        and event["task_id"] == "ops"
        and "timed out" in event["error"]
        for event in events
    )
    assert any(
        event["type"] == "task_completed" and event["task_id"] == "security"
        for event in events
    )
    assert decisions.synthesis_results["security"].text == "security evidence"
    assert decisions.synthesis_results["ops"].state == "failed"


@pytest.mark.anyio
async def test_concurrency_is_bounded():
    plan = HostPlan(
        summary="bounded",
        tasks=[planned(f"task-{i}", f"agent-{i}") for i in range(5)],
    )
    active = 0
    maximum = 0

    async def delegate(agent_id, prompt):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return DelegationResult(state="completed", text=agent_id)

    await collect(
        HostOrchestrationEngine(
            FakeRegistry(*(f"agent-{i}" for i in range(5))),
            FakeDecisions(plan),
            delegate,
            max_concurrency=3,
        )
    )

    assert maximum == 3


@pytest.mark.anyio
async def test_dependent_task_receives_only_dependency_context():
    plan = HostPlan(
        summary="serial",
        tasks=[
            planned("diagnose", "ops"),
            planned("unrelated", "security"),
            planned("remediate", "orchestrator", depends_on=("diagnose",)),
        ],
    )
    prompts = {}

    async def delegate(agent_id, prompt):
        prompts[agent_id] = prompt
        return DelegationResult(state="completed", text=f"{agent_id} finding")

    await collect(
        HostOrchestrationEngine(
            FakeRegistry("ops", "security", "orchestrator"),
            FakeDecisions(plan),
            delegate,
        )
    )

    assert "[diagnose / ops]" in prompts["orchestrator"]
    assert "ops finding" in prompts["orchestrator"]
    assert "security finding" not in prompts["orchestrator"]


@pytest.mark.anyio
async def test_invalid_plan_fails_before_delegation():
    plan = HostPlan(summary="invalid", tasks=[planned("inspect", "missing")])
    called = False

    async def delegate(agent_id, prompt):
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="unknown agent"):
        await collect(
            HostOrchestrationEngine(
                FakeRegistry("ops"), FakeDecisions(plan), delegate
            )
        )

    assert called is False


@pytest.mark.anyio
async def test_transient_failure_retries_once():
    plan = HostPlan(summary="retry", tasks=[planned("inspect", "ops")])
    calls = 0

    async def delegate(agent_id, prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            return DelegationResult(state="failed", error="temporary")
        return DelegationResult(state="completed", text="evidence")

    events = await collect(
        HostOrchestrationEngine(
            FakeRegistry("ops"), ResultAwareDecisions(plan), delegate
        )
    )

    assert calls == 2
    assert any(event["type"] == "task_retry_scheduled" for event in events)


@pytest.mark.anyio
async def test_completed_but_insufficient_result_is_not_expensively_retried():
    plan = HostPlan(summary="refine", tasks=[planned("inspect", "ops")])
    prompts = []

    async def delegate(agent_id, prompt):
        prompts.append(prompt)
        text = "insufficient" if len(prompts) == 1 else "evidence"
        return DelegationResult(state="completed", text=text)

    events = await collect(
        HostOrchestrationEngine(
            FakeRegistry("ops"), ResultAwareDecisions(plan), delegate
        )
    )

    assert len(prompts) == 1
    assert not any(
        event["type"] in {"task_retry_scheduled", "plan_revised"}
        for event in events
    )
    assert any(event["type"] == "task_failed" for event in events)


@pytest.mark.anyio
async def test_exhausted_agent_is_replaced_once():
    plan = HostPlan(summary="replace", tasks=[planned("inspect", "ops")])
    calls = []

    async def delegate(agent_id, prompt):
        calls.append(agent_id)
        if agent_id == "ops":
            return DelegationResult(state="failed", error="offline")
        return DelegationResult(state="completed", text="fallback evidence")

    events = await collect(
        HostOrchestrationEngine(
            FakeRegistry("ops", "fallback"),
            ResultAwareDecisions(plan),
            delegate,
        )
    )

    assert calls == ["ops", "ops", "fallback"]
    revised = next(event for event in events if event["type"] == "plan_revised")
    assert revised["replacement_agent_id"] == "fallback"


@pytest.mark.anyio
async def test_failed_predecessor_blocks_descendant_but_keeps_independent_result():
    plan = HostPlan(
        summary="partial",
        tasks=[
            planned("failed", "only-agent"),
            planned("independent", "healthy"),
            planned("dependent", "healthy", depends_on=("failed",)),
            planned("grandchild", "healthy", depends_on=("dependent",)),
        ],
    )
    calls = []
    decisions = ResultAwareDecisions(plan)

    async def delegate(agent_id, prompt):
        calls.append(agent_id)
        if agent_id == "only-agent":
            return DelegationResult(state="failed", error="unavailable")
        return DelegationResult(state="completed", text="useful")

    events = await collect(
        HostOrchestrationEngine(
            NoReplacementRegistry("only-agent", "healthy"), decisions, delegate
        )
    )

    assert "healthy" in calls
    assert sum(agent == "healthy" for agent in calls) == 1
    assert any(
        event["type"] == "task_blocked"
        and event["task_id"] == "dependent"
        for event in events
    )
    assert any(
        event["type"] == "task_blocked"
        and event["task_id"] == "grandchild"
        for event in events
    )
    assert decisions.synthesis_results["independent"].text == "useful"


@pytest.mark.anyio
async def test_approval_pauses_dependent_branch_without_marking_it_blocked():
    plan = HostPlan(
        summary="approval",
        tasks=[
            planned("change", "orchestrator"),
            planned("independent", "ops"),
            planned("verify", "ops", depends_on=("change",)),
        ],
    )

    async def delegate(agent_id, prompt):
        if agent_id == "orchestrator":
            return DelegationResult(
                state="approval_required", approval={"id": "approval-1"}
            )
        return DelegationResult(state="completed", text="read result")

    events = await collect(
        HostOrchestrationEngine(
            FakeRegistry("orchestrator", "ops"),
            ResultAwareDecisions(plan),
            delegate,
        )
    )

    assert any(event["type"] == "approval_required" for event in events)
    assert any(
        event["type"] == "task_completed"
        and event["task_id"] == "independent"
        for event in events
    )
    assert not any(
        event["type"] == "task_blocked" and event["task_id"] == "verify"
        for event in events
    )
    assert not any(
        event["type"] in {"synthesis_started", "done"}
        for event in events
    )


@pytest.mark.anyio
async def test_resume_continues_same_plan_after_approved_result():
    plan = HostPlan(
        summary="guarded deployment",
        tasks=[
            planned("security", "security"),
            planned(
                "change", "orchestrator", depends_on=("security",)
            ),
            planned("verify", "ops", depends_on=("change",)),
        ],
    )
    calls = []

    async def delegate(run_id, agent_id, prompt):
        calls.append(agent_id)
        if agent_id == "orchestrator":
            return DelegationResult(
                state="approval_required", approval={"id": "approval-1"}
            )
        return DelegationResult(
            state="completed", text=f"{agent_id} complete"
        )

    engine = HostOrchestrationEngine(
        FakeRegistry("security", "orchestrator", "ops"),
        ResultAwareDecisions(plan),
        delegate,
    )
    first = [
        event async for event in engine.stream("deploy nginx", "run-1")
    ]
    assert calls == ["security", "orchestrator"]
    assert any(event["type"] == "approval_required" for event in first)

    resumed = [
        event async for event in engine.stream(
            "deploy nginx",
            "run-1",
            plan=plan,
            initial_results={
                "security": DelegationResult(
                    state="completed", text="security complete"
                ),
                "change": DelegationResult(
                    state="completed", text="resource created"
                ),
            },
            initial_successful={"security", "change"},
        )
    ]

    assert calls == ["security", "orchestrator", "ops"]
    assert any(
        event["type"] == "task_completed"
        and event["task_id"] == "verify"
        for event in resumed
    )
    assert any(event["type"] == "synthesis_started" for event in resumed)
    assert resumed[-1]["type"] == "done"
