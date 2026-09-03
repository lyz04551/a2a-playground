from __future__ import annotations

import json
import os
import asyncio
import uuid
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import ToolNode, create_react_agent

from .config import AgentRuntimeConfig, load_llm_config
from .checkpoint import PostgresCheckpointManager
from .mcp_client import K8sMCPClient
from .models import ApprovalRequired, PendingAction, PolicyAction
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
        summary_reserve_seconds: float | None = None,
        timeout_safety_margin_seconds: float | None = None,
        checkpoint_database_url: str | None = None,
    ):
        self.config = config
        self.prompt = (
            f"{prompt.rstrip()}\n\n"
            "工具调用规则：先规划完成任务所需的最小证据集；可并行调用不同工具；"
            "除非上次调用失败或数据明确失效，不要用相同参数重复调用同一工具；"
            "每批工具结果返回后，必须先判断现有证据是否已经足以回答用户；"
            "证据足够时立即停止调用并输出结论。继续调用前必须能指出尚缺的关键"
            "证据，且不得擅自扩大 cluster、namespace、资源类型或对象范围。"
        )
        self.mcp_client = mcp_client or K8sMCPClient(
            config.mcp_url, transport=config.mcp_transport
        )
        self._model = model
        self.checkpoint_database_url = (
            os.getenv("AGENT_CHECKPOINT_DATABASE_URL", "")
            if checkpoint_database_url is None
            else checkpoint_database_url
        )
        self.run_timeout = run_timeout or float(os.getenv("AGENT_RUN_TIMEOUT", "90"))
        configured_summary_reserve = os.getenv("AGENT_SUMMARY_RESERVE_SECONDS")
        self.summary_reserve_seconds = (
            summary_reserve_seconds
            if summary_reserve_seconds is not None
            else (
                float(configured_summary_reserve)
                if configured_summary_reserve is not None
                else min(35.0, self.run_timeout * 0.2)
            )
        )
        configured_safety_margin = os.getenv("AGENT_TIMEOUT_SAFETY_MARGIN_SECONDS")
        self.timeout_safety_margin_seconds = (
            timeout_safety_margin_seconds
            if timeout_safety_margin_seconds is not None
            else (
                float(configured_safety_margin)
                if configured_safety_margin is not None
                else min(5.0, self.run_timeout * 0.05)
            )
        )
        self.investigation_timeout = (
            self.run_timeout
            - self.summary_reserve_seconds
            - self.timeout_safety_margin_seconds
        )
        if self.investigation_timeout <= 0:
            raise ValueError(
                "AGENT_RUN_TIMEOUT must exceed the summary reserve and safety margin"
            )
        self.max_steps = int(os.getenv("AGENT_MAX_STEPS", "30"))
        self.max_tool_calls = int(os.getenv("AGENT_MAX_TOOL_CALLS", "40"))
        self.tool_budget_warning_ratio = float(
            os.getenv("AGENT_TOOL_BUDGET_WARNING_RATIO", "0.6")
        )
        self._graph = None
        self._tools_loaded = False
        self._dependency_error = ""
        self._pending_by_context: dict[str, PendingAction] = {}
        self._tool_adapter: MCPToolAdapter | None = None
        self._checkpoint_manager: PostgresCheckpointManager | None = None
        self._checkpointer = None

    async def ensure_ready(self) -> None:
        if self._tools_loaded:
            return
        if not self.checkpoint_database_url:
            self._dependency_error = (
                "AGENT_CHECKPOINT_DATABASE_URL is required"
            )
            raise RuntimeError(self._dependency_error)
        try:
            if self._checkpoint_manager is None:
                self._checkpoint_manager = PostgresCheckpointManager(
                    self.checkpoint_database_url
                )
            self._checkpointer = await self._checkpoint_manager.open()
            definitions = await self.mcp_client.list_tools()
        except Exception as exc:
            self._dependency_error = str(exc)
            if self._checkpoint_manager is not None:
                await self._checkpoint_manager.close()
                self._checkpoint_manager = None
                self._checkpointer = None
            raise
        self._tool_adapter = MCPToolAdapter(
            self.mcp_client,
            ToolPolicy(self.config.tool_policy),
            agent_id=self.config.agent_id,
            max_calls=self.max_tool_calls,
            soft_budget_ratio=self.tool_budget_warning_ratio,
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
        self._model = model
        self._graph = create_react_agent(
            model,
            tools=ToolNode(tools, handle_tool_errors=_handle_tool_error),
            prompt=self.prompt,
            checkpointer=self._checkpointer,
        )
        self._tools_loaded = True
        self._dependency_error = ""

    def readiness(self) -> dict[str, Any]:
        mcp_state = "ok" if self._tools_loaded else "error"
        checkpoint_state = "ok" if self._checkpointer is not None else "error"
        return {
            "state": "ready" if self._tools_loaded else "degraded",
            "checks": {
                "llm": {
                    "state": (
                        "ok"
                        if self._model or load_llm_config("AGENT").configured
                        else "unknown"
                    )
                },
                "mcp": {"state": mcp_state, "detail": self._dependency_error},
                "checkpoint": {
                    "state": checkpoint_state,
                    "detail": (
                        ""
                        if checkpoint_state == "ok"
                        else self._dependency_error
                    ),
                },
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
        if self._checkpoint_manager is not None:
            await self._checkpoint_manager.close()
            self._checkpoint_manager = None
            self._checkpointer = None
        self._tools_loaded = False
        await self.mcp_client.disconnect()

    async def stream(self, query: str, context_id: str) -> AsyncIterable[RuntimeEvent]:
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
            previous = await self._graph.aget_state(graph_config)
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
            async with asyncio.timeout(self.investigation_timeout):
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
        except (TimeoutError, GraphRecursionError) as cutoff:
            cutoff_reason = (
                "investigation time budget reached"
                if isinstance(cutoff, TimeoutError)
                else "investigation step budget reached"
            )
            try:
                content = await self._force_summary(query, graph_config)
            except TimeoutError:
                content = await self._deterministic_partial_summary(
                    graph_config,
                    "强制总结模型也达到时间限制",
                )
            except Exception as exc:
                content = await self._deterministic_partial_summary(
                    graph_config,
                    f"强制总结模型不可用：{exc}",
                )
            yield RuntimeEvent.completed(
                content=content,
                artifact_name="specialist_result",
                data={
                    "status": "partial",
                    "summary": content,
                    "findings": [],
                    "resources": [],
                    "evidence": [],
                    "recommendations": [],
                    "continuation": {
                        "allowed": True,
                        "reason": cutoff_reason,
                    },
                    "limitations": [
                        "调查阶段达到时间预算，以上结论仅基于已完成的检查。"
                    ],
                },
            )
            return

        state = await self._graph.aget_state(graph_config)
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

    async def _force_summary(self, query: str, graph_config: dict) -> str:
        if self._model is None:
            raise RuntimeError("Agent model is unavailable for forced summary")
        evidence = await self._bounded_checkpoint_evidence(graph_config)
        prompt = (
            "调查阶段的时间预算已经用完。禁止调用任何工具。请仅根据下面已经取得的"
            "证据回答用户，优先说明已确认的问题、证据和建议，并明确指出哪些检查尚未"
            "完成。不要声称执行了证据中没有出现的检查。\n\n"
            f"用户问题：{query}\n\n已取得证据：\n{evidence}"
        )
        async with asyncio.timeout(self.summary_reserve_seconds):
            response = await self._model.ainvoke([HumanMessage(content=prompt)])
        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            raise RuntimeError("Agent model returned an empty forced summary")
        return content

    async def _deterministic_partial_summary(
        self, graph_config: dict, reason: str
    ) -> str:
        evidence = await self._bounded_checkpoint_evidence(graph_config)
        return (
            "本次调查已达到时间预算，已停止继续调用工具。\n\n"
            f"已取得的结果：\n{evidence[:6_000]}\n\n"
            f"限制：{reason}。以上是部分结果；后续检查和任何尚未进入审批的写操作"
            "均未执行。"
        )

    async def _bounded_checkpoint_evidence(self, graph_config: dict) -> str:
        try:
            state = await self._graph.aget_state(graph_config)
            messages = state.values.get("messages", [])
        except (AttributeError, KeyError, TypeError, ValueError):
            messages = []

        chunks: list[str] = []
        remaining = 40_000
        for message in messages:
            if not isinstance(message, ToolMessage):
                continue
            content = str(message.content or "")
            if not content:
                continue
            excerpt = content[: min(6_000, remaining)]
            chunks.append(
                f"- 工具调用 {message.tool_call_id or 'unknown'} 的结果：{excerpt}"
            )
            remaining -= len(excerpt)
            if remaining <= 0:
                break
        return "\n".join(chunks) or "没有可用的已完成工具结果。"

    @staticmethod
    def _parse_approval(query: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(query)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
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
            await self._close_pending_tool_call(
                context_id,
                pending,
                "用户拒绝了该工具调用，未执行任何写操作。",
            )
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
        try:
            result = await self.mcp_client.call_tool(
                pending.tool_name, pending.arguments
            )
        except Exception as exc:
            error = f"MCP tool {pending.tool_name} failed: {exc}"
            self._pending_by_context.pop(context_id, None)
            await self._close_pending_tool_call(context_id, pending, error)
            yield RuntimeEvent(
                type=RuntimeEventType.ERROR,
                content=error,
                is_task_complete=True,
            )
            return
        self._pending_by_context.pop(context_id, None)
        await self._close_pending_tool_call(context_id, pending, str(result))
        async for event in self._settle_interrupted_batch(
            context_id, pending, result
        ):
            yield event

    def _requires_approval(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> bool:
        """Whether this tool call needs an approval before it may run.

        Falls back to treating unknown calls as approval-gated so the settle
        loop never auto-executes a call whose policy it cannot classify.
        """
        adapter = self._tool_adapter
        policy = getattr(adapter, "policy", None) if adapter is not None else None
        if policy is None:
            return True
        return (
            policy.classify(tool_name, arguments).action
            is PolicyAction.APPROVAL_REQUIRED
        )

    async def _settle_interrupted_batch(
        self,
        context_id: str,
        pending: PendingAction,
        result: Any,
    ) -> AsyncIterable[RuntimeEvent]:
        """Resolve every call of an interrupted batch before the graph resumes.

        LangGraph's ToolNode aborts the whole batch on the first
        ApprovalRequired, so the remaining sibling calls never ran and have no
        ToolMessage. Resuming a partially-resolved batch crashes LangGraph (an
        AIMessage whose sibling calls still lack results cannot be continued),
        which is the source of the "Agent stream failed" failures. So this
        helper drains the batch first: each remaining approval-gated call is
        surfaced as its own serial approval, and any allowed sibling call that
        ToolNode never reached is executed now. Only once every call in the
        interrupted AIMessage has a ToolMessage is a terminal event emitted.
        """
        parts = [str(result)]
        evidence = [
            {
                "tool": pending.tool_name,
                "arguments": pending.arguments,
                "result": result,
            }
        ]
        while True:
            unresolved = await self._pending_batch_unresolved(context_id)
            if not unresolved:
                break
            call = unresolved[0]
            name = str(call.get("name") or "")
            arguments = dict(call.get("args") or {})
            call_id = str(call.get("id") or "")
            if self._requires_approval(name, arguments):
                next_pending = PendingAction.from_call(
                    approval_id=f"ap_{uuid.uuid4().hex}",
                    agent_id=self.config.agent_id,
                    tool_name=name,
                    arguments=arguments,
                    reason="Write operation requires explicit user approval",
                )
                self._pending_by_context[context_id] = next_pending
                yield RuntimeEvent.approval_required(next_pending)
                return
            try:
                sibling_result = await self.mcp_client.call_tool(
                    name, arguments
                )
            except Exception as exc:
                sibling_result = f"工具执行失败：{exc}"
            await self._inject_tool_message(
                context_id, call_id, str(sibling_result)
            )
            parts.append(str(sibling_result))
            evidence.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "result": sibling_result,
                }
            )
        content = "\n\n".join(parts)
        yield RuntimeEvent.completed(
            content=content,
            artifact_name="specialist_result",
            data={
                "status": "completed",
                "summary": content,
                "evidence": evidence,
                "continuation": {
                    "allowed": True,
                    "reason": "approved MCP actions completed",
                },
            },
        )

    async def _pending_batch_unresolved(
        self, context_id: str
    ) -> list[dict[str, Any]]:
        """Return the interrupted AIMessage's tool calls that still lack results.

        Only the most recent AIMessage that still has unresolved tool calls is
        considered: those are the ones ToolNode aborted before recording a
        result, and they must all be resolved before the graph can resume.
        """
        if self._graph is None:
            return []
        graph_config = {"configurable": {"thread_id": context_id}}
        state = await self._graph.aget_state(graph_config)
        messages = state.values.get("messages", [])
        completed_call_ids = {
            str(message.tool_call_id or "")
            for message in messages
            if isinstance(message, ToolMessage)
        }
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            unresolved = [
                call
                for call in message.tool_calls
                if (call.get("id") or "")
                and str(call.get("id")) not in completed_call_ids
            ]
            if unresolved:
                return unresolved
        return []

    async def _inject_tool_message(
        self, context_id: str, call_id: str, content: str
    ) -> None:
        """Append a ToolMessage for a specific tool call id to the checkpoint."""
        if self._graph is None:
            return
        await self._graph.aupdate_state(
            {"configurable": {"thread_id": context_id}},
            {"messages": [ToolMessage(content=content, tool_call_id=call_id)]},
            as_node="tools",
        )

    async def _close_pending_tool_call(
        self, context_id: str, pending: PendingAction, result: str
    ) -> None:
        """Append the missing tool result left behind by an approval interrupt."""
        if self._graph is None:
            return
        graph_config = {"configurable": {"thread_id": context_id}}
        state = await self._graph.aget_state(graph_config)
        messages = state.values.get("messages", [])
        completed_call_ids = {
            str(message.tool_call_id or "")
            for message in messages
            if isinstance(message, ToolMessage)
        }
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            for call in reversed(message.tool_calls):
                call_id = str(call.get("id") or "")
                if (
                    call_id
                    and call_id not in completed_call_ids
                    and call.get("name") == pending.tool_name
                    and call.get("args", {}) == pending.arguments
                ):
                    await self._graph.aupdate_state(
                        graph_config,
                        {
                            "messages": [
                                ToolMessage(
                                    content=result,
                                    tool_call_id=call_id,
                                )
                            ]
                        },
                        as_node="tools",
                    )
                    return


def load_prompt(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
