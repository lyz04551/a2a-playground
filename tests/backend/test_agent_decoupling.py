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


@pytest.mark.anyio
async def test_bootstrap_takes_permissions_from_agent_profile_and_updates_local_aliases():
    stored = [{"id": "legacy", "url": "http://localhost:9000", "risk_level": "write_approval", "read_only": False}]

    class Repository:
        def add_agent(self, agent):
            stored[:] = [item for item in stored if item["id"] != agent["id"]] + [agent]
            return agent

        def list_agents(self):
            return list(stored)

    async def fetch_card(_address):
        return SimpleNamespace(
            name="Inspection Agent", description="Read-only inspection", provider=None,
            capabilities=None, default_input_modes=["text/plain"],
            default_output_modes=["text/plain"], skills=[], version="1.0",
            protocol_version="0.3", preferred_transport="JSONRPC",
            documentation_url="",
        )

    async def fetch_profile(_address):
        return {"agent_id": "inspector", "read_only": True,
                "risk_level": "read_only", "limitations": ["No writes"]}

    agent = await AgentService(Repository(), fetch_card, fetch_profile).register(
        "http://127.0.0.1:9000", stable_id="inspector", risk_level="write_approval"
    )

    assert agent["read_only"] is True
    assert all(item["risk_level"] == "read_only" for item in stored)
    assert next(item for item in stored if item["id"] == "legacy")["superseded_by"] == "inspector"
