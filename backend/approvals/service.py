from __future__ import annotations

import json

from backend.orchestration.events import RunEvent, RunEventType


class ApprovalService:
    def __init__(self, repository, gateway):
        self.repository = repository
        self.gateway = gateway

    def claim(self, approval_id: str, decision: str) -> tuple[dict, bool]:
        return self.repository.claim_approval_decision(
            approval_id, decision
        )

    @staticmethod
    def duplicate_result(approval: dict) -> dict:
        return {
            "approval": approval,
            "result": {
                "state": "already_decided",
                "text": "审批已处理，未重复执行。",
            },
        }

    async def decide(self, approval_id: str, decision: str) -> dict:
        approval, claimed = self.claim(approval_id, decision)
        if not claimed:
            return self.duplicate_result(approval)
        return await self.execute_claimed(approval)

    async def execute_claimed(self, approval: dict) -> dict:
        agent = self.repository.get_agent(approval["agent_id"])
        if agent is None:
            raise ValueError("approval agent is no longer registered")
        continuation = json.dumps(
            {
                "type": "approval_decision",
                "approval_id": approval["id"],
                "agent_id": approval["agent_id"],
                "decision": approval["status"],
                "tool_name": approval["tool_name"],
                "arguments": approval["arguments"],
                "action_digest": approval["action_digest"],
            },
            ensure_ascii=False,
        )
        result = await self.gateway.delegate(approval["run_id"], agent, continuation)
        result = {
            **result,
            "text": self._execution_text(result),
        }
        run = self.repository.get_run(approval["run_id"]) or {}
        if run.get("mode") != "auto":
            self._finalize_direct_run(approval, result, run)
        run_status = (
            "approval_required"
            if result.get("approval")
            else (
                "failed"
                if result.get("state") == "failed"
                else "running" if run.get("mode") == "auto" else "completed"
            )
        )
        self.repository.update_run_status(
            approval["run_id"],
            run_status,
        )
        return {"approval": approval, "result": result}

    def _finalize_direct_run(self, approval: dict, result: dict, run: dict) -> None:
        run_id = approval["run_id"]
        persisted = self.repository.list_run_events(run_id)
        completed_call_ids = {
            str(event.data.get("tool_call_id") or event.data.get("id") or "")
            for event in persisted
            if event.type == RunEventType.TOOL_COMPLETED
        }
        tool_call = next(
            (
                event
                for event in reversed(persisted)
                if event.type == RunEventType.TOOL_CALLED
                and str(event.data.get("tool_call_id") or event.data.get("id") or "")
                not in completed_call_ids
                and (event.data.get("tool") or event.data.get("tool_name"))
                == approval["tool_name"]
                and (event.data.get("arguments") or event.data.get("args") or {})
                == approval["arguments"]
            ),
            None,
        )
        task_id = (
            tool_call.task_id if tool_call is not None else run.get("root_task_id")
        )
        task = self.repository.get_task(task_id) if task_id else None
        parent_task_id = task.get("parent_task_id") if task else None
        conversation_id = run["conversation_id"]
        sequence = persisted[-1].sequence + 1 if persisted else 1

        def persist(event_type: RunEventType, data: dict) -> None:
            nonlocal sequence
            saved = self.repository.append_run_event(
                RunEvent.create(
                    event_type=event_type,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    sequence=sequence,
                    task_id=task_id,
                    parent_task_id=parent_task_id,
                    data={"agent_id": approval["agent_id"], **data},
                )
            )
            sequence = saved.sequence + 1

        persist(
            RunEventType.APPROVAL_DECIDED,
            {
                "approval_id": approval["id"],
                "decision": approval["status"],
            },
        )

        approved = approval["status"] == "approved"
        execution_failed = result.get("state") in {"failed", "error"}
        succeeded = approved and not execution_failed
        tool_call_id = (
            str(tool_call.data.get("tool_call_id") or tool_call.data.get("id") or "")
            if tool_call is not None
            else ""
        )
        tool_data = {
            "tool_call_id": tool_call_id,
            "tool": approval["tool_name"],
        }
        if succeeded:
            tool_data["result"] = result.get("text") or "操作已完成。"
        else:
            tool_data["error"] = (
                result.get("error") or result.get("text") or "用户拒绝了该操作。"
            )
        persist(RunEventType.TOOL_COMPLETED, tool_data)

        if succeeded:
            task_event = RunEventType.TASK_COMPLETED
            task_status = "completed"
            run_event = RunEventType.RUN_COMPLETED
            run_status = "completed"
        elif not approved:
            task_event = RunEventType.TASK_BLOCKED
            task_status = "blocked"
            run_event = RunEventType.RUN_COMPLETED
            run_status = "completed"
        else:
            task_event = RunEventType.TASK_FAILED
            task_status = "failed"
            run_event = RunEventType.RUN_FAILED
            run_status = "failed"

        persist(
            task_event,
            {
                "result": result.get("text", "") if succeeded else "",
                "reason": "" if succeeded else tool_data["error"],
            },
        )
        if task_id:
            self.repository.update_task(task_id, {"status": task_status})
        self.repository.update_run_status(run_id, run_status)
        persist(
            run_event,
            {
                **({} if run_status == "completed" else {"error": tool_data["error"]}),
            },
        )

    @staticmethod
    def _execution_text(result: dict) -> str:
        for artifact in reversed(result.get("artifacts", [])):
            if artifact.get("name") not in {
                "execution_result",
                "specialist_result",
            }:
                continue
            for part in artifact.get("parts", []):
                root = part.get("root", part)
                text = root.get("text") if isinstance(root, dict) else None
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    return text
                value = payload.get(
                    "result",
                    payload.get("summary", payload.get("text", "")),
                )
                if isinstance(value, str):
                    try:
                        decoded = json.loads(value)
                        return decoded if isinstance(decoded, str) else value
                    except json.JSONDecodeError:
                        return value
                return json.dumps(value, ensure_ascii=False)
        return result.get("text") or "操作已完成。"
