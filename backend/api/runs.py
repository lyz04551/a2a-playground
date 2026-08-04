"""Unified Run, replay, cancellation, and system-status endpoints."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from backend.approvals.service import ApprovalService
from backend.models import ApiResponse
from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEvent


def encode_sse(event: RunEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def _error(message: str, *, status_code: int = 400) -> JSONResponse:
    payload = ApiResponse(success=False, error=message)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


def _command(data: dict[str, Any]) -> RunCommand:
    return RunCommand(
        conversation_id=data.get(
            "conversation_id", data.get("conversationId")
        ),
        mode=data.get("mode"),
        target_agent_id=data.get(
            "target_agent_id", data.get("targetAgentId")
        ),
        message=data.get("message", data.get("content", "")),
    )


def create_router(service) -> APIRouter:
    router = APIRouter()

    @router.post("/api/runs/stream")
    async def runs_stream(data: dict[str, Any]):
        try:
            command = _command(data)
        except ValidationError as exc:
            return _error(str(exc))

        async def event_stream():
            async for event in service.stream(command):
                yield encode_sse(event)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/api/runs/get")
    async def runs_get(data: dict[str, Any]):
        run = service.get(str(data.get("run_id") or data.get("runId") or ""))
        if run is None:
            return ApiResponse(success=False, error="Run not found")
        return ApiResponse(result=run)

    @router.post("/api/runs/list")
    async def runs_list():
        return ApiResponse(result=service.list())

    @router.post("/api/runs/events")
    async def runs_events(data: dict[str, Any]):
        run_id = str(data.get("run_id") or data.get("runId") or "")
        if service.get(run_id) is None:
            return ApiResponse(success=False, error="Run not found")
        try:
            after_sequence = int(
                data.get("after_sequence", data.get("afterSequence", 0))
            )
        except (TypeError, ValueError):
            return _error("after_sequence must be an integer")
        if after_sequence < 0:
            return _error("after_sequence must not be negative")
        return ApiResponse(
            result=[
                event.model_dump(mode="json")
                for event in service.events(run_id, after_sequence)
            ]
        )

    @router.post("/api/runs/cancel")
    async def runs_cancel(data: dict[str, Any]):
        run_id = str(data.get("run_id") or data.get("runId") or "")
        run = service.cancel(run_id)
        if run is None:
            return ApiResponse(success=False, error="Run not found")
        return ApiResponse(result=run)

    @router.post("/api/system/status")
    async def system_status():
        return ApiResponse(
            result={
                "model": {
                    "configured": bool(os.getenv("DEEPSEEK_API_KEY", "")),
                }
            }
        )

    return router


def create_approval_router(
    run_service,
    gateway,
    auto_host,
    *,
    logger: logging.Logger | None = None,
) -> APIRouter:
    """Expose the legacy approval wire contract through a router."""
    router = APIRouter()
    approval_service = ApprovalService(run_service.repository, gateway)
    route_logger = logger or logging.getLogger(__name__)

    @router.post("/api/approvals/list")
    async def approvals_list(data: dict[str, Any]):
        return ApiResponse(
            result=run_service.repository.list_approvals(data.get("run_id"))
        )

    @router.post("/api/approvals/decide")
    async def approvals_decide(data: dict[str, Any]):
        try:
            result = await approval_service.decide(
                data.get("approval_id", ""),
                data.get("decision", ""),
            )
            approval = result["approval"]
            execution = result.get("result", {})
            result_text = execution.get("text", "")
            if (
                approval["status"] == "approved"
                and execution.get("state") != "failed"
            ):
                try:
                    summary = await auto_host.summarize_approval_result(
                        approval,
                        result_text,
                    )
                    execution["raw_text"] = result_text
                    execution["text"] = summary
                    result_text = summary
                except Exception:
                    route_logger.warning(
                        "Host summary unavailable; using deterministic summary"
                    )
                    arguments = json.dumps(
                        approval.get("arguments", {}),
                        ensure_ascii=False,
                    )
                    execution["raw_text"] = execution.get("text", "")
                    result_text = (
                        "操作已批准并执行完成。\n\n"
                        f"- 执行工具：`{approval['tool_name']}`\n"
                        f"- 执行参数：`{arguments}`\n"
                        f"- MCP 结果：{result_text}"
                    )
                    execution["text"] = result_text
            if result_text:
                run_service.save_assistant_message(
                    approval["run_id"],
                    result_text,
                    task_id=execution.get("task_id"),
                    metadata={
                        "source": "approval",
                        "routing_agent": "Host Agent",
                        "executed_by": approval["agent_id"],
                        "approval_id": approval["id"],
                    },
                )
            return ApiResponse(result=result)
        except (KeyError, ValueError) as exc:
            return ApiResponse(success=False, error=str(exc))

    return router
