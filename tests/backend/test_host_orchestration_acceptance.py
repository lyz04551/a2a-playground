from __future__ import annotations

import pytest

from backend.host.orchestration.engine import HostOrchestrationEngine
from backend.host.orchestration.models import HostPlan, PlannedTask
from backend.settings import AppSettings


def test_host_orchestration_settings_have_safe_defaults(monkeypatch):
    for name in (
        "HOST_MAX_TASKS",
        "HOST_MAX_ROUNDS",
        "HOST_MAX_CONCURRENCY",
        "HOST_MAX_ATTEMPTS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = AppSettings.from_env()

    assert settings.host_max_tasks == 12
    assert settings.host_max_rounds == 8
    assert settings.host_max_concurrency == 3
    assert settings.host_max_attempts == 2


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HOST_MAX_TASKS", "0"),
        ("HOST_MAX_TASKS", "31"),
        ("HOST_MAX_ROUNDS", "0"),
        ("HOST_MAX_ROUNDS", "21"),
        ("HOST_MAX_CONCURRENCY", "0"),
        ("HOST_MAX_CONCURRENCY", "6"),
        ("HOST_MAX_ATTEMPTS", "0"),
        ("HOST_MAX_ATTEMPTS", "3"),
        ("HOST_MAX_TASKS", "invalid"),
    ],
)
def test_host_orchestration_settings_reject_unsafe_values(
    monkeypatch, name, value
):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        AppSettings.from_env()


@pytest.mark.anyio
async def test_engine_rejects_plan_above_configured_task_limit():
    class Registry:
        def list(self):
            return [
                {"id": "ops", "read_only": True, "health": {"online": True}}
            ]

        def capability_profile(self, agent_id):
            return self.list()[0]

    class Decisions:
        async def create_plan(self, request, agents):
            return HostPlan(
                summary="two tasks",
                tasks=[
                    PlannedTask(
                        id=f"task-{index}",
                        agent_id="ops",
                        objective="inspect",
                        completion_criteria=["evidence"],
                    )
                    for index in range(2)
                ],
            )

    async def delegate(agent_id, prompt):
        raise AssertionError("delegation must not start")

    engine = HostOrchestrationEngine(
        Registry(), Decisions(), delegate, max_tasks=1
    )

    with pytest.raises(ValueError, match="task limit"):
        _ = [event async for event in engine.stream("inspect", "run-1")]
