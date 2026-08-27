from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class PostgresCheckpointManager:
    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("AGENT_CHECKPOINT_DATABASE_URL is required")
        self.database_url = database_url
        self._context: Any = None
        self._saver: AsyncPostgresSaver | None = None

    async def open(self) -> AsyncPostgresSaver:
        if self._saver is None:
            self._context = AsyncPostgresSaver.from_conn_string(
                self.database_url
            )
            self._saver = await self._context.__aenter__()
        return self._saver

    async def close(self) -> None:
        context = self._context
        self._context = None
        self._saver = None
        if context is not None:
            await context.__aexit__(None, None, None)


async def setup_checkpoint_database(database_url: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(
        database_url
    ) as checkpointer:
        await checkpointer.setup()
