"""Model and Agent-card support for the structured Host orchestrator."""

import json
import logging
import os
import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from a2a.types import AgentCard
from backend.llm_config import load_llm_config

logger = logging.getLogger(__name__)

class LangGraphHostAgent:
    """Supplies the Host model, registered cards, and approval summaries."""

    def __init__(self, gateway=None):
        self.cards: dict[str, AgentCard] = {}
        self.agents: dict[str, dict] = {}

    def register_agent_card(self, agent_id: str, card: AgentCard):
        self.cards[agent_id] = card
        self.agents[agent_id] = {
            "id": agent_id,
            "name": card.name or agent_id,
            "url": card.url,
        }

    def unregister_agent(self, agent_id: str):
        self.cards.pop(agent_id, None)
        self.agents.pop(agent_id, None)

    @staticmethod
    def _make_model(*, streaming: bool = True):
        config = load_llm_config("HOST")
        return ChatOpenAI(
            model=config.model,
            openai_api_key=config.api_key,
            openai_api_base=config.base_url,
            temperature=0,
            streaming=streaming,
            request_timeout=float(
                os.getenv("HOST_LLM_TIMEOUT_SECONDS", "90")
            ),
            max_retries=0,
        )

    async def summarize_approval_result(
        self,
        approval: dict,
        execution_result: str,
    ) -> str:
        messages = [
            SystemMessage(content=(
                "你是 Host Agent。用户已经通过正式审批，子智能体也已经完成"
                " Kubernetes 写操作。请根据审批参数和 MCP 执行结果，用中文向"
                "用户给出简洁明确的执行总结。不要调用任何工具，不要再次请求"
                "审批，也不要声称尚未执行。"
            )),
            HumanMessage(content=json.dumps({
                "tool_name": approval.get("tool_name"),
                "arguments": approval.get("arguments", {}),
                "decision": approval.get("status"),
                "mcp_result": execution_result,
            }, ensure_ascii=False)),
        ]
        model = self._make_model(streaming=False)
        for attempt, delay in enumerate((0, 0.5, 1.5)):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await model.ainvoke(messages)
                return str(response.content or execution_result)
            except Exception as exc:
                is_busy = getattr(exc, "status_code", None) == 503
                if not is_busy or attempt == 2:
                    raise
        return execution_result
