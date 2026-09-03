from __future__ import annotations

import json
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


def _response_language(request: str) -> str:
    return "zh-CN" if any("\u4e00" <= char <= "\u9fff" for char in request) else "en"


class LangGraphDecisionPort:
    def __init__(self, model):
        self._model = model

    async def decide_next(
        self,
        request: str,
        agents: list[dict],
        state: HostRunState,
    ) -> HostDecision:
        compact_state = state.model_dump(mode="json")
        for observation in compact_state.get("observations", {}).values():
            result = observation.get("result", {})
            result["text"] = str(result.get("text") or "")[:2000]
        payload = {
            "request": request,
            "response_language": _response_language(request),
            "available_agents": agents,
            "state": compact_state,
        }
        instruction = """Choose exactly one next Host action from the persisted state.

- delegate: create one to three independent tasks for the current round. Tasks in
  this decision run in parallel. Do not speculate about future rounds. After a
  successful security precheck, delegate the write task to the capable Agent;
  the Agent's write tool creates and returns the real approval request.
- clarify: ask one essential question when the observations show that user intent
  or authority is missing.
- complete: answer only when the goal is satisfied and any mutation was verified.
- stop: terminate when continuing is unsafe or impossible.

Base the decision on structured observations, not keywords. Use only available
Agent IDs and declared capabilities. Never repeat semantic work or a rejected
write. A Kubernetes mutation requires a successful Security precheck observation;
mutation and verification must never be delegated in the same round. Wait for a
successful mutation observation, then delegate Ops verification in the next round.
If verification proves the resource unhealthy or the write did not take effect,
one corrective mutation is allowed. For an existing Kubernetes Pod whose immutable
spec must change, instruct the write Agent to delete and recreate it; both writes
must go through formal approval. Verify again after the correction. Return
only a concise public reason. The Host must never ask for write approval in text;
approval is created only by a delegated Agent's write tool.
Use payload.response_language for every user-visible string. When it is zh-CN,
reason, response, task objective, task input, and completion criteria must all
be written in Chinese. Keep Agent IDs, tool names, and Kubernetes identifiers unchanged.
Do not reveal hidden chain-of-thought."""
        try:
            profiles = {agent["id"]: agent for agent in agents}
            for semantic_attempt in range(2):
                decision = await self._invoke_structured(
                    HostDecision, instruction, payload
                )
                try:
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
                            "Choose a different action that satisfies the "
                            "deterministic guardrail. Do not repeat the "
                            "rejected decision."
                        ),
                    }
            raise AssertionError("unreachable semantic decision loop")
        except Exception as exc:
            raise RuntimeError(
                "Unable to create a valid Host decision"
            ) from exc

    async def create_plan(
        self, request: str, agents: list[dict]
    ) -> HostPlan:
        payload = {"request": request, "available_agents": agents}
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
For a Kubernetes deployment mutation, create a Security Agent precheck task
using its declared security skill, then a mutation task depending on it with
risk set to write, then an Ops verification task depending on the mutation.
An Ops resource-conflict check does not replace the Security Agent precheck.
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
        return await self._invoke_structured(
            Evaluation,
            """Evaluate the Agent result against the completion criteria.
Return JSON with outcome sufficient, insufficient, failed, or blocked and a
concise reason. Approval-required work is blocked, never sufficient.""",
            {"task": task.model_dump(), "result": result.model_dump()},
        )

    async def synthesize(
        self,
        request: str,
        plan: HostPlan,
        results: dict[str, DelegationResult],
    ) -> str:
        response = await self._model.ainvoke(
            [
                SystemMessage(content=(
                    "你是 Host Agent。根据结构化计划和各子任务终态，用中文"
                    "直接回答用户。区分事实与建议，明确失败、阻塞和冲突；"
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
        )
        return str(response.content or "")

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
        for attempt in range(2):
            current = list(messages)
            if attempt:
                current.append(HumanMessage(content=(
                    f"The previous response was invalid: {error}. "
                    "Return only corrected JSON."
                )))
            response = await self._model.ainvoke(current)
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
