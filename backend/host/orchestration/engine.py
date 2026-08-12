from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable

from backend.host.orchestration.context import build_task_prompt
from backend.host.orchestration.models import (
    DecisionPort,
    DelegationResult,
    Evaluation,
    PlannedTask,
)
from backend.host.orchestration.validation import validate_plan


Delegate = Callable[..., Awaitable[DelegationResult]]


class HostOrchestrationEngine:
    def __init__(
        self,
        registry,
        decisions: DecisionPort,
        delegate: Delegate,
        *,
        max_concurrency: int = 3,
        max_tasks: int = 6,
        max_attempts: int = 2,
    ):
        self._registry = registry
        self._decisions = decisions
        self._delegate = delegate
        self._delegate_accepts_run_id = len(
            inspect.signature(delegate).parameters
        ) >= 3
        self._delegate_accepts_progress = len(
            inspect.signature(delegate).parameters
        ) >= 4
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_tasks = max_tasks
        self._max_attempts = max_attempts

    async def stream(
        self, request: str, run_id: str
    ) -> AsyncIterator[dict]:
        agents = self._registry.list()
        plan = await self._decisions.create_plan(request, agents)
        if len(plan.tasks) > self._max_tasks:
            raise ValueError("Host plan exceeds configured task limit")
        profiles = {
            agent["id"]: self._registry.capability_profile(agent["id"])
            for agent in agents
        }
        validate_plan(plan, profiles)
        yield {
            "type": "plan_created",
            "summary": plan.summary,
            "tasks": [task.model_dump() for task in plan.tasks],
        }

        by_id = {task.id: task for task in plan.tasks}
        remaining = set(by_id)
        results: dict[str, DelegationResult] = {}
        successful: set[str] = set()

        while remaining:
            blocked = [
                task
                for task in plan.tasks
                if task.id in remaining
                and task.depends_on
                and all(dependency in results for dependency in task.depends_on)
                and any(
                    dependency not in successful
                    for dependency in task.depends_on
                )
            ]
            for task in blocked:
                result = DelegationResult(
                    state="failed",
                    error="required predecessor did not complete",
                )
                results[task.id] = result
                remaining.remove(task.id)
                yield {
                    "type": "task_blocked",
                    "task_id": task.id,
                    "agent_id": task.agent_id,
                    "reason": result.error,
                }

            ready = [
                task
                for task in plan.tasks
                if task.id in remaining
                and all(dependency in successful for dependency in task.depends_on)
            ]
            if not ready:
                if remaining:
                    raise RuntimeError("orchestration plan made no progress")
                break

            prompts: dict[str, str] = {}
            for task in ready:
                dependencies = {
                    dependency: (
                        by_id[dependency].agent_id,
                        results[dependency],
                    )
                    for dependency in task.depends_on
                }
                prompts[task.id] = build_task_prompt(
                    task, request, dependencies
                )
                yield {
                    "type": "context_prepared",
                    "task_id": task.id,
                    "agent_id": task.agent_id,
                    "depends_on": task.depends_on,
                }
                yield {
                    "type": "routing",
                    "task_id": task.id,
                    "agent_id": task.agent_id,
                    "agent": task.agent_id,
                }
                yield {
                    "type": "task_started",
                    "task_id": task.id,
                    "agent_id": task.agent_id,
                }

            progress: asyncio.Queue[dict] = asyncio.Queue()
            executions_task = asyncio.ensure_future(asyncio.gather(
                *(
                    self._run_task(
                        run_id, task, prompts[task.id], progress.put
                    )
                    for task in ready
                )
            ))
            progress_task: asyncio.Task | None = asyncio.create_task(progress.get())
            while not executions_task.done():
                done, _ = await asyncio.wait(
                    {executions_task, progress_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if progress_task in done:
                    yield progress_task.result()
                    progress_task = asyncio.create_task(progress.get())
            if progress_task and not progress_task.done():
                progress_task.cancel()
            while not progress.empty():
                yield progress.get_nowait()
            executions = await executions_task
            for task, execution in zip(ready, executions, strict=True):
                result, evaluation, agent_id, recovery_events = execution
                for event in recovery_events:
                    yield event
                results[task.id] = result
                remaining.remove(task.id)
                yield {
                    "type": "task_evaluated",
                    "task_id": task.id,
                    "agent_id": agent_id,
                    "outcome": evaluation.outcome,
                    "reason": evaluation.reason,
                }
                if evaluation.outcome == "sufficient" and result.state == "completed":
                    successful.add(task.id)
                    yield {
                        "type": "task_completed",
                        "task_id": task.id,
                        "agent_id": agent_id,
                        "result": result.text,
                    }
                elif result.state == "approval_required":
                    yield {
                        "type": "approval_required",
                        "task_id": task.id,
                        "agent_id": agent_id,
                        "approval": result.approval or {},
                    }
                else:
                    yield {
                        "type": "task_failed",
                        "task_id": task.id,
                        "agent_id": agent_id,
                        "error": result.error or evaluation.reason,
                    }

        yield {"type": "synthesis_started"}
        text = await self._decisions.synthesize(request, plan, dict(results))
        yield {"type": "text", "text": text}
        yield {"type": "done", "session_id": run_id}

    async def _run_task(
        self,
        run_id: str,
        task: PlannedTask,
        prompt: str,
        on_progress,
    ) -> tuple[DelegationResult, Evaluation, str, list[dict]]:
        events: list[dict] = []
        agent_id = task.agent_id
        tried = {agent_id}
        result: DelegationResult | None = None
        evaluation: Evaluation | None = None

        allowed_attempts = min(task.max_attempts, self._max_attempts)
        for attempt in range(1, allowed_attempts + 1):
            result = await self._execute_safely(
                run_id, agent_id, prompt, task.id, on_progress
            )
            evaluation = await self._decisions.evaluate(task, result)
            if evaluation.outcome in {"sufficient", "blocked"}:
                return result, evaluation, agent_id, events
            if result.state == "completed":
                # Re-running a completed diagnostic can duplicate dozens of
                # remote tool calls. Preserve it for Host synthesis and report
                # the quality gap instead of repeating the whole audit.
                return result, evaluation, agent_id, events
            if attempt < allowed_attempts:
                events.append(
                    {
                        "type": "task_retry_scheduled",
                        "task_id": task.id,
                        "agent_id": agent_id,
                        "attempt": attempt + 1,
                        "reason": evaluation.reason,
                    }
                )
                prompt = (
                    f"{prompt}\n\nPrevious attempt was insufficient: "
                    f"{evaluation.reason}\nReturn a corrected result."
                )

        candidates = self._registry.rank_candidates(
            skill=None,
            tags=set(),
            risk=task.risk,
            exclude=tried,
        ) if result is not None and result.state == "failed" else []
        if candidates:
            replacement = candidates[0]["id"]
            events.extend(
                [
                    {
                        "type": "plan_revised",
                        "task_id": task.id,
                        "agent_id": agent_id,
                        "replacement_agent_id": replacement,
                        "reason": evaluation.reason,
                    },
                    {
                        "type": "routing",
                        "task_id": task.id,
                        "agent_id": replacement,
                        "agent": replacement,
                    },
                ]
            )
            agent_id = replacement
            result = await self._execute_safely(
                run_id, agent_id, prompt, task.id, on_progress
            )
            evaluation = await self._decisions.evaluate(task, result)

        assert result is not None and evaluation is not None
        return result, evaluation, agent_id, events

    async def _execute_safely(
        self, run_id: str, agent_id: str, prompt: str, task_id: str, on_progress
    ) -> DelegationResult:
        try:
            return await self._execute(
                run_id, agent_id, prompt, task_id, on_progress
            )
        except Exception as exc:
            return DelegationResult(
                state="failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _execute(
        self, run_id: str, agent_id: str, prompt: str, task_id: str, on_progress
    ) -> DelegationResult:
        async with self._semaphore:
            if self._delegate_accepts_run_id:
                if self._delegate_accepts_progress:
                    async def emit(event: dict) -> None:
                        await on_progress({
                            **event,
                            "task_id": task_id,
                            "agent_id": agent_id,
                        })
                    return await self._delegate(
                        run_id, agent_id, prompt, emit
                    )
                return await self._delegate(run_id, agent_id, prompt)
            return await self._delegate(agent_id, prompt)
