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


def test_agent_configs_declare_orchestration_capabilities(monkeypatch):
    ops, orchestrator, security = load_configs(monkeypatch)

    assert ops.read_only is False
    assert security.read_only is True
    assert orchestrator.read_only is False
    assert ops.risk_level == "write_approval"
    assert orchestrator.risk_level == "write_approval"
    assert "mutation requires approval" in orchestrator.limitations


def test_resource_orchestrator_keeps_stable_id_and_public_name(monkeypatch):
    _, orchestrator, _ = load_configs(monkeypatch)

    assert orchestrator.agent_id == "k8s-orchestrator"
    assert orchestrator.name == "K8s Resource Orchestrator Agent"


def test_resource_orchestrator_does_not_own_helm_mutations(monkeypatch):
    _, orchestrator, _ = load_configs(monkeypatch)
    policy = ToolPolicy(orchestrator.tool_policy)

    assert (
        policy.classify("helm_install_chart", {}).action
        is PolicyAction.DENY
    )


def test_security_is_read_only_and_ops_only_approval_gates_pod_debug(monkeypatch):
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

    ops_policy = ToolPolicy(ops.tool_policy)
    assert (
        ops_policy.classify("run_command_in_k8s_pod", {}).action
        is PolicyAction.APPROVAL_REQUIRED
    )
    assert (
        ToolPolicy(security.tool_policy).classify(
            "run_command_in_k8s_pod", {}
        ).action
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
