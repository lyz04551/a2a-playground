from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator


class PlannedTask(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    agent_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    input: str = ""
    depends_on: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(min_length=1)
    risk: Literal["read", "write"] = "read"
    required_skill: str | None = None
    required_tags: list[str] = Field(default_factory=list)
    workflow_role: Literal[
        "standard", "precheck", "mutation", "verification"
    ] = "standard"
    max_attempts: int = Field(default=2, ge=1, le=2)

    @field_validator("id", "agent_id", "objective")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class HostDecision(BaseModel):
    action: Literal[
        "delegate", "clarify", "request_approval", "complete", "stop"
    ]
    reason: str = Field(min_length=1)
    response: str = ""
    tasks: list[PlannedTask] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_action_payload(self):
        self.reason = self.reason.strip()
        self.response = self.response.strip()
        if not self.reason:
            raise ValueError("decision reason must not be blank")
        if self.action == "delegate":
            if not self.tasks:
                raise ValueError("delegate decisions require at least one task")
            if self.response:
                raise ValueError(
                    "delegate decisions must not include a Host response"
                )
        else:
            if self.tasks:
                raise ValueError(
                    f"{self.action} decisions must not include tasks"
                )
            if not self.response:
                raise ValueError(
                    f"{self.action} decisions require a Host response"
                )
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("decision task IDs must be unique")
        return self


class HostPlan(BaseModel):
    action: Literal["direct_response", "clarification", "delegate"] = "delegate"
    summary: str = Field(min_length=1)
    response: str = ""
    tasks: list[PlannedTask] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def validate_action_payload(self):
        self.response = self.response.strip()
        if self.action == "delegate":
            if not self.tasks:
                raise ValueError("delegate plans require at least one task")
            if self.response:
                raise ValueError("delegate plans must not include a direct response")
        else:
            if self.tasks:
                raise ValueError(f"{self.action} plans must not include tasks")
            if not self.response:
                raise ValueError(f"{self.action} plans require a response")
        return self


class Continuation(BaseModel):
    allowed: bool | None = None
    reason: str = ""


class SpecialistOutput(BaseModel):
    status: str = "completed"
    summary: str = ""
    findings: list[dict] = Field(default_factory=list)
    resources: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    continuation: Continuation = Field(default_factory=Continuation)
    limitations: list[str] = Field(default_factory=list)


class DelegationResult(BaseModel):
    state: Literal["completed", "failed", "approval_required"]
    text: str = ""
    output: SpecialistOutput | None = None
    approval: dict | None = None
    error: str = ""


class Evaluation(BaseModel):
    outcome: Literal["sufficient", "insufficient", "failed", "blocked"]
    reason: str


class ObservedTask(BaseModel):
    task: PlannedTask
    result: DelegationResult
    evaluation: Evaluation
    actual_agent_id: str = Field(min_length=1)


class HostRunState(BaseModel):
    goal: str = Field(min_length=1)
    round: int = Field(default=0, ge=0)
    decisions: list[HostDecision] = Field(default_factory=list)
    observations: dict[str, ObservedTask] = Field(default_factory=dict)
    successful: set[str] = Field(default_factory=set)
    task_fingerprints: set[str] = Field(default_factory=set)
    pending_approval_task_id: str | None = None
    total_tasks: int = Field(default=0, ge=0)


class DecisionPort(Protocol):
    async def decide_next(
        self,
        request: str,
        agents: list[dict],
        state: HostRunState,
    ) -> HostDecision: ...

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
