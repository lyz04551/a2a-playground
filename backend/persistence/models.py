from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
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

events = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("conversation_id", String, nullable=False),
    Column("task_id", String, nullable=False),
    Column("event_type", String, nullable=False),
    Column("data", JSON, nullable=False),
)

runs = Table(
    "orchestration_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("conversation_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("data", JSON, nullable=False),
)

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

