"""K8s Orchestrator Agent — LangGraph agent connected to a K8s MCP server via SSE."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable
from typing import Any, Optional

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
K8S_MCP_URL = os.getenv("K8S_MCP_URL", "http://10.2.0.57:9096/sse")


# -- JSON Schema -> Python type helpers --

_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_schema_to_python_type(json_type: str) -> type:
    return _JSON_TYPE_MAP.get(json_type, str)


def _make_args_schema(input_schema: dict) -> type[BaseModel]:
    """Build a Pydantic model from a JSON Schema properties dict."""
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    fields: dict[str, tuple[type, Any]] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _json_schema_to_python_type(prop_schema.get("type", "string"))
        desc = prop_schema.get("description", "")
        if prop_name in required:
            fields[prop_name] = (py_type, Field(description=desc))
        else:
            fields[prop_name] = (py_type, Field(description=desc, default=None))
    return create_model("ToolArgs", **fields)


# -- MCP Client --

class K8sMCPClient:
    """Manages the SSE connection to the K8s MCP server.

    Uses a dedicated background task to keep the SSE context manager alive
    within a single task scope, avoiding anyio cancel-scope cross-task issues.
    """

    def __init__(self, mcp_url: str = K8S_MCP_URL):
        self.mcp_url = mcp_url
        self._session: Optional[ClientSession] = None
        self._tools: list[dict] = []
        self._connected = False

        # Background task management
        self._sse_task: Optional[asyncio.Task] = None
        self._ready_event = asyncio.Event()
        self._stop_event = asyncio.Event()

    async def _sse_runner(self):
        """Background task that keeps the SSE connection alive.

        The sse_client context manager is entered and exited within this
        single task, so anyio cancel-scope tracking is consistent.
        """
        cm = sse_client(url=self.mcp_url)
        read = write = None
        try:
            read, write = await cm.__aenter__()
            try:
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready_event.set()
                    logger.info("MCP background session initialized")
                    await self._stop_event.wait()
            finally:
                try:
                    await cm.__aexit__(None, None, None)
                except RuntimeError as e:
                    if "cancel scope" in str(e):
                        logger.debug("MCP background: suppressed cancel scope RuntimeError")
                    else:
                        raise
        except asyncio.CancelledError:
            logger.info("MCP background task cancelled")
        except Exception as e:
            logger.warning("MCP background task failed: %s", e)
            self._ready_event.set()
            raise
        finally:
            self._session = None
            self._connected = False
            self._ready_event.set()

    async def connect(self):
        """Connect to the MCP server via SSE and initialize the session."""
        if self._connected:
            return

        logger.info("Connecting to MCP server at %s", self.mcp_url)
        self._ready_event.clear()
        self._stop_event.clear()

        self._sse_task = asyncio.create_task(self._sse_runner())

        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("MCP connection timed out after 30s")
            self._sse_task.cancel()
            self._sse_task = None
            raise ConnectionError(
                f"Timed out connecting to MCP server at {self.mcp_url}"
            )

        if not self._session:
            logger.warning("MCP session is None after connect()")
            self._sse_task = None
            raise ConnectionError(
                f"Failed to connect to MCP server at {self.mcp_url}"
            )

        self._connected = True
        logger.info("MCP session initialized successfully")

    async def disconnect(self):
        """Disconnect from the MCP server."""
        self._connected = False
        if self._sse_task:
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._sse_task, timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._sse_task.cancel()
                try:
                    await self._sse_task
                except (asyncio.CancelledError, Exception):
                    pass
            self._sse_task = None
        self._session = None
        logger.info("MCP session disconnected")

    async def list_tools(self) -> list[dict]:
        """List available tools from the MCP server."""
        if not self._connected or not self._session:
            await self.connect()
        tools_response = await self._session.list_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in tools_response.tools
        ]
        return self._tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool on the MCP server and return the result content."""
        if not self._connected or not self._session:
            await self.connect()
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as e:
            logger.warning("MCP call_tool failed (%s), reconnecting and retrying", e)
            self._connected = False
            self._session = None
            await self.connect()
            result = await self._session.call_tool(name, arguments)
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                parts.append(str(content.data))
            else:
                parts.append(str(content))
        return "\n".join(parts)

# -- LangGraph Agent --

