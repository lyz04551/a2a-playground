from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator


class PlannedTask(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    agent_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    input: str = ""
    depends_on: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(min_length=1)
    risk: Literal["read", "write"] = "read"
    max_attempts: int = Field(default=2, ge=1, le=2)

    @field_validator("id", "agent_id", "objective")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class HostPlan(BaseModel):
    summary: str = Field(min_length=1)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=6)


class DelegationResult(BaseModel):
    state: Literal["completed", "failed", "approval_required"]
    text: str = ""
    approval: dict | None = None
    error: str = ""


class Evaluation(BaseModel):
    outcome: Literal["sufficient", "insufficient", "failed", "blocked"]
    reason: str


class DecisionPort(Protocol):
    async def create_plan(
        self, request: str, agents: list[dict]
    ) -> HostPlan: ...

    async def evaluate(
        self, task: PlannedTask, result: DelegationResult
    ) -> Evaluation: ...

    async def synthesize(
        self,
        request: str,
        plan: HostPlan,
        results: dict[str, DelegationResult],
    ) -> str: ...
