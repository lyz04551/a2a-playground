"""Shared building blocks for independently deployable A2A agents."""

from .config import (
    AgentRuntimeConfig,
    AgentSkillConfig,
    ToolPolicyConfig,
    load_agent_config,
)
from .agent import RuntimeMCPAgent, load_prompt
from .executor import RuntimeAgentExecutor
from .models import PendingAction, PolicyAction, PolicyDecision
from .mcp_client import K8sMCPClient
from .server import build_agent_card, create_a2a_app
from .streaming import RuntimeEvent, RuntimeEventType
from .tool_adapter import MCPToolAdapter
from .tool_policy import ToolPolicy

__all__ = [
    "AgentRuntimeConfig",
    "AgentSkillConfig",
    "ToolPolicyConfig",
    "load_agent_config",
    "load_prompt",
    "PendingAction",
    "PolicyAction",
    "PolicyDecision",
    "K8sMCPClient",
    "MCPToolAdapter",
    "RuntimeAgentExecutor",
    "RuntimeMCPAgent",
    "RuntimeEvent",
    "RuntimeEventType",
    "ToolPolicy",
    "build_agent_card",
    "create_a2a_app",
]
