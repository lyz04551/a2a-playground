from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.orchestration.events import RunEvent, RunEventType


def test_create_builds_a_versioned_run_started_event():
    """Protects the wire contract from losing its version, event name, or UTC timestamp."""
    event = RunEvent.create(
        event_type=RunEventType.RUN_STARTED,
        run_id="run-1",
        conversation_id="conv-1",
        sequence=1,
        data={"mode": "direct"},
    )

    assert event.version == 1
    assert event.type == "run.started"
    assert event.sequence == 1
    assert event.task_id is None
    assert event.timestamp.tzinfo == timezone.utc
    assert event.model_dump(mode="json")["timestamp"].endswith("Z")


@pytest.mark.parametrize("sequence", [0, -1])
def test_rejects_sequences_below_one(sequence):
    """Protects event ordering from accepting values that cannot be ordered in a run."""
    with pytest.raises(ValidationError):
        RunEvent.create(
            event_type=RunEventType.RUN_STARTED,
            run_id="run-1",
            conversation_id="conv-1",
            sequence=sequence,
            data={},
        )


def test_rejects_unsupported_event_types():
    """Protects consumers from receiving event names outside the versioned contract."""
    with pytest.raises(ValidationError):
        RunEvent.create(
            event_type="run.unknown",
            run_id="run-1",
            conversation_id="conv-1",
            sequence=1,
            data={},
        )


def test_rejects_a_supplied_naive_timestamp():
    """Protects the wire contract from ambiguous timestamps without a UTC offset."""
    with pytest.raises(ValidationError):
        RunEvent(
            type=RunEventType.RUN_STARTED,
            run_id="run-1",
            conversation_id="conv-1",
            sequence=1,
            timestamp=datetime(2026, 7, 30, 12, 0, 0),
            data={},
        )


def test_normalizes_a_supplied_aware_timestamp_to_utc():
    """Protects consumers from receiving offset timestamps instead of the UTC wire format."""
    event = RunEvent(
        type=RunEventType.RUN_STARTED,
        run_id="run-1",
        conversation_id="conv-1",
        sequence=1,
        timestamp=datetime(2026, 7, 30, 20, 0, 0, tzinfo=timezone(timedelta(hours=8))),
        data={},
    )

    assert event.timestamp == datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)
    assert event.model_dump(mode="json")["timestamp"].endswith("Z")
