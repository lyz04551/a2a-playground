from __future__ import annotations

import json
import re
import os
import asyncio
import time
import uuid
from datetime import datetime, timezone
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

from .evidence import build_assessment, build_evidence_ledger


_JSON_FENCE = re.compile(r"```(?P<label>coverage|json)?[ \t]*\n(?P<body>.*?)\n```", re.DOTALL | re.IGNORECASE)
_COVERAGE_KEYS = frozenset({"scope", "expected_targets", "inspected_targets", "enumeration_complete", "evidence_call_ids"})
_SENSITIVE_FIELD = re.compile(r"password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key|credential", re.I)


def _evidence_excerpt(value: str, *, limit: int = 800) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        if not value:
            return "[工具返回空输出]"
        lines = []
        for line in value.splitlines():
            key, separator, _ = line.partition(":")
            lines.append(f"{key}: [REDACTED]" if separator and _SENSITIVE_FIELD.search(key) else line)
        excerpt = "\n".join(lines)
        return excerpt[:limit] + ("…" if len(excerpt) > limit else "")

    def sanitize(item):
        if isinstance(item, dict):
            return {key: "[REDACTED]" if _SENSITIVE_FIELD.search(str(key)) else sanitize(part) for key, part in item.items()}
        if isinstance(item, list):
            return [sanitize(part) for part in item[:10]]
        return item

    excerpt = json.dumps(sanitize(parsed), ensure_ascii=False)
    return excerpt[:limit] + ("…" if len(excerpt) > limit else "")


def _tool_evidence(calls: dict[str, dict], results: dict[str, str]) -> list[dict]:
    ledger, _ = build_evidence_ledger(calls, results)
    return [
        {
            "call_id": item["call_id"],
            "tool": item["tool"],
            "resource_ids": item["resource_ids"],
            "arguments_excerpt": _evidence_excerpt(json.dumps(item["arguments"], ensure_ascii=False)),
            "called_at": item["called_at"],
            "result_state": item["result_state"],
            "result_excerpt": _evidence_excerpt(item["result"]),
        }
        for item in ledger
    ]


def _runtime_result(content: str, calls: dict[str, dict], results: dict[str, str]) -> tuple[str, list[dict], dict | None]:
    """Discard model-authored coverage; only the MCP ledger may certify it."""
    visible, _ = _extract_coverage(content, set())
    evidence = _tool_evidence(calls, results)
    _, coverage = build_evidence_ledger(calls, results)
    return visible, evidence, coverage if evidence else None


def _assessment_data(calls: dict[str, dict], results: dict[str, str]) -> dict:
    ledger, coverage = build_evidence_ledger(calls, results)
    return build_assessment(ledger, coverage)


def _extract_coverage(content: str, observed_call_ids: set[str]) -> tuple[str, dict | None]:
    """Accept a generic manifest only when its cited calls occurred this turn."""
    candidate = None
    for match in _JSON_FENCE.finditer(content):
        try:
            parsed = json.loads(match.group("body"))
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict) and _COVERAGE_KEYS <= parsed.keys():
            candidate = (match.start(), match.end(), parsed)
    if candidate is None:
        for match in re.finditer(r"(?m)^\{", content):
            try:
                parsed, end = json.JSONDecoder().raw_decode(content[match.start():])
            except ValueError:
                continue
            end += match.start()
            if isinstance(parsed, dict) and _COVERAGE_KEYS <= parsed.keys() and not content[end:].strip():
                candidate = (match.start(), end, parsed)
    if candidate is None:
        return content, None
    start, end, manifest = candidate
    visible = (content[:start] + content[end:]).strip()
    try:
        expected = manifest["expected_targets"]
        inspected = manifest["inspected_targets"]
        citations = manifest["evidence_call_ids"]
        valid = (
            isinstance(manifest.get("scope"), str)
            and isinstance(expected, list) and all(isinstance(item, str) for item in expected)
            and isinstance(inspected, list) and all(isinstance(item, str) for item in inspected)
            and isinstance(citations, list) and bool(citations)
            and set(citations) <= observed_call_ids
            and set(inspected) <= set(expected)
            and isinstance(manifest.get("enumeration_complete"), bool)
        )
        return (visible, manifest) if valid else (visible, None)
    except (KeyError, TypeError, ValueError):
        return visible, None


