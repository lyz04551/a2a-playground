from __future__ import annotations

from fastapi import APIRouter

from backend.diagnostics import collect_connection_diagnostics
from backend.models import ApiResponse


def create_router(repository, model_config_service) -> APIRouter:
    router = APIRouter()

    @router.post("/api/diagnostics/connections")
    async def connection_diagnostics(data: dict):
        try:
            result = await collect_connection_diagnostics(
                repository.list_agents(),
                model_config_service.resolve,
                target=str(data.get("target") or ""),
            )
            return ApiResponse(result=result)
        except ValueError as exc:
            return ApiResponse(success=False, error=str(exc))

    return router
