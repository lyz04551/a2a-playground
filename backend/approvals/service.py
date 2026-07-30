from __future__ import annotations

import json


class ApprovalService:
    def __init__(self, repository, gateway):
        self.repository = repository
        self.gateway = gateway

    async def decide(self, approval_id: str, decision: str) -> dict:
        approval = self.repository.decide_approval(
            approval_id, decision
        )
        agent = self.repository.get_agent(approval["agent_id"])
        if agent is None:
            raise ValueError("approval agent is no longer registered")
        continuation = json.dumps(
            {
                "type": "approval_decision",
                "approval_id": approval["id"],
                "decision": decision,
                "action_digest": approval["action_digest"],
            },
            ensure_ascii=False,
        )
        result = await self.gateway.delegate(
            approval["run_id"], agent, continuation
        )
        result = {
            **result,
            "text": self._execution_text(result),
        }
        run_status = (
            "approval_required"
            if result.get("approval")
            else "failed"
            if result.get("state") == "failed"
            else "completed"
        )
        self.repository.update_run_status(
            approval["run_id"], run_status,
        )
        return {"approval": approval, "result": result}

    @staticmethod
    def _execution_text(result: dict) -> str:
        for artifact in reversed(result.get("artifacts", [])):
            if artifact.get("name") != "execution_result":
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
                value = payload.get("result", payload.get("text", ""))
                if isinstance(value, str):
                    try:
                        decoded = json.loads(value)
                        return decoded if isinstance(decoded, str) else value
                    except json.JSONDecodeError:
                        return value
                return json.dumps(value, ensure_ascii=False)
        return result.get("text") or "操作已完成。"