def _stream_visible_content(content: str) -> str:
    """Keep an unfinished structured block out of the user-facing stream."""
    if content.lstrip().startswith("{"):
        summary = re.search(r'"summary"\s*:\s*"', content)
        if summary is None:
            return ""
        raw = content[summary.end():]
        visible = []
        position = 0
        while position < len(raw):
            if raw[position] == '"':
                break
            if raw[position] == "\\":
                width = 6 if raw[position:position + 2] == "\\u" else 2
                token = raw[position:position + width]
                if len(token) < width:
                    break
                try:
                    visible.append(json.loads('"' + token + '"'))
                except (TypeError, ValueError):
                    break
                position += width
                continue
            visible.append(raw[position])
            position += 1
        summary_text = "".join(visible)
        return summary_text[:-8] if len(summary_text) > 8 else ""
    fence = re.search(r"(?m)^```(?:coverage|json)?[^\n]*", content, re.IGNORECASE)
    if fence is not None and "\n```" not in content[fence.end():]:
        content = content[:fence.start()]
    else:
        content, _ = _extract_coverage(content, set())
    bare_object = re.search(r"(?m)^\{", content)
    if bare_object is not None:
        content = content[:bare_object.start()]
    return content[:-8] if len(content) > 8 else ""


def _final_stream_delta(content: str, emitted_content: str) -> tuple[bool, str]:
    """Append the final tail when the visible draft is a prefix of the result."""
    if content.startswith(emitted_content):
        return False, content[len(emitted_content):]
    return True, content


def _display_content(content: str) -> str:
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return content
    if isinstance(parsed, dict) and isinstance(parsed.get("status"), str) and isinstance(parsed.get("summary"), str):
        return parsed["summary"]
    return content


def _empty_structured_result(content: str) -> bool:
    if not content.strip():
        return True
    try:
        result = json.loads(content)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(result, dict)
        and isinstance(result.get("status"), str)
        and isinstance(result.get("summary"), str)
        and not result["summary"].strip()
    )


def _truncated_report(message: AIMessage | None, content: str, token_limit: int | None = None) -> bool:
    if not content.strip():
        return False
    metadata = getattr(message, "response_metadata", {}) or {}
    finish_reason = str(metadata.get("finish_reason") or metadata.get("stop_reason") or "").lower()
    if finish_reason in {"length", "max_tokens", "max_output_tokens"}:
        return True
    usage = getattr(message, "usage_metadata", {}) or {}
    token_usage = metadata.get("token_usage") or {}
    output_tokens = usage.get("output_tokens") or token_usage.get("completion_tokens") or 0
    return bool(token_limit and output_tokens >= token_limit)

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI  #调用 OpenAI 兼容模型
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import ToolNode, create_react_agent

from .config import AgentRuntimeConfig, load_llm_config
from .checkpoint import PostgresCheckpointManager
from .mcp_client import K8sMCPClient
from .models import ApprovalRequired, PendingAction, PolicyAction
from .streaming import RuntimeEvent, RuntimeEventType
from .tool_adapter import MCPToolAdapter
from .tool_policy import ToolPolicy
from .reasoning_model import ReasoningChatOpenAI


def _handle_tool_error(exc: Exception) -> str:
    if isinstance(exc, ApprovalRequired):
        raise exc
    return f"工具执行失败：{exc}"


