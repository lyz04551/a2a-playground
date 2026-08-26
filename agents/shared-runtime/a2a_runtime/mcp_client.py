from __future__ import annotations

import asyncio
import os
import httpx
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any
from typing import Literal

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client


class K8sMCPClient:
    """Reusable MCP HTTP client supporting Streamable HTTP and legacy SSE."""

    def __init__(
        self,
        mcp_url: str,
        *,
        transport: Literal["sse", "streamable_http"] = "sse",
        session_factory: Callable[[], Any] | None = None,
        connect_timeout: float = 30.0,
        sse_read_timeout: float | None = None,
        tool_timeout: float | None = None,
    ):
        self.mcp_url = mcp_url
        self.transport = transport
        self._session_factory = session_factory
        self.connect_timeout = connect_timeout
        self.sse_read_timeout = sse_read_timeout or float(
            os.getenv("MCP_SSE_READ_TIMEOUT", "3600")
        )
        self.tool_timeout = tool_timeout or float(
            os.getenv("MCP_TOOL_TIMEOUT", "30")
        )
        self._session: Any | None = None
        self._stack: AsyncExitStack | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._session is not None:
            return
        async with self._connect_lock:
            if self._session is not None:
                return
            if self._session_factory is not None:
                self._session = self._session_factory()
                return

            stack = AsyncExitStack()
            try:
                transport_client = (
                    streamablehttp_client
                    if self.transport == "streamable_http"
                    else sse_client
                )
                streams = await asyncio.wait_for(
                    stack.enter_async_context(
                        transport_client(
                            url=self.mcp_url,
                            timeout=self.connect_timeout,
                            sse_read_timeout=self.sse_read_timeout,
                        )
                    ),
                    timeout=self.connect_timeout,
                )
                read, write = streams[:2]
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(
                    session.initialize(),
                    timeout=self.connect_timeout,
                )
            except BaseException:
                await stack.aclose()
                raise
            self._stack = stack
            self._session = session

    async def disconnect(self) -> None:
        self._session = None
        if self._stack is not None:
            stack = self._stack
            self._stack = None
            await stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.connect()
        response = await self._session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        await self.connect()
        try:
            response = await asyncio.wait_for(
                self._session.call_tool(name, arguments),
                timeout=self.tool_timeout,
            )
        except TimeoutError as exc:
            await self.disconnect()
            raise TimeoutError(
                f"MCP tool '{name}' timed out after {self.tool_timeout:g}s"
            ) from exc
        except httpx.TransportError:
            await self.disconnect()
            await self.connect()
            response = await asyncio.wait_for(
                self._session.call_tool(name, arguments),
                timeout=self.tool_timeout,
            )
        parts: list[str] = []
        for content in response.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                parts.append(str(content.data))
            else:
                parts.append(str(content))
        return "\n".join(parts)
