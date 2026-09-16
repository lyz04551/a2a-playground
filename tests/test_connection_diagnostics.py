from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage

from backend.diagnostics import collect_connection_diagnostics, probe_host_model
from backend.llm_config import LLMConfig


@pytest.mark.anyio
async def test_host_diagnostic_requires_a_real_nonempty_model_response():
    class Model:
        async def ainvoke(self, _messages):
            return AIMessage(content="OK")

    result = await probe_host_model(
        lambda: LLMConfig("deepseek", "https://model.test/v1", "deepseek-chat", "secret"),
        model_factory=lambda **_kwargs: Model(),
        timeout=1,
    )

    assert result["state"] == "ok"
    assert result["model"] == "deepseek-chat"
    assert "response" not in result
    assert "api_key" not in str(result)


@pytest.mark.anyio
async def test_connection_diagnostics_keep_agent_failures_independent():
    release = asyncio.Event()

    async def host_probe(_config_loader):
        return {"state": "ok", "model": "deepseek-chat", "latency_ms": 3}

    async def agent_probe(url):
        await release.wait()
        if url.endswith("ops"):
            return {
                "model": {"state": "ok", "latency_ms": 5},
                "mcp": {"state": "error", "latency_ms": 7, "error": "unreachable"},
            }
        raise RuntimeError("agent offline")

    task = asyncio.create_task(collect_connection_diagnostics(
        [
            {"id": "ops", "name": "Ops", "url": "http://agent/ops"},
            {"id": "security", "name": "Security", "url": "http://agent/security"},
        ],
        lambda: None,
        host_probe=host_probe,
        agent_probe=agent_probe,
    ))
    release.set()
    result = await task

    assert result["host"]["state"] == "ok"
    assert result["agents"][0]["mcp"]["state"] == "error"
    assert result["agents"][1]["state"] == "offline"
    assert result["agents"][1]["error"] == "agent offline"


@pytest.mark.anyio
async def test_model_target_skips_host_and_forwards_only_model_probe():
    calls = []

    async def forbidden_host_probe(_config_loader):
        raise AssertionError("child model test must not call Host")

    async def agent_probe(url, target):
        calls.append((url, target))
        return {"model": {"state": "ok", "latency_ms": 4}}

    result = await collect_connection_diagnostics(
        [{"id": "ops", "name": "Ops", "url": "http://agent/ops"}],
        lambda: None,
        target="models",
        host_probe=forbidden_host_probe,
        agent_probe=agent_probe,
    )

    assert "host" not in result
    assert calls == [("http://agent/ops", "model")]
    assert result["agents"][0]["model"]["state"] == "ok"
