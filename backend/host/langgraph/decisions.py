from __future__ import annotations

import json
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from backend.host.orchestration.models import (
    DelegationResult,
    Evaluation,
    HostPlan,
    PlannedTask,
)
from backend.host.orchestration.validation import validate_plan


ModelT = TypeVar("ModelT", bound=BaseModel)


class LangGraphDecisionPort:
    def __init__(self, model):
        self._model = model

    async def create_plan(
        self, request: str, agents: list[dict]
    ) -> HostPlan:
        payload = {"request": request, "available_agents": agents}
        try:
            plan = await self._invoke_structured(
                HostPlan,
                """Create a bounded Host orchestration plan as JSON.
Use one task for simple requests and multiple tasks only when necessary.
Independent tasks may share no dependencies; serial tasks must name their
dependencies. Use only stable agent IDs from available_agents. Never assign
write work to a read-only Agent. The Host performs the final synthesis, so do
not create a task whose sole purpose is combining or summarizing other task
results. Maximum six tasks and two attempts each.""",
                payload,
            )
            profiles = {agent["id"]: agent for agent in agents}
            return validate_plan(plan, profiles)
        except Exception as exc:
            raise RuntimeError("Unable to create a valid Host plan") from exc

    async def evaluate(
        self, task: PlannedTask, result: DelegationResult
    ) -> Evaluation:
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
