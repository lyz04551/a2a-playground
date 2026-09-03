from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from backend.host.orchestration.models import (
    HostDecision,
    HostPlan,
    HostRunState,
    PlannedTask,
)


class PlanValidationError(ValueError):
    """Raised when a model-created Host plan is unsafe or inconsistent."""


def task_fingerprint(task: PlannedTask) -> str:
    normalized = {
        "agent_id": task.agent_id.strip().lower(),
        "objective": " ".join(task.objective.lower().split()),
        "input": " ".join(task.input.lower().split()),
        "risk": task.risk,
        "workflow_role": task.workflow_role,
        "required_skill": (task.required_skill or "").strip().lower(),
        "required_tags": sorted(tag.lower() for tag in task.required_tags),
    }
    payload = json.dumps(
        normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_task_agent(
    task: PlannedTask,
    agents: Mapping[str, Mapping[str, Any]],
) -> None:
    agent = agents.get(task.agent_id)
    if agent is None:
        raise PlanValidationError(
            f"task '{task.id}' references an unknown agent"
        )
    if task.risk == "write" and agent.get("read_only", True):
        raise PlanValidationError(
            f"task '{task.id}' assigns write work to a read-only agent"
        )
    skills = [
        item for item in agent.get("skills", []) if isinstance(item, Mapping)
    ]
    if task.required_skill and not any(
        item.get("id") == task.required_skill for item in skills
    ):
        raise PlanValidationError(
            f"task '{task.id}' requires required skill "
            f"'{task.required_skill}' not declared by agent"
        )
    if task.required_tags:
        agent_tags = {
            tag
            for item in skills
            for tag in item.get("tags", [])
            if isinstance(tag, str)
        }
        missing_tags = set(task.required_tags) - agent_tags
        if missing_tags:
            raise PlanValidationError(
                f"task '{task.id}' requires tags not declared by agent: "
                f"{sorted(missing_tags)}"
            )


def validate_decision(
    decision: HostDecision,
    agents: Mapping[str, Mapping[str, Any]],
    state: HostRunState,
) -> HostDecision:
    for task in decision.tasks:
        _validate_task_agent(task, agents)
        fingerprint = task_fingerprint(task)
        if fingerprint in state.task_fingerprints:
            raise PlanValidationError(
                f"task '{task.id}' is a duplicate semantic task from an earlier round"
            )
        if task.workflow_role == "mutation":
            if task.risk != "write":
                raise PlanValidationError(
                    f"mutation task '{task.id}' must declare risk write"
                )
            previous_mutation = next((
                observed
                for observed in state.observations.values()
                if observed.task.workflow_role == "mutation"
            ), None)
            if previous_mutation is not None:
                raise PlanValidationError(
                    f"mutation already attempted by task "
                    f"'{previous_mutation.task.id}'; do not create a new "
                    "mutation task in a later round"
                )
            security_passed = any(
                observed.task.workflow_role == "precheck"
                and observed.evaluation.outcome == "sufficient"
                and observed.task.id in state.successful
                and observed.result.output is not None
                and observed.result.output.continuation.allowed is not False
                and _agent_has_security_capability(
                    agents.get(observed.actual_agent_id, {})
                )
                for observed in state.observations.values()
            )
            if not security_passed:
                raise PlanValidationError(
                    f"mutation task '{task.id}' requires a successful security precheck observation"
                )
        if task.workflow_role == "verification":
            mutation_completed = any(
                observed.task.workflow_role == "mutation"
                and observed.evaluation.outcome == "sufficient"
                and task_id in state.successful
                for task_id, observed in state.observations.items()
            )
            if not mutation_completed:
                raise PlanValidationError(
                    f"verification task '{task.id}' requires a successful mutation observation from an earlier round"
                )

    if decision.action == "complete":
        successful_mutation = any(
            observed.task.workflow_role == "mutation"
            and observed.evaluation.outcome == "sufficient"
            and task_id in state.successful
            for task_id, observed in state.observations.items()
        )
        successful_verification = any(
            observed.task.workflow_role == "verification"
            and observed.evaluation.outcome == "sufficient"
            and task_id in state.successful
            for task_id, observed in state.observations.items()
        )
        if successful_mutation and not successful_verification:
            raise PlanValidationError(
                "Host cannot complete after a mutation without verification"
            )
    return decision


def _agent_has_security_capability(agent: Mapping[str, Any]) -> bool:
    for skill in agent.get("skills", []):
        if not isinstance(skill, Mapping):
            continue
        words = {
            str(skill.get("id") or "").lower(),
            *(str(tag).lower() for tag in skill.get("tags", [])),
        }
        if any("security" in word for word in words):
            return True
    return False


def validate_plan(
    plan: HostPlan,
    agents: Mapping[str, Mapping[str, Any]],
) -> HostPlan:
    task_ids = [task.id for task in plan.tasks]
    known_ids = set(task_ids)
    if len(known_ids) != len(task_ids):
        raise PlanValidationError("plan contains a duplicate task ID")

    for task in plan.tasks:
        _validate_task_agent(task, agents)
        for dependency in task.depends_on:
            if dependency not in known_ids:
                raise PlanValidationError(
                    f"task '{task.id}' has an unknown dependency"
                )

    dependencies = {
        task.id: set(task.depends_on) for task in plan.tasks
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise PlanValidationError("plan contains a dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)

    by_id = {task.id: task for task in plan.tasks}
    for mutation in (
        task for task in plan.tasks if task.workflow_role == "mutation"
    ):
        if mutation.risk != "write":
            raise PlanValidationError(
                f"mutation task '{mutation.id}' must declare risk write"
            )
        prechecks = [
            by_id[dependency]
            for dependency in mutation.depends_on
            if by_id[dependency].workflow_role == "precheck"
        ]
        if not prechecks:
            raise PlanValidationError(
                f"mutation task '{mutation.id}' requires a precheck dependency"
            )
        has_security_precheck = False
        for precheck in prechecks:
            profile = agents[precheck.agent_id]
            for skill in profile.get("skills", []):
                if not isinstance(skill, Mapping):
                    continue
                capability_words = {
                    str(skill.get("id") or "").lower(),
                    *(
                        str(tag).lower()
                        for tag in skill.get("tags", [])
                    ),
                }
                if any(
                    "security" in value for value in capability_words
                ):
                    has_security_precheck = True
                    break
        if not has_security_precheck:
            raise PlanValidationError(
                f"mutation task '{mutation.id}' requires a security precheck"
            )
        if not any(
            candidate.workflow_role == "verification"
            and mutation.id in candidate.depends_on
            for candidate in plan.tasks
        ):
            raise PlanValidationError(
                f"mutation task '{mutation.id}' requires a verification dependent"
            )
    return plan
