from __future__ import annotations

import uuid
from typing import Any

from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, create_model

from .models import (
    ApprovalRequired,
    PendingAction,
    PolicyAction,
    ToolDenied,
)
from .tool_policy import ToolPolicy


_PRIMITIVE_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _schema_type(schema: dict[str, Any]) -> type:
    return _PRIMITIVE_TYPES.get(schema.get("type", "string"), Any)


def schema_to_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    required = set(schema.get("required", []))
    fields: dict[str, tuple[Any, Any]] = {}
    for property_name, property_schema in schema.get("properties", {}).items():
        python_type = _schema_type(property_schema)
        description = property_schema.get("description", "")
        if property_name in required:
            fields[property_name] = (
                python_type,
                Field(description=description),
            )
        else:
            fields[property_name] = (
                python_type | None,
                Field(default=None, description=description),
            )
    return create_model(name, **fields)


class MCPToolAdapter:
    def __init__(
        self,
        client,
        policy: ToolPolicy,
        *,
        agent_id: str,
        max_calls: int = 40,
    ):
        self.client = client
        self.policy = policy
        self.agent_id = agent_id
        self.max_calls = max_calls
        self._calls_by_context: dict[str, int] = {}

    def reset_budget(self, context_id: str) -> None:
        self._calls_by_context[context_id] = 0

    def build_tools(
        self, definitions: list[dict[str, Any]]
    ) -> list[StructuredTool]:
        tools: list[StructuredTool] = []
        for definition in definitions:
            tool_name = definition["name"]
            decision = self.policy.classify(tool_name, {})
            if decision.action is PolicyAction.DENY:
                continue
            args_schema = schema_to_model(
                f"{tool_name.title().replace('_', '')}Args",
                definition.get("input_schema") or {
                    "type": "object",
                    "properties": {},
                },
            )
            tools.append(
                StructuredTool.from_function(
                    name=tool_name,
                    description=definition.get("description") or tool_name,
                    coroutine=self._make_coroutine(tool_name),
                    args_schema=args_schema,
                )
            )
        return tools

    def _make_coroutine(self, tool_name: str):
        async def execute(config: RunnableConfig, **kwargs):
            arguments = {
                key: value for key, value in kwargs.items() if value is not None
            }
            decision = self.policy.classify(tool_name, arguments)
            if decision.action is PolicyAction.DENY:
                raise ToolDenied(tool_name, decision.reason)
            if decision.action is PolicyAction.APPROVAL_REQUIRED:
                raise ApprovalRequired(
                    PendingAction.from_call(
                        approval_id=f"ap_{uuid.uuid4().hex}",
                        agent_id=self.agent_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        reason=decision.reason,
                    )
                )
            context_id = str(
                config.get("configurable", {}).get("thread_id", "default")
            )
            used = self._calls_by_context.get(context_id, 0)
            if used >= self.max_calls:
                return (
                    f"工具调用预算已达到 {self.max_calls} 次。"
                    "不要继续调用工具，请立即基于已获得的证据总结并回答。"
                )
            self._calls_by_context[context_id] = used + 1
            return await self.client.call_tool(tool_name, arguments)

        return execute
