from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.api.agents import AgentService
from backend import main


@pytest.mark.anyio
async def test_unreachable_bootstrap_agents_do_not_abort_backend_startup(monkeypatch):
    attempted = []

    async def unavailable(address, **kwargs):
        attempted.append((address, kwargs["stable_id"]))
        raise ConnectionError("offline")

    monkeypatch.setenv(
        "BOOTSTRAP_AGENTS",
        '[{"id":"external","url":"http://external.test"}]',
    )
    monkeypatch.setattr(main.run_service, "recover_interrupted_runs", lambda: 0)
    monkeypatch.setattr(main.agent_service, "register", unavailable)

    await main.bootstrap_builtin_agents()

    assert attempted == [("http://external.test", "external")]


@pytest.mark.anyio
async def test_registry_accepts_non_kubernetes_a2a_agent_card():
    class Repository:
        def add_agent(self, agent):
            return agent

    async def fetch_card(_address):
        return SimpleNamespace(
            name="Writing Agent",
            description="Drafts technical documents",
            provider=None,
            capabilities=None,
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain"],
            skills=[],
            version="1.0",
            protocol_version="0.3",
            preferred_transport="JSONRPC",
            documentation_url="",
        )

    agent = await AgentService(Repository(), fetch_card).register(
        "external-agent.test:9000"
    )

    assert agent["name"] == "Writing Agent"
    assert agent["url"] == "http://external-agent.test:9000"
    assert agent["risk_level"] == "read_only"
