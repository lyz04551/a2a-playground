from __future__ import annotations

import pytest
from pydantic import ValidationError

from a2a_runtime.config import AgentRuntimeConfig, load_agent_config, load_llm_config


def test_agent_llm_uses_its_own_configuration(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "vllm")
    monkeypatch.setenv("AGENT_LLM_BASE_URL", "http://agent-model:4000/v1/")
    monkeypatch.setenv("AGENT_LLM_MODEL", "agent-model")
    monkeypatch.setenv("AGENT_LLM_API_KEY", "agent-secret")
    monkeypatch.setenv("HOST_LLM_MODEL", "host-model")

    config = load_llm_config("AGENT")

    assert config.provider == "vllm"
    assert config.base_url == "http://agent-model:4000/v1"
    assert config.model == "agent-model"
    assert config.api_key == "agent-secret"
    assert "host-model" not in str(config)


def test_load_agent_config_substitutes_environment_and_preserves_capabilities(
    tmp_path, monkeypatch
):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent_id: k8s-ops
name: K8s Ops Agent
description: Read-only Kubernetes diagnostics
port: 8052
public_url: ${AGENT_PUBLIC_URL}
mcp_url: ${K8S_MCP_URL}
skills:
  - id: pod.diagnose
    name: Pod Diagnosis
    description: Diagnose unhealthy pods
tool_policy:
  allow:
    - list_k8s_*
    - get_k8s_*
  deny:
    - get_k8s_pod_linked_env
  approval_required: []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_PUBLIC_URL", "http://k8s-ops:8052")
    monkeypatch.setenv("K8S_MCP_URL", "http://mcp:9096/sse")

    config = load_agent_config(config_file)

    assert config.agent_id == "k8s-ops"
    assert config.public_url == "http://k8s-ops:8052"
    assert config.mcp_url == "http://mcp:9096/sse"
    assert config.skills[0].id == "pod.diagnose"
    assert config.tool_policy.allow == ["list_k8s_*", "get_k8s_*"]
    assert config.tool_policy.deny == ["get_k8s_pod_linked_env"]


def test_agent_config_defaults_to_legacy_sse_transport():
    config = AgentRuntimeConfig(
        agent_id="ops",
        name="Ops",
        port=8052,
        public_url="http://ops",
        mcp_url="http://mcp:9096/sse",
    )

    assert config.mcp_transport == "sse"


@pytest.mark.parametrize("transport", ["sse", "streamable_http"])
def test_load_agent_config_accepts_supported_mcp_transport(
    tmp_path, monkeypatch, transport
):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent_id: k8s-ops
name: K8s Ops Agent
port: 8052
public_url: http://ops:8052
mcp_url: http://mcp:9096/mcp
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_TRANSPORT", transport)

    config = load_agent_config(config_file)

    assert config.mcp_transport == transport


def test_load_agent_config_rejects_unsupported_mcp_transport(tmp_path, monkeypatch):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent_id: k8s-ops
name: K8s Ops Agent
port: 8052
public_url: http://ops:8052
mcp_url: http://mcp:9096/mcp
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_TRANSPORT", "auto")

    with pytest.raises(ValidationError, match="mcp_transport"):
        load_agent_config(config_file)


def test_agent_config_rejects_empty_stable_id():
    with pytest.raises(ValidationError):
        AgentRuntimeConfig(
            agent_id="",
            name="Invalid Agent",
            description="",
            port=8051,
            public_url="http://agent:8051",
            mcp_url="http://mcp:9096/sse",
            skills=[],
            tool_policy={},
        )


def test_load_agent_config_fails_when_environment_variable_is_missing(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent_id: k8s-ops
name: K8s Ops Agent
description: Diagnostics
port: 8052
public_url: ${MISSING_PUBLIC_URL}
mcp_url: http://mcp:9096/sse
skills: []
tool_policy: {}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="MISSING_PUBLIC_URL"):
        load_agent_config(config_file)
