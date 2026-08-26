from __future__ import annotations

import pytest

from backend.orchestration.events import RunEvent, RunEventType
from tests.postgres_helpers import create_test_repository


def _event(event_id: str) -> RunEvent:
    return RunEvent(
        event_id=event_id,
        sequence=1,
        run_id="run-1",
        conversation_id="conv-1",
        type=RunEventType.TASK_STARTED,
        data={"source": "test"},
    )


def test_persists_a_run_task_hierarchy(tmp_path):
    repository = create_test_repository()
    repository.initialize()

    repository.create_task(
        {
            "id": "task-root",
            "run_id": "run-1",
            "parent_task_id": None,
            "agent_id": "host",
            "status": "planning",
        }
    )
    repository.create_task(
        {
            "id": "task-child",
            "run_id": "run-1",
            "parent_task_id": "task-root",
            "agent_id": "k8s-ops",
            "status": "working",
        }
    )

    assert repository.list_tasks("run-1")[1]["parent_task_id"] == "task-root"


def test_appends_run_events_with_repository_assigned_sequences(tmp_path):
    repository = create_test_repository()
    repository.initialize()

    first = repository.append_run_event(_event("event-1"))
    second = repository.append_run_event(_event("event-2"))

    assert [first.sequence, second.sequence] == [1, 2]
    assert [event.sequence for event in repository.list_run_events("run-1")] == [
        1,
        2,
    ]
    assert [event.event_id for event in repository.list_run_events("run-1", 1)] == [
        "event-2"
    ]


def test_appending_a_duplicate_run_event_is_idempotent(tmp_path):
    repository = create_test_repository()
    repository.initialize()

    first = repository.append_run_event(_event("event-1"))
    duplicate = repository.append_run_event(_event("event-1"))

    assert duplicate == first
    assert [event.sequence for event in repository.list_run_events("run-1")] == [1]


def test_run_events_ignore_generic_events_with_incidental_run_fields(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    repository.add_event(
        {
            "id": "legacy-1",
            "conversation_id": "conv-1",
            "task_id": "legacy-task",
            "event_type": "legacy.event",
            "run_id": "run-1",
            "sequence": 99,
        }
    )

    appended = repository.append_run_event(_event("event-1"))

    assert appended.sequence == 1
    assert [event.event_id for event in repository.list_run_events("run-1")] == [
        "event-1"
    ]


def test_deleting_a_conversation_preserves_live_run_event_history(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    repository.create_conversation({"id": "conv-1", "agent_id": "host"})
    repository.create_run("run-1", "conv-1", "running")
    repository.append_run_event(_event("event-1"))

    repository.delete_conversation("conv-1")
    next_event = repository.append_run_event(_event("event-2"))

    assert repository.get_run("run-1")["id"] == "run-1"
    assert next_event.sequence == 2
    assert [event.sequence for event in repository.list_run_events("run-1")] == [
        1,
        2,
    ]


def test_lists_tasks_in_parent_before_descendant_order(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    for task_id, parent_task_id in (
        ("root", None),
        ("child-z", "root"),
        ("child-a", "root"),
        ("a-grandchild", "child-z"),
    ):
        repository.create_task(
            {
                "id": task_id,
                "run_id": "run-1",
                "parent_task_id": parent_task_id,
                "agent_id": "host",
                "status": "working",
            }
        )

    assert [task["id"] for task in repository.list_tasks("run-1")] == [
        "root",
        "child-a",
        "child-z",
        "a-grandchild",
    ]


def test_task_updates_preserve_identity_run_and_valid_parent_links(tmp_path):
    repository = create_test_repository()
    repository.initialize()
    for task_id, run_id, parent_task_id in (
        ("root", "run-1", None),
        ("child", "run-1", "root"),
        ("other-root", "run-2", None),
    ):
        repository.create_task(
            {
                "id": task_id,
                "run_id": run_id,
                "parent_task_id": parent_task_id,
                "agent_id": "host",
                "status": "working",
            }
        )

    with pytest.raises(ValueError, match="id"):
        repository.update_task("child", {"id": "renamed"})
    with pytest.raises(ValueError, match="run_id"):
        repository.update_task("child", {"run_id": "run-2"})
    with pytest.raises(ValueError, match="does not exist"):
        repository.update_task("child", {"parent_task_id": "missing"})
    with pytest.raises(ValueError, match="same run"):
        repository.update_task("child", {"parent_task_id": "other-root"})
    with pytest.raises(ValueError, match="own parent"):
        repository.update_task("child", {"parent_task_id": "child"})
    with pytest.raises(ValueError, match="cycle"):
        repository.update_task("root", {"parent_task_id": "child"})

    assert repository.list_tasks("run-1")[1]["parent_task_id"] == "root"


def test_create_task_rejects_a_missing_parent(tmp_path):
    repository = create_test_repository()
    repository.initialize()

    with pytest.raises(ValueError, match="does not exist"):
        repository.create_task(
            {
                "id": "orphan",
                "run_id": "run-1",
                "parent_task_id": "missing",
                "agent_id": "host",
                "status": "working",
            }
        )


def test_generic_events_cannot_use_the_run_event_discriminator(tmp_path):
    repository = create_test_repository()
    repository.initialize()

    with pytest.raises(ValueError, match="reserved"):
        repository.add_event(
            {
                "id": "generic-run-event",
                "conversation_id": "conv-1",
                "task_id": "",
                "event_type": "run_event",
            }
        )


def test_task_parent_validation_rejects_legacy_cycles_and_indirect_cross_run_links(
    tmp_path,
):
    from sqlalchemy import update

    from backend.persistence.models import orchestration_tasks

    repository = create_test_repository()
    repository.initialize()
    for task_id, run_id, parent_task_id in (
        ("a", "run-1", None),
        ("b", "run-1", "a"),
        ("candidate", "run-1", None),
        ("foreign", "run-2", None),
    ):
        repository.create_task(
            {
                "id": task_id,
                "run_id": run_id,
                "parent_task_id": parent_task_id,
                "agent_id": "host",
                "status": "working",
            }
        )

    with repository.engine.begin() as connection:
        connection.execute(
            update(orchestration_tasks)
            .where(orchestration_tasks.c.id == "a")
            .values(parent_task_id="b")
        )
    with pytest.raises(ValueError, match="cycle"):
        repository.update_task("candidate", {"parent_task_id": "a"})

    with repository.engine.begin() as connection:
        connection.execute(
            update(orchestration_tasks)
            .where(orchestration_tasks.c.id == "a")
            .values(parent_task_id="foreign")
        )
    with pytest.raises(ValueError, match="same run"):
        repository.update_task("candidate", {"parent_task_id": "a"})


def test_lists_a_deep_task_hierarchy_without_recursion(tmp_path):
    from sqlalchemy import insert

    from backend.persistence.models import orchestration_tasks

    repository = create_test_repository()
    repository.initialize()
    parent_task_id = None
    rows = []
    for index in range(1_050):
        task_id = f"task-{index:04d}"
        data = {
            "id": task_id,
            "run_id": "run-1",
            "parent_task_id": parent_task_id,
            "agent_id": "host",
            "status": "working",
        }
        rows.append(
            {
                **data,
                "data": data,
            }
        )
        parent_task_id = task_id
    with repository.engine.begin() as connection:
        connection.execute(insert(orchestration_tasks), rows)

    tasks = repository.list_tasks("run-1")

    assert len(tasks) == 1_050
    assert tasks[0]["id"] == "task-0000"
    assert tasks[-1]["id"] == "task-1049"
