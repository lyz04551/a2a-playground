from __future__ import annotations

import json
import os
import asyncio
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, create_react_agent

from .config import AgentRuntimeConfig, load_llm_config
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
        run_timeout: float | None = None,
    ):
        self.config = config
        self.prompt = (
            f"{prompt.rstrip()}\n\n"
            "工具调用规则：先规划完成任务所需的最小证据集；可并行调用不同工具；"
            "除非上次调用失败或数据明确失效，不要用相同参数重复调用同一工具；"
            "证据足以回答后立即停止调用并输出结论。"
        )
        self.mcp_client = mcp_client or K8sMCPClient(
            config.mcp_url, transport=config.mcp_transport
        )
        self._model = model
        self.run_timeout = run_timeout or float(
            os.getenv("AGENT_RUN_TIMEOUT", "90")
        )
        self.max_steps = int(os.getenv("AGENT_MAX_STEPS", "30"))
        self.max_tool_calls = int(os.getenv("AGENT_MAX_TOOL_CALLS", "40"))
        self._graph = None
        self._tools_loaded = False
        self._dependency_error = ""
        self._pending_by_context: dict[str, PendingAction] = {}
        self._tool_adapter: MCPToolAdapter | None = None

    async def ensure_ready(self) -> None:
        if self._tools_loaded:
            return
        try:
            definitions = await self.mcp_client.list_tools()
        except Exception as exc:
            self._dependency_error = str(exc)
            raise
        self._tool_adapter = MCPToolAdapter(
            self.mcp_client,
            ToolPolicy(self.config.tool_policy),
            agent_id=self.config.agent_id,
            max_calls=self.max_tool_calls,
        )
        tools = self._tool_adapter.build_tools(definitions)
        llm = load_llm_config("AGENT")
        model = self._model or ChatOpenAI(
            model=llm.model,
            openai_api_key=llm.api_key,
            openai_api_base=llm.base_url,
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
        self._dependency_error = ""

    def readiness(self) -> dict[str, Any]:
        mcp_state = "ok" if self._tools_loaded else "error"
        return {
            "state": "ready" if self._tools_loaded else "degraded",
            "checks": {
                "llm": {"state": "ok" if self._model or load_llm_config("AGENT").configured else "unknown"},
                "mcp": {"state": mcp_state, "detail": self._dependency_error},
                "kubernetes": {"state": "ok" if self._tools_loaded else "unknown"},
            },
        }

    async def warm_up(self, timeout: float = 0.25) -> bool:
        """Best-effort startup probe; requests retry initialization lazily."""
        try:
            await asyncio.wait_for(self.ensure_ready(), timeout=timeout)
            return True
        except TimeoutError:
            if not self._dependency_error:
                self._dependency_error = f"MCP warm-up timed out after {timeout:.2f}s"
            return False
        except Exception as exc:
            if not self._dependency_error:
                self._dependency_error = str(exc)
            return False

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

        graph_config = {
            "configurable": {"thread_id": context_id},
            "recursion_limit": self.max_steps,
        }
        if self._tool_adapter is not None:
            self._tool_adapter.reset_budget(context_id)
        seen_tool_calls: set[str] = set()
        seen_tool_results: set[str] = set()
        try:
            previous = self._graph.get_state(graph_config)
            for message in previous.values.get("messages", []):
                if isinstance(message, AIMessage):
                    seen_tool_calls.update(
                        str(call["id"]) for call in message.tool_calls
                    )
                elif isinstance(message, ToolMessage):
                    seen_tool_results.add(str(message.tool_call_id or ""))
        except (AttributeError, KeyError, TypeError, ValueError):
            # A new context may not have a checkpoint yet.
            pass
        try:
            async with asyncio.timeout(self.run_timeout):
                async for state in self._graph.astream(
                    {"messages": [("user", query)]},
                    graph_config,
                    stream_mode="values",
                ):
                    messages = state.get("messages", [])
                    if not messages:
                        continue
                    for message in messages:
                        if isinstance(message, AIMessage) and message.tool_calls:
                            for call in message.tool_calls:
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
                        elif isinstance(message, ToolMessage):
                            call_id = str(message.tool_call_id or "")
                            if call_id in seen_tool_results:
                                continue
                            seen_tool_results.add(call_id)
                            yield RuntimeEvent(
                                type=RuntimeEventType.TOOL_RESULT,
                                content=str(message.content),
                                data={
                                    "tool_call_id": call_id,
                                    "result": str(message.content),
                                },
                            )
        except ApprovalRequired as exc:
            self._pending_by_context[context_id] = exc.pending_action
            yield RuntimeEvent.approval_required(exc.pending_action)
            return
        except TimeoutError:
            yield RuntimeEvent(
                type=RuntimeEventType.ERROR,
                content=f"Agent execution timed out after {self.run_timeout:g}s",
                is_task_complete=True,
            )
            return

        state = self._graph.get_state(graph_config)
        messages = state.values.get("messages", [])
        content = ""
        if messages and isinstance(messages[-1], AIMessage):
            content = str(messages[-1].content or "")
        yield RuntimeEvent.completed(
            content=content or "处理完成，但未生成文本响应。",
            artifact_name="specialist_result",
            data={
                "status": "completed",
                "summary": content,
                "findings": [],
                "resources": [],
                "evidence": [],
                "recommendations": [],
                "continuation": {"allowed": None, "reason": ""},
                "limitations": [],
            },
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
        if pending is None:
            try:
                pending = PendingAction.from_call(
                    approval_id=str(approval.get("approval_id") or ""),
                    agent_id=str(approval.get("agent_id") or ""),
                    tool_name=str(approval.get("tool_name") or ""),
                    arguments=dict(approval.get("arguments") or {}),
                )
            except (TypeError, ValueError):
                pending = None
            if (
                pending is None
                or pending.agent_id != self.config.agent_id
                or pending.action_digest != approval.get("action_digest")
            ):
                pending = None
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
                artifact_name="specialist_result",
                data={
                    "status": "blocked",
                    "summary": "用户已拒绝该变更，未执行任何写操作。",
                    "continuation": {
                        "allowed": False,
                        "reason": "approval rejected",
                    },
                },
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
            artifact_name="specialist_result",
            data={
                "status": "completed",
                "summary": str(result),
                "evidence": [{
                    "tool": pending.tool_name,
                    "arguments": pending.arguments,
                    "result": result,
                }],
                "continuation": {
                    "allowed": True,
                    "reason": "approved MCP action completed",
                },
            },
        )


def load_prompt(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
