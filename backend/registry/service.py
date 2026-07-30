from __future__ import annotations

from typing import Any


class AgentRegistry:
    """Stable-ID capability registry backed by SQLite."""

    def __init__(self, repository):
        self.repository = repository

    def get(self, agent_id: str) -> dict[str, Any] | None:
        return self.repository.get_agent(agent_id)

    def list(self) -> list[dict[str, Any]]:
        return self.repository.list_agents()

    def find_candidates(
        self,
        *,
        skill: str | None = None,
        risk_level: str | None = None,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for agent in self.list():
            if not agent.get("health", {}).get("online", True):
                continue
            if risk_level and agent.get("risk_level") != risk_level:
                continue
            skill_ids = {
                item.get("id")
                for item in agent.get("skills", [])
                if isinstance(item, dict)
            }
            if skill and skill not in skill_ids:
                continue
            candidates.append(agent)
        return candidates

