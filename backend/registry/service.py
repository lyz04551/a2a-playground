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

    def capability_profile(self, agent_id: str) -> dict[str, Any] | None:
        agent = self.get(agent_id)
        if agent is None:
            return None
        profile = dict(agent)
        profile.setdefault("skills", [])
        profile.setdefault("read_only", True)
        profile.setdefault(
            "risk_level",
            "read_only" if profile["read_only"] else "write_approval",
        )
        profile.setdefault("limitations", [])
        profile.setdefault("priority", 100)
        profile.setdefault("health", {"online": True})
        return profile

    def rank_candidates(
        self,
        *,
        skill: str | None,
        tags: set[str],
        risk: str,
        exclude: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        excluded = exclude or set()
        ranked: list[tuple[int, int, int, str, dict[str, Any]]] = []
        for stored in self.list():
            profile = self.capability_profile(stored["id"])
            if profile is None or profile["id"] in excluded:
                continue
            if not profile["health"].get("online", True):
                continue
            if risk == "write" and profile["read_only"]:
                continue
            skills = [
                item for item in profile["skills"] if isinstance(item, dict)
            ]
            exact = int(
                bool(skill)
                and any(item.get("id") == skill for item in skills)
            )
            agent_tags = {
                tag
                for item in skills
                for tag in item.get("tags", [])
                if isinstance(tag, str)
            }
            overlap = len(tags & agent_tags)
            if skill and not exact and not overlap:
                continue
            ranked.append(
                (
                    -exact,
                    -overlap,
                    int(profile["priority"]),
                    profile["id"],
                    profile,
                )
            )
        ranked.sort(key=lambda item: item[:4])
        return [item[4] for item in ranked]

    def find_candidates(
        self,
        *,
        skill: str | None = None,
        risk_level: str | None = None,
    ) -> list[dict[str, Any]]:
        candidates = self.rank_candidates(
            skill=skill,
            tags=set(),
            risk="write" if risk_level == "write_approval" else "read",
        )
        if risk_level:
            candidates = [
                item
                for item in candidates
                if item["risk_level"] == risk_level
            ]
        return candidates
