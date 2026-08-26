from __future__ import annotations

import asyncio
import os

from .checkpoint import setup_checkpoint_database


async def migrate() -> None:
    database_url = os.getenv("AGENT_CHECKPOINT_DATABASE_URL")
    if not database_url:
        raise RuntimeError("AGENT_CHECKPOINT_DATABASE_URL is required")
    await setup_checkpoint_database(database_url)


def main() -> None:
    asyncio.run(migrate())


if __name__ == "__main__":
    main()
