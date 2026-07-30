from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, delete, event, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import (
    agents,
    approvals,
    artifacts,
    conversations,
    events,
    messages,
    metadata,
    migrations,
    remote_bindings,
    runs,
)


class SQLiteRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.database_path}",
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def initialize(self) -> None:
        metadata.create_all(self.engine)

    def upsert_agent(self, data: dict[str, Any]) -> dict[str, Any]:
        statement = sqlite_insert(agents).values(
            id=data["id"],
            name=data["name"],
            url=data["url"],
            data=data,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[agents.c.id],
            set_={"name": data["name"], "url": data["url"], "data": data},
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return dict(data)

    def list_agents(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(agents).order_by(agents.c.name, agents.c.id)
            ).mappings()
            return [dict(row["data"]) for row in rows]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(agents.c.data).where(agents.c.id == agent_id)
            ).scalar_one_or_none()
            return dict(row) if row else None

    def delete_agent(self, agent_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(agents).where(agents.c.id == agent_id)
            )
            return result.rowcount > 0

    def list_conversations(
        self, agent_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(conversations)
        if agent_id is not None:
            statement = statement.where(
                conversations.c.agent_id == agent_id
            )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [dict(row["data"]) for row in rows]

    def get_conversation(
        self, conversation_id: str
    ) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            data = connection.execute(
                select(conversations.c.data).where(
                    conversations.c.id == conversation_id
                )
            ).scalar_one_or_none()
            return dict(data) if data else None

    def create_conversation(
        self, data: dict[str, Any]
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            connection.execute(
                insert(conversations).values(
                    id=data["id"],
                    agent_id=data.get("agent_id", ""),
                    title=data.get("title", "New Chat"),
                    type=data.get("type", "single"),
                    data=data,
                )
            )
        return dict(data)

    def update_conversation(
        self, conversation_id: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        current = self.get_conversation(conversation_id)
        if current is None:
            return None
        current.update(changes)
        with self.engine.begin() as connection:
            connection.execute(
                update(conversations)
                .where(conversations.c.id == conversation_id)
                .values(
                    agent_id=current.get("agent_id", ""),
                    title=current.get("title", "New Chat"),
                    type=current.get("type", "single"),
                    data=current,
                )
            )
        return current

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.engine.begin() as connection:
            connection.execute(
                delete(messages).where(
                    messages.c.conversation_id == conversation_id
                )
            )
            connection.execute(
                delete(events).where(
                    events.c.conversation_id == conversation_id
                )
            )
            result = connection.execute(
                delete(conversations).where(
                    conversations.c.id == conversation_id
                )
            )
            return result.rowcount > 0

    def list_messages(
        self, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(messages)
        if conversation_id is not None:
            statement = statement.where(
                messages.c.conversation_id == conversation_id
            )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [dict(row["data"]) for row in rows]

    def add_message(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as connection:
            connection.execute(
                insert(messages).values(
                    id=data["id"],
                    conversation_id=data["conversation_id"],
                    role=data.get("role", "user"),
                    content=data.get("content", ""),
                    data=data,
                )
            )
        conversation_id = data["conversation_id"]
        self.update_conversation(
            conversation_id,
            {
                "message_count": len(
                    self.list_messages(conversation_id)
                )
            },
        )
        return dict(data)

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            data = connection.execute(
                select(messages.c.data).where(messages.c.id == message_id)
            ).scalar_one_or_none()
            return dict(data) if data else None

    def list_events(
        self, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(events)
        if conversation_id is not None:
            statement = statement.where(
                events.c.conversation_id == conversation_id
            )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [dict(row["data"]) for row in rows]

    def add_event(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as connection:
            connection.execute(
                insert(events).values(
                    id=data["id"],
                    conversation_id=data.get("conversation_id", ""),
                    task_id=data.get("task_id", ""),
                    event_type=data.get("event_type", ""),
                    data=data,
                )
            )
        return dict(data)

    def create_run(
        self,
        run_id: str,
        conversation_id: str,
        status: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "id": run_id,
            "conversation_id": conversation_id,
            "status": status,
            **(data or {}),
        }
        with self.engine.begin() as connection:
            connection.execute(
                insert(runs).values(
                    id=run_id,
                    conversation_id=conversation_id,
                    status=status,
                    data=payload,
                )
            )
        return payload

    def update_run_status(self, run_id: str, status: str) -> None:
        with self.engine.begin() as connection:
            current = connection.execute(
                select(runs.c.data).where(runs.c.id == run_id)
            ).scalar_one()
            data = {**current, "status": status}
            connection.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(status=status, data=data)
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            data = connection.execute(
                select(runs.c.data).where(runs.c.id == run_id)
            ).scalar_one_or_none()
            return dict(data) if data else None

    def list_runs(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(runs.c.data)).scalars()
            return [dict(row) for row in rows]

    def upsert_remote_binding(
        self,
        *,
        run_id: str,
        agent_id: str,
        context_id: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        binding_id = f"{run_id}:{agent_id}"
        statement = sqlite_insert(remote_bindings).values(
            id=binding_id,
            run_id=run_id,
            agent_id=agent_id,
            context_id=context_id,
            task_id=task_id,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                remote_bindings.c.run_id,
                remote_bindings.c.agent_id,
            ],
            set_={"context_id": context_id, "task_id": task_id},
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return self.get_remote_binding(run_id, agent_id)

    def get_remote_binding(
        self, run_id: str, agent_id: str
    ) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(remote_bindings).where(
                    remote_bindings.c.run_id == run_id,
                    remote_bindings.c.agent_id == agent_id,
                )
            ).mappings().one_or_none()
            return dict(row) if row else None

    def create_approval(
        self,
        *,
        approval_id: str,
        run_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        action_digest: str,
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            connection.execute(
                insert(approvals).values(
                    id=approval_id,
                    run_id=run_id,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    action_digest=action_digest,
                    status="pending",
                )
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(approvals).where(approvals.c.id == approval_id)
            ).mappings().one_or_none()
            return dict(row) if row else None

    def list_approvals(
        self, run_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(approvals)
        if run_id is not None:
            statement = statement.where(approvals.c.run_id == run_id)
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(statement).mappings()
            ]

    def decide_approval(
        self, approval_id: str, decision: str
    ) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        with self.engine.begin() as connection:
            current = connection.execute(
                select(approvals).where(approvals.c.id == approval_id)
            ).mappings().one()
            if current["status"] not in {"pending", decision}:
                raise ValueError("approval already has a conflicting decision")
            if current["status"] == "pending":
                connection.execute(
                    update(approvals)
                    .where(approvals.c.id == approval_id)
                    .values(status=decision)
                )
        return self.get_approval(approval_id)

    def has_migration(self, migration_id: str) -> bool:
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(migrations.c.id).where(
                        migrations.c.id == migration_id
                    )
                ).scalar_one_or_none()
                is not None
            )

    def mark_migration(
        self, migration_id: str, data: dict[str, Any]
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(migrations).values(id=migration_id, data=data)
            )

    def import_legacy_rows(
        self,
        *,
        conversation_rows: list[dict[str, Any]],
        message_rows: list[dict[str, Any]],
        event_rows: list[dict[str, Any]],
    ) -> None:
        with self.engine.begin() as connection:
            for row in conversation_rows:
                connection.execute(
                    sqlite_insert(conversations)
                    .values(
                        id=row["id"],
                        agent_id=row.get("agent_id", ""),
                        title=row.get("title", "New Chat"),
                        type=row.get("type", "single"),
                        data=row,
                    )
                    .on_conflict_do_nothing(index_elements=[conversations.c.id])
                )
            for row in message_rows:
                connection.execute(
                    sqlite_insert(messages)
                    .values(
                        id=row["id"],
                        conversation_id=row["conversation_id"],
                        role=row.get("role", "user"),
                        content=row.get("content", ""),
                        data=row,
                    )
                    .on_conflict_do_nothing(index_elements=[messages.c.id])
                )
            for row in event_rows:
                connection.execute(
                    sqlite_insert(events)
                    .values(
                        id=row["id"],
                        conversation_id=row.get("conversation_id", ""),
                        task_id=row.get("task_id", ""),
                        event_type=row.get("event_type", ""),
                        data=row,
                    )
                    .on_conflict_do_nothing(index_elements=[events.c.id])
                )
