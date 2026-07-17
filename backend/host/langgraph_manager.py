"""LangGraph Host Manager — bridges the LangGraph host agent with the playground backend."""

import json
import logging
import uuid
from typing import AsyncIterable, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from host.langgraph_agent import LangGraphHostAgent, RemoteAgentConnections
from a2a.types import AgentCard

logger = logging.getLogger(__name__)


class LangGraphHostManager:
    """Manages the LangGraph HostAgent lifecycle and bridges to the playground backend."""

    def __init__(self):
        self._host_agent = LangGraphHostAgent()

    def register_agents_from_db(self, agents: list[dict]):
        for a in agents:
            try:
                card = AgentCard(
                    name=a.get("name", "Unknown"),
                    description=a.get("description", ""),
                    url=a.get("url", ""),
                    version=a.get("version", "1.0"),
                    default_input_modes=a.get("inputModes", ["text"]),
                    default_output_modes=a.get("outputModes", ["text"]),
                    capabilities={"streaming": True} if a.get("capabilities", {}).get("streaming") else {},
                    skills=a.get("skills", []),
                    preferred_transport=a.get("preferredTransport", "JSONRPC"),
                )
                self._host_agent.register_agent_card(card)
            except Exception as e:
                logger.warning(f"Failed to register agent {a.get('name')}: {e}")

    async def process_message_stream(self, text: str, session_id: str) -> AsyncIterable[dict]:
        """Process a user message and stream LangGraph events to the frontend.

        Yields dicts:
          - {"type": "tool_call", "tool": "...", "args": ..., "id": "..."}
          - {"type": "tool_result", "tool": "...", "result": ..., "id": "..."}
          - {"type": "routing", "agent": "..."}
          - {"type": "text", "text": "..."}
          - {"type": "done", "session_id": "..."}
        """
        graph = self._host_agent.get_graph()
        config = {"configurable": {"thread_id": session_id}}

        # Track seen IDs to avoid duplicates from stream_mode="values"
        seen_tool_call_ids = set()
        seen_tool_result_ids = set()
        tool_call_names = {}
        # Track which agent a send_task was routed to
        tool_call_agent_map = {}
        # Track text already emitted to avoid re-emitting from ToolMessage content
        # that the LLM then repeats in its final AIMessage
        emitted_text_hashes = set()

        async for event in graph.astream(
            {"messages": [HumanMessage(content=text)]},
            config,
            stream_mode="values",
        ):
            messages = event.get("messages", [])
            if not messages:
                continue

            last = messages[-1]

            if isinstance(last, AIMessage):
                if last.tool_calls:
                    for tc in last.tool_calls:
                        if tc["id"] in seen_tool_call_ids:
                            continue
                        seen_tool_call_ids.add(tc["id"])
                        tool_call_names[tc["id"]] = tc["name"]
                        # Track which agent send_task is targeting
                        if tc["name"] == "send_task" and tc.get("args"):
                            agent_name = tc["args"].get("agent_name", "")
                            if agent_name:
                                tool_call_agent_map[tc["id"]] = agent_name
                        yield {"type": "tool_call", "tool": tc["name"], "args": tc.get("args", {}), "id": tc["id"]}
                elif last.content:
                    # Only emit text that hasn't been emitted before
                    text_hash = hash(last.content)
                    if text_hash not in emitted_text_hashes:
                        emitted_text_hashes.add(text_hash)
                        yield {"type": "text", "text": last.content}

            elif isinstance(last, ToolMessage):
                if last.tool_call_id in seen_tool_result_ids:
                    continue
                seen_tool_result_ids.add(last.tool_call_id)
                tool_name = tool_call_names.get(last.tool_call_id, "unknown")
                result = last.content
                # If this was a send_task, emit routing info for the sub-agent
                if tool_name == "send_task" and last.tool_call_id in tool_call_agent_map:
                    agent_name = tool_call_agent_map[last.tool_call_id]
                    yield {"type": "routing", "agent": agent_name}
                yield {"type": "tool_result", "tool": tool_name, "result": result, "id": last.tool_call_id}

        yield {"type": "done", "session_id": session_id}


_manager: Optional[LangGraphHostManager] = None


def get_manager() -> LangGraphHostManager:
    global _manager
    if _manager is None:
        _manager = LangGraphHostManager()
    return _manager
