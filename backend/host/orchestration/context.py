from __future__ import annotations

from collections.abc import Mapping

from backend.host.orchestration.models import DelegationResult, PlannedTask


def build_task_prompt(
    task: PlannedTask,
    request: str,
    dependency_results: Mapping[str, tuple[str, DelegationResult]],
) -> str:
    criteria = "\n".join(
        f"- {criterion}" for criterion in task.completion_criteria
    )
    findings = "\n".join(
        f"[{task_id} / {agent_id}]\n{result.text}"
        for task_id, (agent_id, result) in dependency_results.items()
    ) or "(none)"
    constraint = (
        "Read-only: do not mutate external state."
        if task.risk == "read"
        else "Any mutation must stop for formal approval."
    )
    return (
        f"Objective:\n{task.objective}\n\n"
        f"Relevant user request:\n{task.input or request}\n\n"
        f"Completion criteria:\n{criteria}\n\n"
        f"Constraints:\n{constraint}\n\n"
        f"Predecessor findings:\n{findings}\n\n"
        "Return findings, supporting evidence, uncertainty, and recommended "
        "next steps."
    )
