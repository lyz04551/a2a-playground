from __future__ import annotations

from tests.postgres_helpers import create_test_repository
from backend.registry.service import AgentRegistry


def test_registry_keeps_duplicate_names_separate_and_filters_by_skill(tmp_path):
    repository = create_test_repository()
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
    repository = create_test_repository()
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


def test_registry_normalizes_legacy_agent_conservatively(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    repository.upsert_agent(
        {"id": "legacy", "name": "Legacy", "url": "http://legacy"}
    )

    profile = AgentRegistry(repository).capability_profile("legacy")

    assert profile["read_only"] is True
    assert profile["risk_level"] == "read_only"
    assert profile["limitations"] == []
    assert profile["priority"] == 100


def test_registry_ranks_exact_skill_before_tag_match(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    for agent in (
        {
            "id": "tagged",
            "name": "Tagged",
            "url": "http://tagged",
            "skills": [{"id": "cluster.inspect", "tags": ["logs"]}],
            "read_only": True,
            "priority": 1,
        },
        {
            "id": "exact",
            "name": "Exact",
            "url": "http://exact",
            "skills": [{"id": "pod.diagnose", "tags": ["kubernetes"]}],
            "read_only": True,
            "priority": 100,
        },
    ):
        repository.upsert_agent(agent)

    candidates = AgentRegistry(repository).rank_candidates(
        skill="pod.diagnose",
        tags={"kubernetes", "logs"},
        risk="read",
    )

    assert [agent["id"] for agent in candidates] == ["exact", "tagged"]


def test_registry_excludes_read_only_agent_from_write_candidates(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    repository.upsert_agent(
        {
            "id": "reader",
            "name": "Reader",
            "url": "http://reader",
            "read_only": True,
        }
    )

    assert AgentRegistry(repository).rank_candidates(
        skill=None, tags=set(), risk="write"
    ) == []
