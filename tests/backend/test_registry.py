from __future__ import annotations

from backend.persistence.repository import SQLiteRepository
from backend.registry.service import AgentRegistry


def test_registry_keeps_duplicate_names_separate_and_filters_by_skill(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.upsert_agent(
        {
            "id": "ops-a",
            "name": "K8s Agent",
            "url": "http://ops-a",
            "skills": [{"id": "pod.diagnose"}],
            "health": {"online": True},
            "risk_level": "read_only",
        }
    )
    repository.upsert_agent(
        {
            "id": "orchestrator-a",
            "name": "K8s Agent",
            "url": "http://orchestrator-a",
            "skills": [{"id": "workload.orchestrate"}],
            "health": {"online": True},
            "risk_level": "write_approval",
        }
    )

    registry = AgentRegistry(repository)

    assert registry.get("ops-a")["url"] == "http://ops-a"
    assert [
        agent["id"]
        for agent in registry.find_candidates(skill="pod.diagnose")
    ] == ["ops-a"]


def test_registry_excludes_offline_agent_from_candidates(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    repository.initialize()
    repository.upsert_agent(
        {
            "id": "offline",
            "name": "Offline",
            "url": "http://offline",
            "skills": [{"id": "pod.diagnose"}],
            "health": {"online": False},
        }
    )

    assert AgentRegistry(repository).find_candidates(
        skill="pod.diagnose"
    ) == []

