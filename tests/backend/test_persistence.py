from __future__ import annotations

from backend.persistence.repository import SQLiteRepository
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import inspect


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


def test_message_insert_atomically_updates_conversation_count(tmp_path):
    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()
    repository.create_conversation(
        {"id": "conv-1", "agent_id": "ops", "message_count": 0}
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda index: repository.add_message(
                    {
                        "id": f"message-{index}",
                        "conversation_id": "conv-1",
                        "role": "user",
                        "content": str(index),
                    }
                ),
                range(12),
            )
        )

    conversation = repository.get_conversation("conv-1")
    assert conversation["message_count"] == 12
    assert conversation["updated_at"]


def test_sqlite_enables_wal_and_common_lookup_indexes(tmp_path):
    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()

    with repository.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"

    indexes = {
        (table, index["name"])
        for table in (
            "messages",
            "events",
            "orchestration_runs",
            "orchestration_tasks",
            "approvals",
        )
        for index in inspect(repository.engine).get_indexes(table)
    }
    assert {
        ("messages", "ix_messages_conversation"),
        ("events", "ix_events_conversation_type"),
        ("orchestration_runs", "ix_runs_conversation_status"),
        ("orchestration_tasks", "ix_tasks_run_status"),
        ("approvals", "ix_approvals_run_status"),
    } <= indexes


def test_repository_merges_run_and_task_checkpoint_data(tmp_path):
    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()
    repository.create_run(
        "run-1", "conv-1", "running", {"title": "deploy nginx"}
    )
    repository.create_task({
        "id": "task-1",
        "run_id": "run-1",
        "parent_task_id": None,
        "agent_id": "host",
        "status": "working",
        "objective": "deploy",
    })

    repository.update_run_data(
        "run-1", {"host_plan": {"summary": "guarded deployment"}}
    )
    repository.update_task_data(
        "task-1",
        {
            "logical_task_id": "security-review",
            "delegation_result": {"state": "completed"},
        },
    )

    run = repository.get_run("run-1")
    task = repository.get_task("task-1")
    assert run["title"] == "deploy nginx"
    assert run["host_plan"]["summary"] == "guarded deployment"
    assert task["objective"] == "deploy"
    assert task["logical_task_id"] == "security-review"
    assert task["delegation_result"] == {"state": "completed"}
