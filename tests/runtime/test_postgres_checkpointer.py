import pytest
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy.engine import make_url

from a2a_runtime.agent import RuntimeMCPAgent
from a2a_runtime.config import AgentRuntimeConfig


def _psycopg_url(database_url: str) -> str:
    return make_url(database_url).set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)


@pytest.mark.anyio
async def test_checkpointer_reopens_a_thread_after_runtime_restart(
    postgres_url,
):
    try:
        from a2a_runtime.checkpoint import (
            PostgresCheckpointManager,
            setup_checkpoint_database,
        )
    except ModuleNotFoundError:
        pytest.fail("Postgres checkpoint lifecycle is not implemented")

    checkpoint_url = _psycopg_url(postgres_url)
    await setup_checkpoint_database(checkpoint_url)
    config = {
        "configurable": {"thread_id": "ctx-1", "checkpoint_ns": ""}
    }

    first = PostgresCheckpointManager(checkpoint_url)
    first_saver = await first.open()
    saved_config = await first_saver.aput(
        config,
        empty_checkpoint(),
        {"source": "input", "step": 1, "parents": {}},
        {},
    )
    await first.close()

    second = PostgresCheckpointManager(checkpoint_url)
    second_saver = await second.open()
    restored = await second_saver.aget_tuple(saved_config)
    await second.close()

    assert restored is not None
    assert restored.config["configurable"]["thread_id"] == "ctx-1"


@pytest.mark.anyio
async def test_checkpoint_manager_close_is_idempotent(postgres_url):
    try:
        from a2a_runtime.checkpoint import PostgresCheckpointManager
    except ModuleNotFoundError:
        pytest.fail("Postgres checkpoint lifecycle is not implemented")

    manager = PostgresCheckpointManager(_psycopg_url(postgres_url))
    await manager.close()
    await manager.close()


@pytest.mark.anyio
async def test_runtime_without_checkpoint_url_is_degraded():
    class UnusedMCP:
        async def list_tools(self):
            raise AssertionError("checkpoint configuration must fail first")

        async def disconnect(self):
            return None

    config = AgentRuntimeConfig(
        agent_id="ops",
        name="Ops",
        port=8052,
        public_url="http://ops",
        mcp_url="http://mcp",
    )
    agent = RuntimeMCPAgent(
        config,
        "prompt",
        mcp_client=UnusedMCP(),
        checkpoint_database_url="",
    )

    with pytest.raises(
        RuntimeError, match="AGENT_CHECKPOINT_DATABASE_URL is required"
    ):
        await agent.ensure_ready()

    readiness = agent.readiness()
    assert readiness["state"] == "degraded"
    assert readiness["checks"]["checkpoint"]["state"] == "error"
