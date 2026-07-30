from __future__ import annotations

import pytest
from pydantic import ValidationError

from a2a_runtime.config import AgentRuntimeConfig, load_agent_config


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
