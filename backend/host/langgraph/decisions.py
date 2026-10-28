from __future__ import annotations

import asyncio
import json
import os
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError


from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostDecision,
    HostPlan,
    HostRunState,
    PlannedTask,
)
from backend.host.orchestration.validation import (
    PlanValidationError,
    validate_decision,
    validate_plan,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


def _compact_decision_state(state: HostRunState) -> dict:
    compact = state.model_dump(mode="json")
    for observation in compact.get("observations", {}).values():
        task = observation.get("task") or {}
        task["input"] = str(task.get("input") or "")[:2000]
        result = observation.get("result") or {}
        result["text"] = str(result.get("text") or "")[:1200]
        output = result.get("output") or {}
        output["summary"] = str(output.get("summary") or "")[:1800]
        output["evidence"] = [
            {**item, "result_excerpt": str(item.get("result_excerpt") or "")[:400]}
            for item in output.get("evidence", [])[-8:]
            if isinstance(item, dict)
        ]
        for field in ("findings", "resources", "recommendations", "limitations"):
            output[field] = output.get(field, [])[-8:]
        assessment = output.get("assessment") or {}
        for field in ("facts", "inferences", "unknowns"):
            assessment[field] = [
                {key: str(value)[:400] if isinstance(value, str) else value for key, value in item.items()}
                for item in assessment.get(field, [])[-8:]
                if isinstance(item, dict)
            ]
    return compact


def _response_language(request: str) -> str:
    return "zh-CN" if any("\u4e00" <= char <= "\u9fff" for char in request) else "en"


def _planning_agents(agents: list[dict]) -> list[dict]:
    """Keep the Host prompt limited to tools it may actually request."""
    return [
        {
            **agent,
            "tool_catalog": [
                tool for tool in agent.get("tool_catalog", [])
                if tool.get("access") in {"allow", "approval_required"}
            ],
        }
        for agent in agents
    ]


def _scoped_coverage(task: PlannedTask, coverage) -> dict:
    data = coverage.model_dump()
    kinds = set(task.coverage_kinds)
    if kinds:
        for field in ("expected_targets", "inspected_targets"):
            data[field] = [
                target for target in data[field]
                if target.split("/", 1)[0] in kinds
            ]
    return data


class LangGraphDecisionPort:
    def __init__(self, model=None, *, model_factory=None, stream_model_factory=None):
        self._model = model
        self._model_factory = model_factory
        self._stream_model_factory = stream_model_factory
        self._decision_timeout_seconds = float(
            os.getenv("HOST_DECISION_TIMEOUT_SECONDS", "45")
        )

    def _current_model(self):
        return self._model_factory() if self._model_factory else self._model

    def _current_stream_model(self):
        return self._stream_model_factory() if self._stream_model_factory else self._current_model()

    async def decide_next(
        self,
        request: str,
        agents: list[dict],
        state: HostRunState,
    ) -> HostDecision:
        compact_state = _compact_decision_state(state)
        for observation in compact_state.get("observations", {}).values():
            result = observation.get("result", {})
            output = result.get("output") or {}
            kinds = set((observation.get("task") or {}).get("coverage_kinds") or [])
            coverage = output.get("coverage")
            if kinds and isinstance(coverage, dict):
                for field in ("expected_targets", "inspected_targets"):
                    coverage[field] = [
                        target for target in coverage.get(field, [])
                        if target.split("/", 1)[0] in kinds
                    ]
                assessment = output.get("assessment") or {}
                assessment["unknowns"] = [
                    item for item in assessment.get("unknowns", [])
                    if str(item.get("resource_id") or "").split("/", 1)[0] in kinds
                ]
        payload = {
            "request": request,
            "response_language": _response_language(request),
            "available_agents": _planning_agents(agents),
            "state": compact_state,
        }
        instruction = """Choose exactly one next Host action from the persisted state.

- delegate: create one to three independent tasks for the current round. Tasks in
  this decision run in parallel. Each task must have all target information it
  needs before this round starts. If one task needs targets, evidence, or output
  discovered by another task, delegate only the prerequisite now; create the
  dependent task in a later round with the observed result and its task ID in
  depends_on. Parallel work is appropriate only when tasks have independent,
  explicitly scoped inputs, regardless of whether they use the same Agent.
  Do not speculate about future rounds. After a
  successful security precheck, delegate the write task to the capable Agent;
  the Agent's write tool creates and returns the real approval request.
- clarify: ask one essential question when the observations show that user intent
  or authority is missing. Resolve references and abbreviated follow-ups from the
  supplied conversation context and current structured state before clarifying;
  do not ask the user to repeat a value that has exactly one contextual referent.
- complete: answer only when the goal is satisfied and any mutation was verified.
- stop: terminate when continuing is unsafe or impossible.

Base the decision on structured observations, not keywords. Use only available
Agent IDs and declared capabilities. For tasks needing MCP calls, put exact
names from the selected Agent's tool_catalog in required_tools. Tools with
access=deny are unavailable. Every write task must name an approval_required
tool. If tool_catalog_state is unavailable, do not claim a tool exists.
Never repeat semantic work or a rejected
write. For a finite multi-target audit, set coverage_required=true on its
PlannedTask; the specialist must enumerate and account for the target set.
Set coverage_kinds to the resource kinds the user asked to inspect (for
example ["Deployment"]); discovery-only Cluster and Namespace metadata must
not count as audit targets unless the user requested those objects.
Never call such a task sufficient without complete coverage of the requested
resource kinds and evidence for every other completion criterion.
The specialist assessment.facts are runtime-recorded tool returns; interpret
their result excerpts before stating a resource fact. Treat inferences as
uncertain and assessment.unknowns as unresolved. Do not promote report prose
to a verified finding when its tool evidence is absent or contradictory.
Derive task completion criteria from the user's goal and available tool catalog.
State which observations would prove each criterion, and treat any missing
observation as unknown rather than as proof of a suspected cause.
For a continuation, carry forward the prior coverage target list and name only
the remaining targets in the new task input. Do not request another target
enumeration when the prior manifest says enumeration_complete=true for the
same scope; request a refresh only if freshness is relevant or prior evidence
is incomplete. Set continues_task_id to the prior task's ID whenever a task
continues an incomplete observation, even when a different Agent is now the
best capable choice. The Host will hand that Agent the prior tool evidence.
A mutation requires a successful Security precheck observation;
mutation and verification must never be delegated in the same round. Wait for a
successful mutation observation, then delegate verification to a capable Agent in the next round.
If verification proves the resource unhealthy or the write did not take effect,
one corrective mutation is allowed. Determine a valid correction from the live
resource schema and observed error; every write requires formal approval.
If a mutation observation is insufficient, delegate
the unmet remainder back to the same mutation-capable Agent; this continues the
logical correction and is not a new corrective mutation. Never send mutation work
to a read-only diagnostics Agent. Verify again after the correction. Return
only a concise public reason. The Host must never ask for write approval in text;
approval is created only by a delegated Agent's write tool.
An identical incomplete task may be continued only once. If the second result is
still transitional, empty, or reports a tool argument/schema error, stop and report
that state; do not poll or delegate the same mutation again. A tool validation error
is not a successful mutation and must not be described as completed.
An incomplete, partial, timed-out, or step-budget-limited verification is not proof
that the resource is unhealthy and must never justify a corrective mutation.
Use payload.response_language for every user-visible string. When it is zh-CN,
reason, response, task objective, task input, and completion criteria must all
be written in Chinese. Keep Agent IDs, tool names, and resource identifiers unchanged.
Do not reveal hidden chain-of-thought."""
        try:
            profiles = {agent["id"]: agent for agent in agents}
            for semantic_attempt in range(2):
                decision = await self._invoke_structured(
                    HostDecision, instruction, payload
                )
                try:
                    self._validate_reason_history(decision, state)
                    return validate_decision(decision, profiles, state)
                except PlanValidationError as exc:
                    if semantic_attempt:
                        raise
                    payload = {
                        **payload,
                        "previous_decision_error": str(exc),
                        "previous_decision": decision.model_dump(
                            mode="json"
                        ),
                        "correction": (
                            "This is a validation retry for the current decision, "
                            "not a previous Host round or prior run. Choose a "
                            "different action that satisfies the deterministic "
                            "guardrail. Do not repeat the rejected decision or "
                            "invent prior events."
                        ),
                    }
            raise AssertionError("unreachable semantic decision loop")
        except Exception as exc:
            raise RuntimeError(
                "Unable to create a valid Host decision"
            ) from exc

    @staticmethod
    def _validate_reason_history(
        decision: HostDecision, state: HostRunState
    ) -> None:
        """Reject invented history when the run has no prior Host decision."""
        if state.decisions or state.observations:
            return
        reason = decision.reason.casefold()
        invented_history_markers = (
            "上一轮",
            "前一轮",
            "previous round",
            "last round",
            "earlier round",
        )
        if any(marker in reason for marker in invented_history_markers):
            raise PlanValidationError(
                "the current decision is the first Host round; its public "
                "reason must not claim a previous round or prior failure"
            )

    async def create_plan(
        self, request: str, agents: list[dict]
    ) -> HostPlan:
        payload = {"request": request, "available_agents": _planning_agents(agents)}
        try:
            plan = await self._invoke_structured(
                HostPlan,
                """Choose exactly one Host action and return it as JSON.

- direct_response: respond directly when no registered Agent capability, external
  observation, or execution is needed. Put the complete user-facing answer in response
  and return an empty tasks list.
- clarification: ask one concise question when essential information is missing and
  different answers would materially change the work. Put that question in response
  and return an empty tasks list.
- delegate: use registered Agents when their specialist capability, external evidence,
  or execution is needed. Leave response empty and create one task for simple work,
  using multiple tasks only when necessary.

Decide from the request and available capabilities; do not classify by fixed keywords.
Independent tasks may share no dependencies; serial tasks must name their
dependencies. Use only stable agent IDs from available_agents. Never assign
write work to a read-only Agent. The Host performs the final synthesis, so do
not create a task whose sole purpose is combining or summarizing other task
results. Every delegated task must declare the most specific required_skill
from the selected Agent card, relevant required_tags, and a workflow_role.
For tasks needing MCP calls, list exact names from the selected Agent's
tool_catalog in required_tools; denied tools are unavailable. Every write
task must name an approval_required tool. If the catalog is unavailable,
do not claim a specific tool exists.
For a mutation, create a Security Agent precheck task
using its declared security skill, then a mutation task depending on it with
risk set to write, then a verification task depending on the mutation.
A resource-conflict check does not replace the Security Agent precheck.
Derive concrete completion criteria and required tools for each task from the
request and the selected Agent's live catalog.
Maximum six tasks and two attempts each.""",
                payload,
            )
            profiles = {agent["id"]: agent for agent in agents}
            return validate_plan(plan, profiles)
        except Exception as exc:
            raise RuntimeError("Unable to create a valid Host plan") from exc

    async def evaluate(
        self, task: PlannedTask, result: DelegationResult
    ) -> Evaluation:
        if result.state == "approval_required":
            return Evaluation(
                outcome="blocked", reason="approval required"
            )
        if result.state == "failed":
            return Evaluation(
                outcome="failed",
                reason=result.error or "delegated Agent failed",
            )
        if (
            result.output is not None
            and result.output.continuation.allowed is False
        ):
            return Evaluation(
                outcome="blocked",
                reason=(
                    result.output.continuation.reason
                    or result.output.summary
                    or "specialist Agent blocked continuation"
                ),
            )
        if result.output is not None and result.output.status == "partial":
            return Evaluation(
                outcome="insufficient",
                reason=(
                    "partial specialist result does not satisfy all completion "
                    "criteria; retain its evidence and explicitly report missing coverage"
                ),
            )
        if task.coverage_required and (result.output is None or result.output.coverage is None):
            return Evaluation(outcome="insufficient", reason="runtime tool evidence is unavailable")
        if task.coverage_required and result.output is not None and result.output.coverage is not None:
            coverage = result.output.coverage
            scoped = _scoped_coverage(task, coverage)
            expected = set(scoped["expected_targets"])
            inspected = set(scoped["inspected_targets"])
            missing = sorted(expected - inspected)
            scoped_complete = (
                bool(coverage.evidence_call_ids)
                and coverage.enumeration_complete
                and not missing
            )
            if not scoped_complete:
                reason = "target enumeration is incomplete" if not coverage.enumeration_complete else "runtime target coverage is incomplete"
                if missing:
                    reason += f"; unverified targets: {', '.join(missing[:20])}"
                return Evaluation(
                    outcome="insufficient",
                    reason=reason,
                )
        return await self._invoke_structured(
            Evaluation,
            """Evaluate the Agent result against the completion criteria.
Return JSON with outcome sufficient, insufficient, failed, or blocked and a
concise reason. Check each completion criterion against actual tool evidence;
report missing observations explicitly. Model prose alone is not evidence.
Approval-required work is blocked, never sufficient.""",
            {"task": task.model_dump(), "result": result.model_dump()},
        )

    async def synthesize(
        self,
        request: str,
        plan: HostPlan,
        results: dict[str, DelegationResult],
    ) -> str:
        return "".join([
            chunk async for chunk in self.synthesize_stream(request, plan, results)
        ])

    async def synthesize_stream(
        self,
        request: str,
        plan: HostPlan,
        results: dict[str, DelegationResult],
    ):
        messages = [
                SystemMessage(content=(
                    "你是 Host Agent。根据结构化计划和各子任务终态，用中文"
                    "直接回答用户。按已验证事实、推断、未知项区分结论；"
                    "已验证事实必须可追溯到 assessment.facts 的真实工具调用；"
                    "推断需说明依据和不确定性，未知项不得补写为事实。"
                    "明确失败、阻塞和冲突；"
                    "没有执行证据时不得声称写操作已经完成。"
                )),
                HumanMessage(content=json.dumps(
                    {
                        "request": request,
                        "plan": plan.model_dump(),
                        "results": {
                            task_id: result.model_dump()
                            for task_id, result in results.items()
                        },
                    },
                    ensure_ascii=False,
                )),
        ]
        async for response in self._current_stream_model().astream(messages):
            content = response.content
            if isinstance(content, str) and content:
                yield content

    async def synthesize_react(
        self,
        request: str,
        state: HostRunState,
        decision: HostDecision,
    ) -> str:
        return "".join([
            chunk async for chunk in self.synthesize_react_stream(request, state, decision)
        ])

    async def synthesize_react_stream(
        self,
        request: str,
        state: HostRunState,
        decision: HostDecision,
    ):
        """Write the Host's final answer from all observed specialist work."""
        observations = []
        for task_id, observed in state.observations.items():
            output = observed.result.output
            observations.append({
                "task_id": task_id,
                "agent_id": observed.actual_agent_id,
                "objective": observed.task.objective,
                "completion_criteria": observed.task.completion_criteria,
                "evaluation": observed.evaluation.model_dump(),
                "result_state": observed.result.state,
                "summary": (output.summary if output else observed.result.text)[:2500],
                "limitations": output.limitations if output else [],
                "coverage": _scoped_coverage(observed.task, output.coverage) if output and output.coverage else None,
                "assessment": output.assessment.model_dump() if output else None,
                "evidence": [
                    {
                        "call_id": item.get("call_id"),
                        "tool": item.get("tool"),
                        "resource_ids": item.get("resource_ids", []),
                        "result_state": item.get("result_state"),
                        "result_excerpt": str(item.get("result_excerpt") or "")[:800],
                    }
                    for item in (output.evidence[:12] if output else [])
                    if isinstance(item, dict)
                ],
            })
        payload = {
            "request": request,
            "final_action": decision.action,
            "decision_reason": decision.reason,
            "observations": observations,
        }
        messages = [
            SystemMessage(content=(
                "你是 Host Agent。现在根据所有轮次的子 Agent 结果，直接给用户写最终总结。"
                "先判断原始目标是否完成，再汇总有真实工具证据支持的结论、需要关注的对象和仍未知的项目。"
                "子 Agent 的文字报告是线索，不能替代工具证据；不要把未读取对象写成已验证。"
                "若评估仍为 insufficient、failed 或 blocked，明确说明部分完成或受阻，"
                "不要声称全量完成。不要照抄评估器的英文内部原因或生成固定模板。"
                "只回答用户，不输出 JSON。按用户请求的语言回答。"
            )),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        received = False
        async for response in self._current_stream_model().astream(messages):
            content = response.content
            if isinstance(content, str) and content:
                received = True
                yield content
        if not received:
            raise RuntimeError("Host final synthesis was empty")

    async def _invoke_structured(
        self,
        schema: type[ModelT],
        instruction: str,
        payload: dict,
    ) -> ModelT:
        schema_json = json.dumps(
            schema.model_json_schema(), ensure_ascii=False
        )
        messages = [
            SystemMessage(content=(
                f"{instruction}\n\nJSON Schema:\n{schema_json}\n\n"
                "Return only one JSON object matching this schema exactly."
            )),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        error = ""
        async with asyncio.timeout(self._decision_timeout_seconds):
            for attempt in range(2):
                current = list(messages)
                if attempt:
                    current.append(HumanMessage(content=(
                        f"The previous response was invalid: {error}. "
                        "Return only corrected JSON."
                    )))
                response = await self._current_model().ainvoke(current)
                try:
                    content = str(response.content).strip()
                    if content.startswith("```") and content.endswith("```"):
                        content = content[3:-3].strip()
                        if content.startswith("json"):
                            content = content[4:].lstrip()
                    raw = json.loads(content)
                    return schema.model_validate(raw)
                except (json.JSONDecodeError, TypeError, ValidationError) as exc:
                    error = str(exc)
        raise RuntimeError(f"Model did not return valid {schema.__name__}")
