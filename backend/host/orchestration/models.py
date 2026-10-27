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
    coverage_required: bool = False
    risk: Literal["read", "write"] = "read"
    required_skill: str | None = None
    required_tags: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
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
        "delegate", "clarify", "complete", "stop"
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


class CoverageManifest(BaseModel):
    """Agent-declared scope; absent manifests mean coverage is unknown."""

    scope: str = Field(min_length=1)
    expected_targets: list[str] = Field(default_factory=list)
    inspected_targets: list[str] = Field(default_factory=list)
    enumeration_complete: bool = False
    evidence_call_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_targets(self):
        if len(self.expected_targets) != len(set(self.expected_targets)):
            raise ValueError("expected targets must be unique")
        if len(self.inspected_targets) != len(set(self.inspected_targets)):
            raise ValueError("inspected targets must be unique")
        if not set(self.inspected_targets) <= set(self.expected_targets):
            raise ValueError("inspected targets must be declared in expected targets")
        return self

    @property
    def complete(self) -> bool:
        return bool(self.evidence_call_ids) and self.enumeration_complete and set(self.inspected_targets) == set(self.expected_targets)

    def merge(self, earlier: "CoverageManifest") -> "CoverageManifest":
        if self.scope != earlier.scope or not (set(self.expected_targets) & set(earlier.expected_targets)):
            return self
        return self.model_copy(update={
            "expected_targets": list(dict.fromkeys([*earlier.expected_targets, *self.expected_targets])),
            "inspected_targets": list(dict.fromkeys([*earlier.inspected_targets, *self.inspected_targets])),
            "enumeration_complete": self.enumeration_complete or earlier.enumeration_complete,
            "evidence_call_ids": list(dict.fromkeys([*earlier.evidence_call_ids, *self.evidence_call_ids])),
        })


class SpecialistOutput(BaseModel):
    status: str = "completed"
    summary: str = ""
    findings: list[dict] = Field(default_factory=list)
    resources: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    assessment: "EvidenceAssessment" = Field(default_factory=lambda: EvidenceAssessment())
    recommendations: list[str] = Field(default_factory=list)
    continuation: Continuation = Field(default_factory=Continuation)
    limitations: list[str] = Field(default_factory=list)
    coverage: CoverageManifest | None = None


class EvidenceAssessment(BaseModel):
    facts: list[dict] = Field(default_factory=list)
    inferences: list[dict] = Field(default_factory=list)
    unknowns: list[dict] = Field(default_factory=list)


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
