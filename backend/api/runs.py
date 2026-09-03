"""Unified Run, replay, cancellation, and system-status endpoints."""

from __future__ import annotations

import json
import logging
import os
import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from backend.approvals.service import ApprovalService
from backend.models import ApiResponse
from backend.orchestration.commands import RunCommand
from backend.orchestration.events import RunEvent
from backend.llm_config import load_llm_config


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


def _schedule_auto_resume(
    run_service,
    approval: dict[str, Any],
    execution: dict[str, Any],
    background_tasks: set[asyncio.Task],
    logger: logging.Logger | None = None,
) -> asyncio.Task:
    run_id = approval["run_id"]
    run_service.repository.update_run_status(run_id, "running")

    async def resume() -> None:
        try:
            await run_service.resume_after_approval(approval, execution)
        except Exception:
            (logger or logging.getLogger(__name__)).exception(
                "Unable to resume Auto Run %s after approval", run_id
            )
            run_service.repository.update_run_status(run_id, "failed")

    task = asyncio.create_task(resume())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task


def _schedule_auto_approval_execution(
    approval_service,
    run_service,
    approval: dict[str, Any],
    background_tasks: set[asyncio.Task],
    logger: logging.Logger | None = None,
) -> asyncio.Task:
    run_id = approval["run_id"]
    run_service.repository.update_run_status(run_id, "running")

    async def execute_and_resume() -> None:
        try:
            outcome = await approval_service.execute_claimed(approval)
            execution = outcome.get("result", {})
        except Exception as exc:
            (logger or logging.getLogger(__name__)).exception(
                "Unable to execute approval %s", approval.get("id")
            )
            execution = {
                "state": "failed",
                "text": str(exc),
                "error": str(exc),
            }
        await run_service.resume_after_approval(approval, execution)

    task = asyncio.create_task(execute_and_resume())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task


def create_router(service) -> APIRouter:
    router = APIRouter()
    background_runs: set[asyncio.Task] = set()

    @router.post("/api/runs/stream")
    async def runs_stream(data: dict[str, Any]):
        try:
            command = _command(data)
        except ValidationError as exc:
            return _error(str(exc))

        reconnect_run_id = str(data.get("run_id") or data.get("runId") or "")
        if reconnect_run_id:
            if service.get(reconnect_run_id) is None:
                return _error("Run not found", status_code=404)
            try:
                after_sequence = max(0, int(data.get("after_sequence", 0)))
            except (TypeError, ValueError):
                return _error("after_sequence must be an integer")

            async def event_stream():
                cursor = after_sequence
                generation = service._event_generations.get(reconnect_run_id, 0)
                while True:
                    events = service.events(reconnect_run_id, cursor)
                    for event in events:
                        cursor = max(cursor, event.sequence)
                        yield encode_sse(event)
                    run = service.get(reconnect_run_id)
                    if run is None or run["status"] in {
                        "completed", "failed", "cancelled", "interrupted", "approval_required"
                    }:
                        return
                    next_generation = await service.wait_for_events(reconnect_run_id, generation)
                    if next_generation == generation:
                        yield ": heartbeat\n\n"
                    generation = next_generation
        else:
            queue: asyncio.Queue = asyncio.Queue()

            async def produce():
                try:
                    async for event in service.stream(command):
                        await queue.put(event)
                finally:
                    await queue.put(None)

            producer = asyncio.create_task(produce())
            background_runs.add(producer)
            producer.add_done_callback(background_runs.discard)

            async def event_stream():
                while True:
                    event = await queue.get()
                    if event is None:
                        return
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
    async def runs_list(data: dict | None = None):
        data = data or {}
        if "page" not in data and "page_size" not in data and "pageSize" not in data:
            return ApiResponse(result=service.list())
        try:
            page = max(1, int(data.get("page", 1)))
            size = min(100, max(1, int(data.get("page_size", data.get("pageSize", 20)))))
        except (TypeError, ValueError):
            return _error("page and page_size must be integers")
        total = service.repository.count_runs()
        return ApiResponse(result={
            "items": service.list(limit=size, offset=(page - 1) * size),
            "page": page, "page_size": size, "total": total,
            "has_more": page * size < total,
        })

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
        model = load_llm_config("HOST")
        return ApiResponse(
            result={
                "model": {"configured": model.configured},
                "model_details": {
                    key: value
                    for key, value in model.public().items()
                    if key != "configured"
                },
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
    background_resumes: set[asyncio.Task] = set()
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
            approval, claimed = approval_service.claim(
                data.get("approval_id", ""),
                data.get("decision", ""),
            )
            run = run_service.repository.get_run(approval["run_id"]) or {}
            if run.get("mode") == "auto":
                if claimed:
                    _schedule_auto_approval_execution(
                        approval_service,
                        run_service,
                        approval,
                        background_resumes,
                        route_logger,
                    )
                return ApiResponse(result={
                    "approval": approval,
                    "result": {
                        "state": "accepted" if claimed else "already_decided",
                        "text": (
                            "审批决定已接受，正在执行。"
                            if claimed
                            else "审批已处理，未重复执行。"
                        ),
                    },
                    "resume_started": claimed,
                })

            result = (
                await approval_service.execute_claimed(approval)
                if claimed
                else approval_service.duplicate_result(approval)
            )
            execution = result.get("result", {})
            result_text = execution.get("text", "")
            # A serial multi-write approval returns control to a follow-up
            # approval instead of a terminal result; do not summarise it as a
            # finished action (the final approval in the chain will be).
            followup_required = bool(
                execution.get("approval")
            ) and execution.get("state") == "input-required"
            if (
                approval["status"] == "approved"
                and execution.get("state") != "failed"
                and not followup_required
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
