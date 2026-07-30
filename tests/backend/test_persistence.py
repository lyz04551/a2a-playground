from __future__ import annotations

from backend.persistence.repository import SQLiteRepository


def test_repository_uses_stable_agent_ids_even_with_duplicate_names(tmp_path):
    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()

    repository.upsert_agent(
        {"id": "ops-a", "name": "K8s Ops", "url": "http://ops-a"}
    )
    repository.upsert_agent(
        {"id": "ops-b", "name": "K8s Ops", "url": "http://ops-b"}
    )

    agents = repository.list_agents()
    assert {agent["id"] for agent in agents} == {"ops-a", "ops-b"}


def test_remote_binding_reuses_context_for_same_run_and_agent(tmp_path):
    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()
    repository.create_run(
        run_id="run-1",
        conversation_id="conv-1",
        status="running",
    )

    repository.upsert_remote_binding(
        run_id="run-1",
        agent_id="k8s-ops",
        context_id="remote-context-1",
        task_id="task-1",
    )
    repository.upsert_remote_binding(
        run_id="run-1",
        agent_id="k8s-ops",
        context_id="remote-context-1",
        task_id="task-2",
    )

    binding = repository.get_remote_binding("run-1", "k8s-ops")
    assert binding["context_id"] == "remote-context-1"
    assert binding["task_id"] == "task-2"


def test_approval_decision_is_idempotent(tmp_path):
    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()
    repository.create_run("run-1", "conv-1", "approval_required")
    repository.create_approval(
        approval_id="ap-1",
        run_id="run-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"name": "api", "replicas": 2},
        action_digest="a" * 64,
    )

    first = repository.decide_approval("ap-1", "approved")
    second = repository.decide_approval("ap-1", "approved")

    assert first["status"] == "approved"
    assert second == first

