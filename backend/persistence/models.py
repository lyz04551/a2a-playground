from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)


metadata = MetaData()

agents = Table(
    "agents",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("url", String, nullable=False),
    Column("data", JSON, nullable=False),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("title", String, nullable=False, default="New Chat"),
    Column("type", String, nullable=False, default="single"),
    Column("data", JSON, nullable=False),
)

messages = Table(
    "messages",
    metadata,
    Column("id", String, primary_key=True),
    Column("conversation_id", String, nullable=False),
    Column("role", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("data", JSON, nullable=False),
)
Index("ix_messages_conversation", messages.c.conversation_id)

events = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("conversation_id", String, nullable=False),
    Column("task_id", String, nullable=False),
    Column("event_type", String, nullable=False),
    Column("run_id", String, nullable=True),
    Column("sequence", Integer, nullable=True),
    Column("created_at", String, nullable=True),
    Column("data", JSON, nullable=False),
)
Index("ix_events_conversation_type", events.c.conversation_id, events.c.event_type)
Index(
    "ix_events_run_sequence",
    events.c.run_id,
    events.c.sequence,
    unique=True,
    postgresql_where=text("run_id IS NOT NULL"),
)
Index("ix_events_conversation_created", events.c.conversation_id, events.c.created_at)
Index("ix_events_type_created", events.c.event_type, events.c.created_at)

runs = Table(
    "orchestration_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("conversation_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("data", JSON, nullable=False),
)
Index("ix_runs_conversation_status", runs.c.conversation_id, runs.c.status)

orchestration_tasks = Table(
    "orchestration_tasks",
    metadata,
    Column("id", String, primary_key=True),
    Column("run_id", String, nullable=False),
    Column("parent_task_id", String, nullable=True),
    Column("agent_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("data", JSON, nullable=False),
)
Index("ix_tasks_run_status", orchestration_tasks.c.run_id, orchestration_tasks.c.status)

remote_bindings = Table(
    "remote_task_bindings",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "run_id",
        String,
        ForeignKey("orchestration_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("agent_id", String, nullable=False),
    Column("context_id", String, nullable=False),
    Column("task_id", String, nullable=True),
    UniqueConstraint("run_id", "agent_id", name="uq_binding_run_agent"),
)

approvals = Table(
    "approvals",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "run_id",
        String,
        ForeignKey("orchestration_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("agent_id", String, nullable=False),
    Column("tool_name", String, nullable=False),
    Column("arguments", JSON, nullable=False),
    Column("action_digest", String(64), nullable=False),
    Column("status", String, nullable=False, default="pending"),
)
Index("ix_approvals_run_status", approvals.c.run_id, approvals.c.status)

artifacts = Table(
    "artifacts",
    metadata,
    Column("id", String, primary_key=True),
    Column("run_id", String, nullable=False),
    Column("task_id", String, nullable=True),
    Column("name", String, nullable=False),
    Column("data", JSON, nullable=False),
)

migrations = Table(
    "migrations",
    metadata,
    Column("id", String, primary_key=True),
    Column("data", JSON, nullable=False),
)
