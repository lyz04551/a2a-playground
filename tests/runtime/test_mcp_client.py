from __future__ import annotations

import pytest

from a2a_runtime.mcp_client import K8sMCPClient


class FakeSession:
    async def list_tools(self):
        class Tool:
            name = "list_k8s_pod"
            description = "List pods"
            inputSchema = {"type": "object", "properties": {}}

        class Response:
            tools = [Tool()]

        return Response()

    async def call_tool(self, name, arguments):
        class Text:
            text = f"{name}:{arguments['namespace']}"

        class Response:
            content = [Text()]

        return Response()


@pytest.mark.anyio
async def test_client_normalizes_tool_catalog_and_text_result():
    client = K8sMCPClient(
        "http://mcp.invalid/sse",
        session_factory=lambda: FakeSession(),
    )

    tools = await client.list_tools()
    result = await client.call_tool("list_k8s_pod", {"namespace": "default"})

    assert tools == [
        {
            "name": "list_k8s_pod",
            "description": "List pods",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    assert result == "list_k8s_pod:default"
