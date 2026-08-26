from __future__ import annotations

import os
from pathlib import Path

import pytest

from a2a_runtime.config import load_agent_config
from a2a_runtime.models import PolicyAction
from a2a_runtime.tool_policy import ToolPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MCP_TOOLS = {
    "annotate_k8s_resource",
    "apply_k8s_yaml",
    "cordon_k8s_node",
    "delete_k8s_pod",
    "delete_k8s_resource",
    "delete_k8s_yaml",
    "delete_pod_file",
    "describe_k8s_pod",
    "describe_k8s_resource",
    "drain_k8s_node",
    "get_k8s_deployment_hpa_list",
    "get_k8s_deployment_rollout_history",
    "get_k8s_deployment_rollout_status",
    "get_k8s_node_ip_usage",
    "get_k8s_node_resource_usage",
    "get_k8s_pod_count_running_on_node",
    "get_k8s_pod_linked_env",
    "get_k8s_pod_linked_pv",
    "get_k8s_pod_linked_pvc",
    "get_k8s_pod_linked_services",
    "get_k8s_pod_logs",
    "get_k8s_pod_resource_usage",
    "get_k8s_resource",
    "get_k8s_storageclass_pv_count",
    "get_k8s_storageclass_pvc_count",
    "get_k8s_top_node",
    "get_k8s_top_pod",
    "get_large_model_yaml_example",
    "get_metax_gpu_pod_yaml",
    "get_mthreads_gpu_pod_yaml",
    "get_pod_linked_endpoints",
    "get_pod_linked_env_from_yaml",
    "get_pod_linked_ingresses",
    "helm_install_chart",
    "helm_list_releases",
    "helm_uninstall_release",
    "label_k8s_resource",
    "list_files_in_k8s_pod",
    "list_k8s_clusters",
    "list_k8s_deploy_event",
    "list_k8s_event",
    "list_k8s_namespace",
    "list_k8s_node",
    "list_k8s_pod",
    "list_k8s_pod_event",
    "list_k8s_resource",
    "list_pod_all_files",
    "patch_k8s_resource",
    "pause_k8s_deployment_rollout",
    "register_k8s_cluster",
    "restart_k8s_daemonset",
    "restart_k8s_deployment",
    "restore_k8s_deployment",
    "resume_k8s_deployment_rollout",
    "run_command_in_k8s_pod",
    "scale_k8s_deployment",
    "set_default_k8s_ingressclass",
    "set_k8s_default_storageclass",
    "stop_k8s_deployment",
    "taint_k8s_node",
    "uncordon_k8s_node",
    "undo_k8s_deployment_rollout",
    "unregister_k8s_cluster",
    "untaint_k8s_node",
    "update_k8s_deployment_image_tag",
    "upload_file_to_k8s_pod",
}

AGENTS = {
    "k8s-orchestrator": (8051, 40, "write_approval"),
    "k8s-ops": (8052, 20, "write_approval"),
    "k8s-security": (8053, 30, "read_only"),
    "k8s-infrastructure": (8054, 35, "write_approval"),
    "k8s-helm": (8055, 38, "write_approval"),
}

WRITE_TOOLS = {
    "annotate_k8s_resource",
    "apply_k8s_yaml",
    "cordon_k8s_node",
    "delete_k8s_pod",
    "delete_k8s_resource",
    "delete_k8s_yaml",
    "delete_pod_file",
    "drain_k8s_node",
    "helm_install_chart",
    "helm_uninstall_release",
    "label_k8s_resource",
    "patch_k8s_resource",
    "pause_k8s_deployment_rollout",
    "register_k8s_cluster",
    "restart_k8s_daemonset",
    "restart_k8s_deployment",
    "restore_k8s_deployment",
    "resume_k8s_deployment_rollout",
    "run_command_in_k8s_pod",
    "scale_k8s_deployment",
    "set_default_k8s_ingressclass",
    "set_k8s_default_storageclass",
    "stop_k8s_deployment",
    "taint_k8s_node",
    "uncordon_k8s_node",
    "undo_k8s_deployment_rollout",
    "unregister_k8s_cluster",
    "untaint_k8s_node",
    "update_k8s_deployment_image_tag",
    "upload_file_to_k8s_pod",
}


def _load_configs(monkeypatch):
    monkeypatch.setenv("K8S_MCP_URL", "http://mcp.test/mcp")
    monkeypatch.setenv("MCP_TRANSPORT", "streamable_http")
    configs = []
    for agent_id in AGENTS:
        monkeypatch.setenv("AGENT_PUBLIC_URL", f"http://{agent_id}.test")
        configs.append(
            load_agent_config(PROJECT_ROOT / "agents" / agent_id / "agent.yaml")
        )
    return configs


def test_five_agent_configs_have_stable_identity_and_routing_metadata(monkeypatch):
    configs = _load_configs(monkeypatch)

    assert {config.agent_id for config in configs} == set(AGENTS)
    for config in configs:
        port, priority, risk_level = AGENTS[config.agent_id]
        assert config.port == port
        assert config.priority == priority
        assert config.risk_level == risk_level
        assert config.skills
        assert all(skill.tags for skill in config.skills)


def test_every_live_mcp_tool_has_an_agent_owner(monkeypatch):
    configs = _load_configs(monkeypatch)
    policies = [ToolPolicy(config.tool_policy) for config in configs]

    uncovered = {
        tool
        for tool in MCP_TOOLS
        if all(
            policy.classify(tool).action is PolicyAction.DENY
            for policy in policies
        )
    }

    assert uncovered == set()


def test_exact_agent_tool_names_exist_on_live_server_contract(monkeypatch):
    configs = _load_configs(monkeypatch)
    configured = {
        pattern
        for config in configs
        for pattern in (
            config.tool_policy.allow
            + config.tool_policy.deny
            + config.tool_policy.approval_required
        )
        if "*" not in pattern
    }

    assert configured - MCP_TOOLS == set()


def test_mutating_tools_are_never_directly_allowed(monkeypatch):
    configs = _load_configs(monkeypatch)

    violations = {
        (config.agent_id, tool)
        for config in configs
        for tool in WRITE_TOOLS
        if ToolPolicy(config.tool_policy).classify(tool).action
        is PolicyAction.ALLOW
    }

    assert violations == set()


@pytest.mark.parametrize(
    ("agent_id", "tool", "expected"),
    [
        ("k8s-ops", "run_command_in_k8s_pod", PolicyAction.APPROVAL_REQUIRED),
        ("k8s-security", "apply_k8s_yaml", PolicyAction.DENY),
        ("k8s-orchestrator", "delete_k8s_resource", PolicyAction.APPROVAL_REQUIRED),
        ("k8s-infrastructure", "drain_k8s_node", PolicyAction.APPROVAL_REQUIRED),
        ("k8s-helm", "helm_uninstall_release", PolicyAction.APPROVAL_REQUIRED),
    ],
)
def test_representative_agent_tool_boundaries(
    monkeypatch, agent_id, tool, expected
):
    configs = {config.agent_id: config for config in _load_configs(monkeypatch)}

    assert ToolPolicy(configs[agent_id].tool_policy).classify(tool).action is expected


def test_orchestrator_prompt_clarifies_incomplete_create_requests_before_tools():
    prompt = (
        PROJECT_ROOT / "agents" / "k8s-orchestrator" / "prompt.md"
    ).read_text(encoding="utf-8")

    assert "资源名称、namespace 或镜像版本" in prompt
    assert "不得调用任何工具" in prompt
