from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter

from backend.models import Agent, AgentRegister, ApiResponse


CardFetcher = Callable[[str], Awaitable[Any]]
HealthChecker = Callable[[str], Awaitable[dict[str, Any]]]


class AgentService:
    def __init__(self, repository, fetch_card: CardFetcher):
        self.repository = repository
        self.fetch_card = fetch_card

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
            read_only=risk_level != "write_approval",
            risk_level=risk_level or "read_only",
        ).model_dump()
        agent["health"] = {"online": True}
        return self.repository.add_agent(agent)


def create_router(
    repository,
    service: AgentService,
    check_health: HealthChecker,
) -> APIRouter:
    router = APIRouter(prefix="/api/agents")

    @router.post("/list")
    async def list_agents():
        return ApiResponse(result=repository.list_agents())

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
        agents = repository.list_agents()
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
