from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from backend.security import validate_agent_url
from backend.settings import AppSettings


async def probe_host_model(
    config_loader,
    *,
    model_factory=ChatOpenAI,
    timeout: float = 15.0,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        config = config_loader()
        if not config.configured:
            raise RuntimeError("Host model is not configured")
        model = model_factory(
            model=config.model,
            openai_api_key=config.api_key,
            openai_api_base=config.base_url,
            temperature=0,
            streaming=False,
            request_timeout=timeout,
            max_retries=0,
            max_tokens=8,
        )
        async with asyncio.timeout(timeout):
            response = await model.ainvoke([
                HumanMessage(content="Reply with exactly OK.")
            ])
        if not str(getattr(response, "content", "") or "").strip():
            raise RuntimeError("Host model returned an empty response")
        return {
            "state": "ok",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "provider": config.provider,
            "model": config.model,
        }
    except Exception as exc:
        return {
            "state": "error",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": str(exc)[:200],
        }


async def probe_agent_connections(
    agent_url: str,
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    url = await validate_agent_url(
        agent_url,
        allow_private=AppSettings.from_env().allow_private_agents,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{url}/health/diagnostics")
    if response.status_code in {404, 405}:
        return {
            "state": "unsupported",
            "error": "Agent does not expose connection diagnostics",
        }
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Agent returned an invalid diagnostics response")
    return payload


async def collect_connection_diagnostics(
    agents: list[dict[str, Any]],
    config_loader,
    *,
    host_probe: Callable[[Any], Awaitable[dict[str, Any]]] = probe_host_model,
    agent_probe: Callable[[str], Awaitable[dict[str, Any]]] = probe_agent_connections,
) -> dict[str, Any]:
    async def collect_agent(agent: dict[str, Any]) -> dict[str, Any]:
        identity = {
            "id": str(agent.get("id") or ""),
            "name": str(agent.get("name") or agent.get("id") or "Agent"),
        }
        try:
            result = await agent_probe(str(agent.get("url") or ""))
            return {**identity, "state": result.get("state", "ready"), **result}
        except Exception as exc:
            return {
                **identity,
                "state": "offline",
                "error": str(exc)[:200],
            }

    host_result, agent_results = await asyncio.gather(
        host_probe(config_loader),
        asyncio.gather(*(collect_agent(agent) for agent in agents)),
    )
    return {"host": host_result, "agents": list(agent_results)}
