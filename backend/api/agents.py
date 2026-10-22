from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter

from backend.models import Agent, AgentRegister, ApiResponse


CardFetcher = Callable[[str], Awaitable[Any]]
HealthChecker = Callable[[str], Awaitable[dict[str, Any]]]
ProfileFetcher = Callable[[str], Awaitable[dict[str, Any]]]
ToolCatalogFetcher = Callable[[str], Awaitable[dict[str, Any]]]


async def fetch_agent_profile(address: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{address.rstrip('/')}/health/profile")
        response.raise_for_status()
        return response.json()


async def fetch_agent_tool_catalog(address: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(f"{address.rstrip('/')}/health/diagnostics", json={"target": "mcp"})
        response.raise_for_status()
        payload = response.json()
    return payload.get("mcp", {}) if isinstance(payload, dict) else {}


class AgentService:
    def __init__(self, repository, fetch_card: CardFetcher, profile_fetcher: ProfileFetcher | None = None, tool_catalog_fetcher: ToolCatalogFetcher | None = None):
        self.repository = repository
        self.fetch_card = fetch_card
        self.fetch_profile = profile_fetcher or fetch_agent_profile
        self.fetch_tool_catalog = tool_catalog_fetcher or fetch_agent_tool_catalog

    async def register(
        self,
        address: str,
        *,
        stable_id: str | None = None,
        risk_level: str | None = None,
    ) -> dict[str, Any]:
        card = await self.fetch_card(address)
        agent_url = address.strip()
        if not agent_url.startswith("http"):
            agent_url = f"http://{agent_url}"
        profile = await self.fetch_profile(agent_url) if stable_id else None
        if profile is not None:
            if profile.get("agent_id") != stable_id:
                raise ValueError("Agent profile ID does not match bootstrap ID")
            if not isinstance(profile.get("read_only"), bool):
                raise ValueError("Agent profile must declare read_only")
            declared_risk = profile.get("risk_level")
            expected_risk = "read_only" if profile["read_only"] else "write_approval"
            if declared_risk != expected_risk:
                raise ValueError("Agent profile risk_level conflicts with read_only")
        agent = Agent(
            id=stable_id or uuid.uuid4().hex[:12],
            name=card.name or "Unknown Agent",
            url=agent_url,
            description=card.description or "",
            provider=card.provider.model_dump() if card.provider else None,
            capabilities=(
                card.capabilities.model_dump(mode="json")
                if card.capabilities else {}
            ),
            inputModes=card.default_input_modes or ["text"],
            outputModes=card.default_output_modes or ["text"],
            skills=[skill.model_dump() for skill in (card.skills or [])],
            version=card.version or "",
            protocolVersion=card.protocol_version or "",
            preferredTransport=card.preferred_transport or "",
            documentationUrl=card.documentation_url or "",
            read_only=profile["read_only"] if profile else risk_level != "write_approval",
            risk_level=profile["risk_level"] if profile else risk_level or "read_only",
        ).model_dump()
        if profile is not None:
            agent["limitations"] = profile.get("limitations", [])
            try:
                catalog_result = await self.fetch_tool_catalog(agent_url)
                tools = catalog_result.get("tools")
                if catalog_result.get("state") != "ok" or not isinstance(tools, list):
                    raise ValueError("MCP tool catalog is unavailable")
                agent["tool_catalog"] = [
                    {"name": tool["name"], "access": tool["access"]}
                    for tool in tools
                    if isinstance(tool, dict)
                    and isinstance(tool.get("name"), str)
                    and tool.get("access") in {"allow", "approval_required", "deny"}
                ]
                agent["tool_catalog_state"] = "ok"
            except (httpx.HTTPError, TypeError, ValueError, KeyError):
                agent["tool_catalog"] = []
                agent["tool_catalog_state"] = "unavailable"
        agent["health"] = {"online": True}
        stored = self.repository.add_agent(agent)
        if stable_id:
            canonical = urlparse(agent_url)
            for existing in self.repository.list_agents():
                if existing["id"] == stable_id:
                    continue
                address = urlparse(existing.get("url", ""))
                same_local_endpoint = (
                    canonical.hostname in {"localhost", "127.0.0.1"}
                    and address.hostname in {"localhost", "127.0.0.1"}
                    and canonical.port == address.port
                )
                if same_local_endpoint:
                    self.repository.add_agent({
                        **existing,
                        "read_only": agent["read_only"],
                        "risk_level": agent["risk_level"],
                        "skills": agent["skills"],
                        "limitations": agent.get("limitations", []),
                        "tool_catalog": agent.get("tool_catalog", []),
                        "tool_catalog_state": agent.get("tool_catalog_state", "unavailable"),
                        "superseded_by": stable_id,
                    })
        return stored


def create_router(
    repository,
    service: AgentService,
    check_health: HealthChecker,
) -> APIRouter:
    router = APIRouter(prefix="/api/agents")

    @router.post("/list")
    async def list_agents():
        return ApiResponse(result=[
            agent for agent in repository.list_agents()
            if not agent.get("superseded_by")
        ])

    @router.post("/fetch-card")
    async def fetch_card(request: AgentRegister):
        try:
            card = await service.fetch_card(request.agentAddress)
            return ApiResponse(
                result=card.model_dump(mode="json", by_alias=True)
            )
        except Exception as exc:
            return ApiResponse(success=False, error=str(exc))

    @router.post("/register")
    async def register_agent(request: AgentRegister):
        try:
            return ApiResponse(
                result=await service.register(request.agentAddress)
            )
        except Exception as exc:
            return ApiResponse(success=False, error=str(exc))

    @router.post("/delete")
    async def delete_agent(data: dict):
        if not repository.delete_agent(data.get("agentId", "")):
            return ApiResponse(success=False, error="Agent not found")
        return ApiResponse()

    @router.post("/get")
    async def get_agent(data: dict):
        agent = repository.get_agent(data.get("agentId", ""))
        if not agent:
            return ApiResponse(success=False, error="Agent not found")
        return ApiResponse(result=agent)

    @router.post("/health-check")
    async def health_check():
        agents = [
            agent for agent in repository.list_agents()
            if not agent.get("superseded_by")
        ]
        if not agents:
            return ApiResponse(result=[])
        results = await asyncio.gather(
            *(check_health(agent["url"]) for agent in agents)
        )
        return ApiResponse(result={
            agent["id"]: health
            for agent, health in zip(agents, results)
        })

    return router
