from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


_ENV_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


class ToolPolicyConfig(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    approval_required: list[str] = Field(default_factory=list)


class AgentSkillConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class AgentRuntimeConfig(BaseModel):
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    port: int = Field(gt=0, le=65535)
    public_url: str = Field(min_length=1)
    mcp_url: str = Field(min_length=1)
    mcp_transport: Literal["sse", "streamable_http"] = "sse"
    skills: list[AgentSkillConfig] = Field(default_factory=list)
    read_only: bool = True
    risk_level: str = "read_only"
    limitations: list[str] = Field(default_factory=list)
    priority: int = 100
    tool_policy: ToolPolicyConfig = Field(default_factory=ToolPolicyConfig)
    input_modes: list[str] = Field(default_factory=lambda: ["text/plain"])
    output_modes: list[str] = Field(default_factory=lambda: ["text/plain"])


class LLMRuntimeConfig(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)


def load_llm_config(scope: str = "AGENT") -> LLMRuntimeConfig:
    prefix = f"{scope.upper()}_LLM_"
    base_url = (os.getenv(f"{prefix}BASE_URL") or os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    model = os.getenv(f"{prefix}MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"
    api_key = os.getenv(f"{prefix}API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    provider = os.getenv(f"{prefix}PROVIDER") or os.getenv("LLM_PROVIDER") or ("deepseek" if "deepseek.com" in base_url else "openai-compatible")
    return LLMRuntimeConfig(provider=provider, base_url=base_url, model=model, api_key=api_key)


def _substitute_environment(raw: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.getenv(name)
        if value is None:
            raise ValueError(f"Missing required environment variable: {name}")
        return value

    return _ENV_PATTERN.sub(replace, raw)


def load_agent_config(path: str | Path) -> AgentRuntimeConfig:
    config_path = Path(path)
    raw = config_path.read_text(encoding="utf-8")
    substituted = _substitute_environment(raw)
    data = yaml.safe_load(substituted) or {}
    data["mcp_transport"] = os.getenv(
        "MCP_TRANSPORT", data.get("mcp_transport", "sse")
    )
    return AgentRuntimeConfig.model_validate(data)
