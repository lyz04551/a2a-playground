from __future__ import annotations

from pathlib import Path

from a2a_runtime.config import load_agent_config
from a2a_runtime.models import PolicyAction
from a2a_runtime.tool_policy import ToolPolicy


ROOT = Path(__file__).resolve().parents[2]


def load_configs(monkeypatch):
    monkeypatch.setenv("K8S_MCP_URL", "http://mcp:9096/sse")
    configs = []
    for directory, port in (
        ("k8s-ops", 8052),
        ("k8s-orchestrator", 8051),
        ("k8s-security", 8053),
    ):
        monkeypatch.setenv(
            "AGENT_PUBLIC_URL", f"http://{directory}:{port}"
        )
        configs.append(
            load_agent_config(ROOT / "agents" / directory / "agent.yaml")
        )
    return configs


def test_agent_configs_have_unique_stable_ids_and_urls(monkeypatch):
    configs = load_configs(monkeypatch)

    assert {config.agent_id for config in configs} == {
        "k8s-ops",
        "k8s-orchestrator",
        "k8s-security",
    }
    assert len({config.public_url for config in configs}) == 3


def test_ops_and_security_cannot_mutate_cluster(monkeypatch):
    ops, _, security = load_configs(monkeypatch)

    for config in (ops, security):
        policy = ToolPolicy(config.tool_policy)
        assert (
            policy.classify("get_k8s_resource", {}).action
            is PolicyAction.ALLOW
        )
        assert (
            policy.classify("patch_k8s_resource", {}).action
            is PolicyAction.DENY
        )
        assert (
            policy.classify("apply_k8s_yaml", {}).action
            is PolicyAction.DENY
        )


def test_orchestrator_mutations_require_approval(monkeypatch):
    _, orchestrator, _ = load_configs(monkeypatch)
    policy = ToolPolicy(orchestrator.tool_policy)

    for tool_name in (
        "apply_k8s_yaml",
        "patch_k8s_resource",
        "scale_k8s_deployment",
        "restart_k8s_deployment",
        "update_k8s_deployment_image_tag",
    ):
        assert (
            policy.classify(tool_name, {}).action
            is PolicyAction.APPROVAL_REQUIRED
        )

    assert (
        policy.classify("run_command_in_k8s_pod", {}).action
        is PolicyAction.DENY
    )