class K8sOrchestratorAgent:
    """LangGraph-based K8s orchestrator agent connected to an MCP server.

    Follows the pattern from langgraph CurrencyAgent example:
      - stream() yields dicts with is_task_complete, require_user_input, content
      - MCP connection is handled gracefully with fallback
    """

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    SYSTEM_INSTRUCTION = (
        "你是一个Kubernetes容器资源编排智能体，专门通过MCP（Model Context Protocol）工具与Kubernetes集群交互。"
        "你的核心任务是根据用户提供的场景和需求，生成、分析或操作Kubernetes资源配置。\n\n"
        "请严格遵循以下步骤执行任务：\n"
        "1. **解析输入**：仔细阅读并理解用户提供的所有信息，包括场景描述、具体需求、操作类型、配置参数和现有配置。\n"
        "2. **确定操作与资源**：确定核心操作（如\"生成\"、\"分析\"、\"应用\"、\"获取\"），"
        "确定需要处理的Kubernetes资源类型（如Deployment, Service, ConfigMap等）。"
        "如果用户未明确指定，请根据场景推断最合适的资源。\n"
        "3. **规划MCP工具调用**：基于确定的操作和资源，规划需要使用的MCP工具。\n"
        "4. **执行与输出**：\n"
        "   - 你的思考过程应侧重于如何组合MCP工具调用来满足需求。\n"
        "   - 如果操作是\"生成\"配置，请输出清晰、完整、符合Kubernetes最佳实践的YAML配置，并附上简要说明。\n"
        "   - 如果操作是\"分析\"、\"获取\"或\"应用\"，请以结构化的段落、列表的形式提供清晰说明。\n"
        "   - 如果操作涉及调用MCP工具，请在输出中清晰地展示工具调用的逻辑、预期命令或对返回结果的分析。"
    )

    def __init__(self, mcp_url: str = K8S_MCP_URL):
        self.mcp_client = K8sMCPClient(mcp_url)
        self._mcp_tools: list[dict] = []
        self._graph = None
        self._tools_loaded = False

    async def ensure_connected(self):
        """Ensure the MCP client is connected and tools are loaded."""
        if not self._tools_loaded:
            try:
                self._mcp_tools = await self.mcp_client.list_tools()
                self._tools_loaded = True
                logger.info(
                    "Loaded %d MCP tools: %s",
                    len(self._mcp_tools),
                    [t["name"] for t in self._mcp_tools],
                )
            except Exception as e:
                logger.warning("Failed to load MCP tools: %s", e)
                self._mcp_tools = []
                self._tools_loaded = False

    def _create_mcp_tool(self, name: str, description: str, input_schema: dict):
        """Create a LangChain StructuredTool from an MCP tool definition."""
        mcp_client = self.mcp_client
        args_schema = _make_args_schema(input_schema) if input_schema else None

        async def _impl(**kwargs) -> str:
            return await mcp_client.call_tool(name, kwargs)

        return StructuredTool.from_function(
            name=name,
            description=description,
            coroutine=_impl,
            args_schema=args_schema,
        )

    def _make_tools(self) -> list[StructuredTool]:
        """Convert MCP tools to LangChain StructuredTools."""
        tools: list[StructuredTool] = []

        mcp_tools_ref = self._mcp_tools

        async def list_k8s_tools() -> list[dict]:
            """List all available Kubernetes MCP tools with their schemas."""
            return mcp_tools_ref

        list_k8s_tool = StructuredTool.from_function(
            name="list_k8s_tools",
            description="List all available Kubernetes MCP tools with their schemas",
            coroutine=list_k8s_tools,
        )
        tools.append(list_k8s_tool)

        for mcp_tool in self._mcp_tools:
            name = mcp_tool["name"]
            desc = mcp_tool.get("description") or f"Kubernetes tool: {name}"
            input_schema = mcp_tool.get("input_schema", {})
            tools.append(self._create_mcp_tool(name, desc, input_schema))

        return tools

    def _build_prompt(self) -> str:
        """Build the system prompt with available tool info."""
        tools_text = json.dumps(
            [
                {"name": t["name"], "description": (t.get("description") or "")[:200]}
                for t in self._mcp_tools
            ],
            indent=2,
            ensure_ascii=False,
        )

        return (
            self.SYSTEM_INSTRUCTION
            + "\n\n"
            + "可用K8s MCP工具列表：\n"
            + tools_text
            + "\n\n"
            + "使用 `list_k8s_tools` 查看每个工具的完整输入schema。\n"
            + "在调用工具前，务必先检查其输入schema。\n"
            + "始终提供清晰、结构化的回复。如果工具调用失败，向用户解释错误原因。"
        )

    def get_graph(self):
        """Get or create the LangGraph ReAct agent."""
        if self._graph is not None:
            return self._graph

        model = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_base=DEEPSEEK_BASE_URL,
            temperature=0,
            streaming=True,
        )

        memory = MemorySaver()
        self._graph = create_react_agent(
            model,
            tools=self._make_tools(),
            prompt=self._build_prompt(),
            checkpointer=memory,
        )
        return self._graph

    async def stream(
        self, query: str, context_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        """Process a message through the LangGraph agent and stream events.

        Yields dicts with keys:
          - is_task_complete: bool
          - require_user_input: bool
          - content: str
        """
        await self.ensure_connected()

        if not self._tools_loaded or not self._mcp_tools:
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": (
                    "⚠️ K8s MCP 服务器不可用，无法加载工具。\n\n"
                    f"请确保 MCP 服务器 ({K8S_MCP_URL}) 正在运行。\n"
                    "当前配置：\n"
                    f"- MCP URL: {K8S_MCP_URL}\n"
                    "- 状态：未连接\n\n"
                    "请检查网络连接和 MCP 服务器状态后重试。"
                ),
            }
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": "MCP 服务器不可用，请检查连接配置。",
            }
            return

        # Rebuild the graph with the correct prompt
        self._graph = None
        graph = self.get_graph()
        config = {"configurable": {"thread_id": context_id}}

        inputs = {"messages": [("user", query)]}
        seen_tool_ids: set[str] = set()

        async for event in graph.astream(inputs, config, stream_mode="values"):
            messages = event.get("messages", [])
            if not messages:
                continue

            last = messages[-1]

            if isinstance(last, AIMessage):
                if last.tool_calls:
                    for tc in last.tool_calls:
                        if tc["id"] not in seen_tool_ids:
                            seen_tool_ids.add(tc["id"])
                            yield {
                                "type": "tool_call",
                                "is_task_complete": False,
                                "require_user_input": False,
                                "content": f"🔧 调用工具: **{tc['name']}**\n参数: ```json\n{json.dumps(tc.get('args', {}), indent=2, ensure_ascii=False)}\n```",
                            }

            elif isinstance(last, ToolMessage):
                content_preview = last.content[:500] if last.content else ""
                if content_preview:
                    yield {
                        "type": "tool_result",
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": f"✅ 工具执行完成:\n```\n{content_preview}\n```",
                    }

        yield self._get_final_response(config)

    def _get_final_response(self, config) -> dict[str, Any]:
        """Get the final response from the graph state."""
        try:
            current_state = self._graph.get_state(config)
            messages = current_state.values.get("messages", [])
            if not messages:
                return {
                    "type": "text",
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": "处理完成，但未生成响应。",
                }

            last_message = messages[-1]
            if isinstance(last_message, AIMessage) and last_message.content:
                return {
                    "type": "text",
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": last_message.content,
                }
        except Exception as e:
            logger.warning("Failed to get final state: %s", e)

        return {
            "type": "text",
            "is_task_complete": False,
            "require_user_input": True,
            "content": "无法处理请求，请提供更多信息。",
        }


# -- Singleton --

_agent: Optional[K8sOrchestratorAgent] = None


def get_agent() -> K8sOrchestratorAgent:
    global _agent
    if _agent is None:
        _agent = K8sOrchestratorAgent()
    return _agent


async def init_agent():
    """Initialize the agent on startup (graceful on failure)."""
    agent = get_agent()
    try:
        await agent.ensure_connected()
        logger.info(
            "K8s orchestrator agent initialized with %d tools",
            len(agent._mcp_tools),
        )
    except Exception as e:
        logger.warning("MCP connection failed on startup: %s", e)
        logger.warning("Agent will run without MCP connectivity")


async def shutdown_agent():
    """Shutdown the agent and disconnect MCP."""
    global _agent
    if _agent:
        await _agent.mcp_client.disconnect()
        _agent = None
        logger.info("K8s orchestrator agent shut down")