def _limit_tool_batch(message: AIMessage, limit: int) -> AIMessage:
    if not isinstance(message, AIMessage) or len(message.tool_calls) <= limit:
        return message
    return message.model_copy(update={"tool_calls": message.tool_calls[:limit]})


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
            "证据，且不得擅自扩大用户指定的对象范围。报告应完整呈现已有证据、"
            "结论和未检查项；不得因固定字数目标省略必要内容。"
        )
        self.mcp_client = mcp_client or K8sMCPClient(
            config.mcp_url, transport=config.mcp_transport
        )
        self._model = model
        self._batch_results_by_context: dict[str, dict[str, str]] = {}
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
        self.max_output_tokens = int(
            os.getenv("AGENT_MAX_OUTPUT_TOKENS", "8192")
        )
        self.summary_max_tokens = int(
            os.getenv("AGENT_SUMMARY_MAX_TOKENS", "4096")
        )
        self.enable_thinking = os.getenv(
            "AGENT_ENABLE_THINKING", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
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
        model = self._model or ReasoningChatOpenAI(
            model=llm.model,
            openai_api_key=llm.api_key,
            openai_api_base=llm.base_url,
            temperature=0,
            streaming=True,
            max_tokens=self.max_output_tokens,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": self.enable_thinking,
                }
            },
        )
        self._model = model
        # The model may propose a large batch even when the remaining tool
        # budget is small. Keep parallel execution, but cap what reaches ToolNode.
        tool_bound_model = model.bind_tools(tools)
        max_parallel_calls = min(
            self.max_tool_calls,
            max(1, int(os.getenv("AGENT_MAX_PARALLEL_TOOL_CALLS", "4"))),
        )

        def model_for_session(_state, runtime):
            session_id = (runtime.context or {}).get("session_id")
            active_model = tool_bound_model if not session_id else tool_bound_model.bind(
                extra_body={
                    "chat_template_kwargs": {
                        "enable_thinking": self.enable_thinking,
                    },
                    "metadata": {"session_id": session_id},
                }
            )
            remaining = max(1, self.max_tool_calls - self._tool_adapter._calls_by_context.get(session_id, 0))
            return active_model | RunnableLambda(
                lambda message: _limit_tool_batch(message, min(max_parallel_calls, remaining))
            )

        self._graph = create_react_agent(
            model_for_session,
            tools=ToolNode(tools, handle_tool_errors=_handle_tool_error),
            prompt=self.prompt,
            checkpointer=self._checkpointer,
            context_schema=dict,
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

    async def probe_connections(
        self, timeout: float = 15.0, target: str = "all"
    ) -> dict[str, Any]:
        if target not in {"all", "model", "mcp"}:
            raise ValueError("target must be all, model, or mcp")
        async def probe_model() -> dict[str, Any]:
            started = time.monotonic()
            try:
                llm = load_llm_config("AGENT")
                if self._model is None and not llm.configured:
                    raise RuntimeError("Agent model is not configured")
                model = self._model or ChatOpenAI(
                    model=llm.model,
                    openai_api_key=llm.api_key,
                    openai_api_base=llm.base_url,
                    temperature=0,
                    streaming=False,
                    request_timeout=timeout,
                    max_retries=0,
                )
                diagnostic_model = model.bind(
                    max_tokens=8,
                    extra_body={
                        "chat_template_kwargs": {"enable_thinking": False}
                    },
                )
                async with asyncio.timeout(timeout):
                    response = await diagnostic_model.ainvoke([
                        HumanMessage(content="Reply with exactly OK.")
                    ])
                if not str(getattr(response, "content", "") or "").strip():
                    raise RuntimeError("Agent model returned an empty response")
                return {
                    "state": "ok",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "model": llm.model,
                }
            except Exception as exc:
                return {
                    "state": "error",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "error": str(exc)[:200],
                }

        async def probe_mcp() -> dict[str, Any]:
            started = time.monotonic()
            try:
                async with asyncio.timeout(timeout):
                    tools = await self.mcp_client.list_tools()
                policy = ToolPolicy(self.config.tool_policy)
                catalog = sorted((
                    {
                        "name": str(tool.get("name") or ""),
                        "description": str(tool.get("description") or ""),
                        "access": policy.classify(str(tool.get("name") or "")).action.value,
                    }
                    for tool in tools
                    if tool.get("name")
                ), key=lambda item: item["name"])
                return {
                    "state": "ok",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "tool_count": len(catalog),
                    "callable_count": sum(item["access"] != "deny" for item in catalog),
                    "tools": catalog,
                }
            except Exception as exc:
                return {
                    "state": "error",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "error": str(exc)[:200],
                }

        result = {"agent_id": self.config.agent_id}
        if target == "model":
            result["model"] = await probe_model()
        elif target == "mcp":
            result["mcp"] = await probe_mcp()
        else:
            result["model"], result["mcp"] = await asyncio.gather(
                probe_model(), probe_mcp()
            )
        return result

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
            # A ReAct tool turn consumes an agent step and a tool step. Keep
            # the graph recursion budget consistent with the configured tool
            # budget so the framework does not terminate before ToolPolicy.
            "recursion_limit": max(
                self.max_steps, self.max_tool_calls * 2 + 2
            ),
        }
        if self._tool_adapter is not None:
            self._tool_adapter.reset_budget(context_id)
        seen_tool_calls: set[str] = set()
        seen_tool_results: set[str] = set()
        current_tool_names: dict[str, str] = {}
        current_tool_calls: dict[str, dict] = {}
        current_tool_results: dict[str, str] = {}
        streamed_content = ""
        emitted_content = ""
        thinking_pending = ""
        thinking_last_emit = time.monotonic()
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
                async for item in self._graph.astream(
                    {"messages": [("user", query)]},
                    graph_config,
                    stream_mode=["values", "messages"],
                    context={"session_id": context_id},
                ):
                    mode, state = item if isinstance(item, tuple) and len(item) == 2 else ("values", item)
                    if mode == "messages":
                        chunk, metadata = state
                        if (
                            self.enable_thinking
                            and metadata.get("langgraph_node") == "agent"
                            and isinstance(chunk, AIMessageChunk)
                        ):
                            reasoning = chunk.additional_kwargs.get("reasoning_content")
                            if isinstance(reasoning, str) and reasoning:
                                thinking_pending += reasoning
                                if len(thinking_pending) >= 80 or time.monotonic() - thinking_last_emit >= 0.3:
                                    yield RuntimeEvent(type=RuntimeEventType.THINKING, content=thinking_pending)
                                    thinking_pending = ""
                                    thinking_last_emit = time.monotonic()
                        if (
                            metadata.get("langgraph_node") == "agent"
                            and isinstance(chunk, AIMessageChunk)
                            and isinstance(chunk.content, str)
                            and chunk.content
                            and not chunk.tool_call_chunks
                        ):
                            streamed_content += chunk.content
                            visible = _stream_visible_content(streamed_content)
                            if visible.startswith(emitted_content):
                                delta = visible[len(emitted_content):]
                                if delta:
                                    yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
                                    emitted_content = visible
                        continue
                    if thinking_pending:
                        yield RuntimeEvent(type=RuntimeEventType.THINKING, content=thinking_pending)
                        thinking_pending = ""
                    messages = state.get("messages", [])
                    if not messages:
                        continue
                    for message in messages:
                        if isinstance(message, AIMessage) and message.tool_calls:
                            for call in message.tool_calls:
                                if call["id"] in seen_tool_calls:
                                    continue
                                if streamed_content:
                                    if emitted_content:
                                        yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Tool call superseded draft")
                                    streamed_content = ""
                                    emitted_content = ""
                                seen_tool_calls.add(call["id"])
                                current_tool_names[call["id"]] = call["name"]
                                current_tool_calls[call["id"]] = {
                                    "tool": call["name"],
                                    "arguments": call.get("args", {}),
                                    "called_at": datetime.now(timezone.utc).isoformat(),
                                }
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
                            current_tool_results[call_id] = str(message.content)
                            yield RuntimeEvent(
                                type=RuntimeEventType.TOOL_RESULT,
                                content=str(message.content),
                                data={
                                    "tool_call_id": call_id,
                                    "result": str(message.content),
                                    "skipped": str(message.content).startswith("工具调用预算已达到"),
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
            evidence = self._current_run_evidence(current_tool_results, current_tool_calls)
            if emitted_content:
                yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Switch to partial summary")
            summary_emitted = ""
            try:
                content = ""
                async for chunk in self._force_summary_chunks(query, evidence):
                    content += chunk
                    visible = _stream_visible_content(content)
                    if visible.startswith(summary_emitted):
                        delta = visible[len(summary_emitted):]
                        if delta:
                            yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
                            summary_emitted = visible
                content = content.strip()
            except TimeoutError:
                if summary_emitted:
                    yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Summary timed out")
                summary_emitted = ""
                content = await self._deterministic_partial_summary(
                    current_tool_results,
                    "强制总结模型也达到时间限制",
                    current_tool_names,
                    current_tool_calls,
                )
            except Exception as exc:
                if summary_emitted:
                    yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Summary failed")
                summary_emitted = ""
                content = await self._deterministic_partial_summary(
                    current_tool_results,
                    f"强制总结模型不可用：{exc}",
                    current_tool_names,
                    current_tool_calls,
                )
            content, evidence_items, coverage = _runtime_result(content, current_tool_calls, current_tool_results)
            reset, delta = _final_stream_delta(_display_content(content), summary_emitted)
            if reset:
                yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Finalize partial summary")
            if delta:
                yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
            yield RuntimeEvent.completed(
                content=content,
                artifact_name="specialist_result",
                data={
                    "status": "partial",
                    "summary": content,
                    "findings": [],
                    "resources": [],
                    "evidence": evidence_items,
                    "assessment": _assessment_data(current_tool_calls, current_tool_results),
                    "recommendations": [],
                    "continuation": {
                        "allowed": True,
                        "reason": cutoff_reason,
                    },
                    "limitations": [
                        "调查阶段达到时间预算，以上结论仅基于已完成的检查。"
                    ],
                    **({"coverage": coverage} if coverage else {}),
                },
            )
            return

        state = await self._graph.aget_state(graph_config)
        messages = state.values.get("messages", [])
        content = ""
        final_message = messages[-1] if messages and isinstance(messages[-1], AIMessage) else None
        if final_message is not None:
            content = str(final_message.content or "")
        if (
            self._tool_adapter is not None
            and self._tool_adapter._calls_by_context.get(context_id, 0) >= self.max_tool_calls
        ):
            yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Discard incomplete draft")
            evidence = self._current_run_evidence(current_tool_results, current_tool_calls)
            summary_emitted = ""
            try:
                content = ""
                async for chunk in self._force_summary_chunks(query, evidence):
                    content += chunk
                    visible = _stream_visible_content(content)
                    if visible.startswith(summary_emitted):
                        delta = visible[len(summary_emitted):]
                        if delta:
                            yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
                            summary_emitted = visible
                content = content.strip()
            except Exception:
                if summary_emitted:
                    yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Summary failed")
                summary_emitted = ""
                content = await self._deterministic_partial_summary(
                    current_tool_results, "工具调用预算已用尽", current_tool_names,
                    current_tool_calls,
                )
            content, evidence_items, coverage = _runtime_result(content, current_tool_calls, current_tool_results)
            reset, delta = _final_stream_delta(_display_content(content), summary_emitted)
            if reset:
                yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Finalize partial summary")
            if delta:
                yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
            yield RuntimeEvent.completed(
                content=content,
                artifact_name="specialist_result",
                data={
                    "status": "partial", "summary": content,
                    "evidence": evidence_items,
                    "assessment": _assessment_data(current_tool_calls, current_tool_results),
                    "continuation": {"allowed": True, "reason": "tool call budget reached"},
                    "limitations": ["工具调用预算已用尽，未覆盖的检查不作结论。"],
                    **({"coverage": coverage} if coverage else {}),
                },
            )
            return
        if "Sorry, need more steps to process this request." in content:
            content = await self._deterministic_partial_summary(
                current_tool_results,
                "调查步骤预算已用尽",
                current_tool_names,
                current_tool_calls,
            )
            yield RuntimeEvent.completed(
                content=content,
                artifact_name="specialist_result",
                data={
                    "status": "partial",
                    "summary": content,
                    "findings": [],
                    "resources": [],
                    "evidence": _tool_evidence(current_tool_calls, current_tool_results),
                    "assessment": _assessment_data(current_tool_calls, current_tool_results),
                    **({"coverage": build_evidence_ledger(current_tool_calls, current_tool_results)[1]} if current_tool_results else {}),
                    "recommendations": [],
                    "continuation": {
                        "allowed": True,
                        "reason": "investigation step budget reached",
                    },
                    "limitations": [
                        "调查步骤预算已用尽，结论仅基于已完成的工具结果。"
                    ],
                },
            )
            return
        failed_tool_results = [
            result
            for result in current_tool_results.values()
            if result.lstrip().startswith("工具执行失败：")
        ]
        if failed_tool_results:
            failure = failed_tool_results[-1]
            summary = content.strip() or failure
            yield RuntimeEvent.completed(
                content=summary,
                artifact_name="specialist_result",
                data={
                    "status": "partial",
                    "summary": summary,
                    "findings": [],
                    "resources": [],
                    "evidence": _tool_evidence(current_tool_calls, current_tool_results),
                    "assessment": _assessment_data(current_tool_calls, current_tool_results),
                    **({"coverage": build_evidence_ledger(current_tool_calls, current_tool_results)[1]} if current_tool_results else {}),
                    "recommendations": [],
                    "continuation": {
                        "allowed": False,
                        "reason": failure,
                    },
                    "limitations": [
                        "工具调用失败，本任务未完成；不得将其视为成功变更。"
                    ],
                },
            )
            return
        if _empty_structured_result(content) or _truncated_report(final_message, content, self.max_output_tokens):
            incomplete_reason = "Agent 最终文本为空" if _empty_structured_result(content) else "Agent 报告生成中断"
            if emitted_content:
                yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Replace incomplete draft")
            evidence = self._current_run_evidence(current_tool_results, current_tool_calls)
            summary_emitted = ""
            try:
                summary = ""
                async for chunk in self._force_summary_chunks(query, evidence, reason=incomplete_reason):
                    summary += chunk
                    visible = _stream_visible_content(summary)
                    if visible.startswith(summary_emitted):
                        delta = visible[len(summary_emitted):]
                        if delta:
                            yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
                            summary_emitted = visible
                summary = summary.strip()
            except Exception:
                if summary_emitted:
                    yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Evidence summary failed")
                summary_emitted = ""
                summary = await self._deterministic_partial_summary(
                    current_tool_results, incomplete_reason, current_tool_names,
                    current_tool_calls, headline="本轮检查尚未形成完整结论",
                )
            summary, evidence_items, coverage = _runtime_result(summary, current_tool_calls, current_tool_results)
            reset, delta = _final_stream_delta(_display_content(summary), summary_emitted)
            if reset:
                yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Finalize evidence summary")
            if delta:
                yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
            yield RuntimeEvent.completed(
                content=summary,
                artifact_name="specialist_result",
                data={
                    "status": "partial",
                    "summary": summary,
                    "evidence": evidence_items,
                    "assessment": _assessment_data(current_tool_calls, current_tool_results),
                    **({"coverage": coverage} if coverage else {}),
                    "continuation": {"allowed": True, "reason": incomplete_reason},
                    "limitations": ["本轮结论仅基于已完成的工具检查；未验证项需要续查。"],
                },
            )
            return
        content, evidence_items, coverage = _runtime_result(content, current_tool_calls, current_tool_results)
        display_content = _display_content(content)
        reset, delta = _final_stream_delta(display_content, emitted_content)
        if reset:
            yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET, content="Finalize specialist response")
        if delta:
            yield RuntimeEvent(type=RuntimeEventType.TEXT, content=delta)
        yield RuntimeEvent.completed(
            content=content or "处理完成，但未生成文本响应。",
            artifact_name="specialist_result",
            data={
                "status": "completed",
                "summary": content,
                "findings": [],
                "resources": [],
                "evidence": evidence_items,
                "assessment": _assessment_data(current_tool_calls, current_tool_results),
                "recommendations": [],
                "continuation": {"allowed": None, "reason": ""},
                "limitations": [],
                **({"coverage": coverage} if coverage else {}),
            },
        )

    async def _force_summary(self, query: str, evidence: str) -> str:
        chunks = []
        async for chunk in self._force_summary_chunks(query, evidence):
            chunks.append(chunk)
        content = "".join(chunks).strip()
        if not content:
            raise RuntimeError("Agent model returned an empty forced summary")
        return content

    async def _force_summary_chunks(self, query: str, evidence: str, *, reason: str = "调查阶段的时间预算已经用完") -> AsyncIterable[str]:
        if self._model is None:
            raise RuntimeError("Agent model is unavailable for forced summary")
        prompt = (
            f"{reason}。禁止调用任何工具。请仅根据下面已经取得的"
            "证据形成本轮正式的部分检查报告：先概括已枚举的资源及数量，再说明已验证"
            "的状态、尚未逐项检查的内容和下一轮需要补查的对象。不要声称执行了证据中"
            "没有出现的检查。区分已观察事实、推断和未知项。"
            "证据关联由运行时自动完成，不要生成 coverage JSON 或调用 ID。\n\n"
            f"用户问题：{query}\n\n已取得证据：\n{evidence}"
        )
        async with asyncio.timeout(self.summary_reserve_seconds):
            summary_model = self._model.bind(
                max_tokens=self.summary_max_tokens,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False}
                },
            )
            received = False
            async for response in summary_model.astream([HumanMessage(content=prompt)]):
                content = getattr(response, "content", "")
                if isinstance(content, str) and content:
                    received = True
                    yield content
            if not received:
                raise RuntimeError("Agent model returned an empty forced summary")

    async def _deterministic_partial_summary(
        self,
        results: dict[str, str],
        reason: str,
        tool_names: dict[str, str] | None = None,
        tool_calls: dict[str, dict] | None = None,
        *,
        headline: str = "本次检查已达到执行预算",
    ) -> str:
        tool_names = tool_names or {}
        tool_calls = tool_calls or {}
        evidence_notes: list[str] = []
        for call_id, content in results.items():
            call = tool_calls.get(call_id) or {}
            tool = str(tool_names.get(call_id) or call.get("tool") or "").lower()
            arguments = call.get("arguments") or {}
            try:
                payload = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                payload = None
            target = json.dumps(arguments, ensure_ascii=False, sort_keys=True) if arguments else "{}"
            if isinstance(payload, list):
                detail = f"返回 {len(payload)} 项"
                names = [str(item["name"]) for item in payload if isinstance(item, dict) and item.get("name")]
                if names:
                    detail += f"：{', '.join(names)}"
            elif isinstance(payload, dict):
                detail = "返回对象"
            elif content.strip():
                detail = "返回文本"
            else:
                detail = "返回空内容"
            evidence_notes.append(f"{tool or '工具'} {target}：{detail}（调用 {call_id}）")
        if not evidence_notes:
            evidence_notes.append("没有已完成的工具结果。")
        unknowns: list[str] = []
        if tool_calls:
            _, coverage = build_evidence_ledger(tool_calls, results)
            missing = [target for target in coverage["expected_targets"] if target not in coverage["inspected_targets"]]
            if missing:
                unknowns.append(f"已枚举但尚未逐项读取的资源：{', '.join(missing)}")
        if not unknowns:
            unknowns.append("未完成的任务要求仍需续查；本报告不推断未读取对象的状态或根因。")
        return (
            f"## {self.config.name} 本轮部分检查报告\n\n"
            f"{headline}。工具检查已停止，以下只陈述已返回的证据。\n\n"
            "### 已返回的工具结果\n- " + "\n- ".join(evidence_notes) + "\n\n"
            "### 未完成与未知\n- " + "\n- ".join(unknowns) + "\n\n"
            f"限制：{reason}。建议仅补查上述缺口；未执行任何写操作。"
        )

    @staticmethod
    def _current_run_evidence(results: dict[str, str], calls: dict[str, dict] | None = None) -> str:
        chunks: list[str] = []
        calls = calls or {}
        remaining = 12_000
        per_call = min(2_000, max(250, remaining // max(1, len(results)) - 100))
        for call_id, content in results.items():
            excerpt = content[: min(per_call, remaining)] if content else "[工具返回空输出]"
            call = calls.get(call_id) or {}
            tool = str(call.get("tool") or "")
            arguments = call.get("arguments") or {}
            target = f"，工具 {tool}，参数 {_evidence_excerpt(json.dumps(arguments, ensure_ascii=False), limit=300)}" if tool else ""
            chunks.append(
                f"- 工具调用 {call_id or 'unknown'}{target} 的结果：{excerpt}"
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
        batch_results = self._batch_results_by_context.setdefault(context_id, {})
        calls, completed_call_ids = await self._pending_batch_calls(context_id)
        current_call = next((
            call for call in calls
            if call.get("name") == pending.tool_name
            and call.get("args", {}) == pending.arguments
            and str(call.get("id") or "") not in completed_call_ids
            and str(call.get("id") or "") not in batch_results
        ), None)
        if current_call is not None:
            batch_results[str(current_call["id"])] = str(result)
        parts = list(batch_results.values())
        evidence = [
            {
                "tool": pending.tool_name,
                "arguments": pending.arguments,
                "result": result,
            }
        ]
        while True:
            unresolved = [
                call for call in calls
                if str(call.get("id") or "") not in completed_call_ids
                and str(call.get("id") or "") not in batch_results
            ]
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
            batch_results[call_id] = str(sibling_result)
            parts.append(str(sibling_result))
            evidence.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "result": sibling_result,
                }
            )
        await self._inject_tool_messages(context_id, [
            ToolMessage(content=value, tool_call_id=call_id)
            for call_id, value in batch_results.items()
        ])
        self._batch_results_by_context.pop(context_id, None)
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

    async def _pending_batch_calls(
        self, context_id: str
    ) -> tuple[list[dict[str, Any]], set[str]]:
        if self._graph is None:
            return [], set()
        state = await self._graph.aget_state(
            {"configurable": {"thread_id": context_id}}
        )
        messages = state.values.get("messages", [])
        completed = {
            str(message.tool_call_id or "")
            for message in messages
            if isinstance(message, ToolMessage)
        }
        for message in reversed(messages):
            if isinstance(message, AIMessage) and message.tool_calls:
                return list(message.tool_calls), completed
        return [], completed

    async def _inject_tool_messages(
        self, context_id: str, messages: list[ToolMessage]
    ) -> None:
        if self._graph is None or not messages:
            return
        await self._graph.aupdate_state(
            {"configurable": {"thread_id": context_id}},
            {"messages": messages},
            as_node="tools",
        )

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
