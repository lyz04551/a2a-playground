from __future__ import annotations

import json
import os
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, create_react_agent

from .config import AgentRuntimeConfig
from .mcp_client import K8sMCPClient
from .models import ApprovalRequired, PendingAction
from .streaming import RuntimeEvent, RuntimeEventType
from .tool_adapter import MCPToolAdapter
from .tool_policy import ToolPolicy


def _handle_tool_error(exc: Exception) -> str:
    if isinstance(exc, ApprovalRequired):
        raise exc
    return f"工具执行失败：{exc}"


class RuntimeMCPAgent:
    """LangGraph agent that exposes policy-filtered MCP tools over A2A."""

    def __init__(
        self,
        config: AgentRuntimeConfig,
        prompt: str,
        *,
        mcp_client: K8sMCPClient | None = None,
        model=None,
    ):
        self.config = config
        self.prompt = prompt
        self.mcp_client = mcp_client or K8sMCPClient(config.mcp_url)
        self._model = model
        self._graph = None
        self._tools_loaded = False
        self._pending_by_context: dict[str, PendingAction] = {}

    async def ensure_ready(self) -> None:
        if self._tools_loaded:
            return
        definitions = await self.mcp_client.list_tools()
        tools = MCPToolAdapter(
            self.mcp_client,
            ToolPolicy(self.config.tool_policy),
            agent_id=self.config.agent_id,
        ).build_tools(definitions)
        model = self._model or ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            openai_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            openai_api_base=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
            ),
            temperature=0,
            streaming=True,
        )
        self._graph = create_react_agent(
            model,
            tools=ToolNode(tools, handle_tool_errors=_handle_tool_error),
            prompt=self.prompt,
            checkpointer=MemorySaver(),
        )
        self._tools_loaded = True

    async def shutdown(self) -> None:
        await self.mcp_client.disconnect()

    async def stream(
        self, query: str, context_id: str
    ) -> AsyncIterable[RuntimeEvent]:
        approval = self._parse_approval(query)
        if approval is not None:
            async for event in self._resume_approved(context_id, approval):
                yield event
            return

        try:
            await self.ensure_ready()
        except Exception as exc:
            yield RuntimeEvent(
                type=RuntimeEventType.ERROR,
                content=f"MCP dependency unavailable: {exc}",
                is_task_complete=True,
            )
            return

        graph_config = {"configurable": {"thread_id": context_id}}
        seen_tool_calls: set[str] = set()
        try:
            async for state in self._graph.astream(
                {"messages": [("user", query)]},
                graph_config,
                stream_mode="values",
            ):
                messages = state.get("messages", [])
                if not messages:
                    continue
                last = messages[-1]
                if isinstance(last, AIMessage) and last.tool_calls:
                    for call in last.tool_calls:
                        if call["id"] in seen_tool_calls:
                            continue
                        seen_tool_calls.add(call["id"])
                        yield RuntimeEvent(
                            type=RuntimeEventType.TOOL_CALL,
                            content=call["name"],
                            data={
                                "id": call["id"],
                                "tool": call["name"],
                                "arguments": call.get("args", {}),
                            },
                        )
                elif isinstance(last, ToolMessage):
                    yield RuntimeEvent(
                        type=RuntimeEventType.TOOL_RESULT,
                        content=str(last.content),
                        data={
                            "tool_call_id": last.tool_call_id,
                            "result": str(last.content),
                        },
                    )
        except ApprovalRequired as exc:
            self._pending_by_context[context_id] = exc.pending_action
            yield RuntimeEvent.approval_required(exc.pending_action)
            return

        state = self._graph.get_state(graph_config)
        messages = state.values.get("messages", [])
        content = ""
        if messages and isinstance(messages[-1], AIMessage):
            content = str(messages[-1].content or "")
        yield RuntimeEvent.completed(
            content=content or "处理完成，但未生成文本响应。",
            artifact_name=f"{self.config.agent_id}_result",
            data={"text": content},
        )

    @staticmethod
    def _parse_approval(query: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(query)
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if payload.get("type") == "approval_decision" else None

    async def _resume_approved(
        self, context_id: str, approval: dict[str, Any]
    ) -> AsyncIterable[RuntimeEvent]:
        pending = self._pending_by_context.get(context_id)
        if pending is None or pending.approval_id != approval.get("approval_id"):
            yield RuntimeEvent(
                type=RuntimeEventType.ERROR,
                content="Approval does not match a pending action.",
                is_task_complete=True,
            )
            return
        if approval.get("decision") != "approved":
            self._pending_by_context.pop(context_id, None)
            yield RuntimeEvent.completed(
                content="用户已拒绝该变更，未执行任何写操作。",
                artifact_name="approval_rejected",
                data=pending.model_dump(),
            )
            return
        if approval.get("action_digest") != pending.action_digest:
            yield RuntimeEvent(
                type=RuntimeEventType.ERROR,
                content="Approved action digest does not match.",
                is_task_complete=True,
            )
            return
        result = await self.mcp_client.call_tool(
            pending.tool_name, pending.arguments
        )
        self._pending_by_context.pop(context_id, None)
        yield RuntimeEvent.completed(
            content=result,
            artifact_name="execution_result",
            data={
                "pending_action": pending.model_dump(),
                "result": result,
            },
        )


def load_prompt(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
