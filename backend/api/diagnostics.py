from __future__ import annotations

from fastapi import APIRouter

from backend.diagnostics import collect_connection_diagnostics
from backend.models import ApiResponse


def refresh_tool_catalogs(repository, agents: list[dict], result: dict) -> None:
    by_id = {agent["id"]: agent for agent in agents}
    for report in result.get("agents", []):
        agent = by_id.get(report.get("id"))
        if agent is None or "tool_catalog_state" not in agent:
            continue
        mcp = report.get("mcp") or {}
        tools = mcp.get("tools") if isinstance(mcp, dict) else None
        available = mcp.get("state") == "ok" and isinstance(tools, list)
        catalog = [
            {"name": tool["name"], "access": tool["access"]}
            for tool in (tools if available else [])
            if isinstance(tool, dict)
            and isinstance(tool.get("name"), str)
            and tool.get("access") in {"allow", "approval_required", "deny"}
        ]
        repository.add_agent({
            **agent,
            "tool_catalog": catalog,
            "tool_catalog_state": "ok" if available else "unavailable",
        })


def create_router(repository, model_config_service) -> APIRouter:
    router = APIRouter()

    @router.post("/api/diagnostics/connections")
    async def connection_diagnostics(data: dict):
        try:
            agents = [agent for agent in repository.list_agents() if not agent.get("superseded_by")]
            target = str(data.get("target") or "")
            result = await collect_connection_diagnostics(
                agents,
                model_config_service.resolve,
                target=target,
            )
            if target in {"mcp", "all"}:
                refresh_tool_catalogs(repository, agents, result)
            return ApiResponse(result=result)
        except ValueError as exc:
            return ApiResponse(success=False, error=str(exc))

    return router
