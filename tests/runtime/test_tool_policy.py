from __future__ import annotations

from a2a_runtime.config import ToolPolicyConfig
from a2a_runtime.models import PendingAction, PolicyAction
from a2a_runtime.tool_policy import ToolPolicy


def make_policy() -> ToolPolicy:
    return ToolPolicy(
        ToolPolicyConfig(
            allow=["list_k8s_*", "get_k8s_*", "patch_k8s_resource"],
            deny=["get_k8s_pod_linked_env"],
            approval_required=["patch_k8s_resource"],
        )
    )


def test_read_only_allow_pattern_executes_without_approval():
    decision = make_policy().classify("get_k8s_pod_logs", {"name": "api"})

    assert decision.action is PolicyAction.ALLOW


def test_explicit_deny_overrides_broad_allow():
    decision = make_policy().classify("get_k8s_pod_linked_env", {"name": "api"})

    assert decision.action is PolicyAction.DENY
    assert "agent policy" in decision.reason


def test_mutation_returns_approval_required():
    decision = make_policy().classify(
        "patch_k8s_resource",
        {"name": "api", "patch_data": '{"spec":{"replicas":2}}'},
    )

    assert decision.action is PolicyAction.APPROVAL_REQUIRED


def test_global_dangerous_tool_deny_overrides_agent_configuration():
    policy = ToolPolicy(
        ToolPolicyConfig(
            allow=["run_command_in_k8s_pod"],
            approval_required=["run_command_in_k8s_pod"],
        )
    )

    decision = policy.classify(
        "run_command_in_k8s_pod",
        {"namespace": "default", "name": "api", "command": "sh"},
    )

    assert decision.action is PolicyAction.DENY
    assert "global policy" in decision.reason


def test_unmatched_tool_is_denied_by_default():
    decision = make_policy().classify("unknown_tool", {})

    assert decision.action is PolicyAction.DENY


def test_pending_action_digest_is_stable_across_json_key_order():
    first = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="patch_k8s_resource",
        arguments={"namespace": "default", "name": "api"},
    )
    second = PendingAction.from_call(
        approval_id="ap-2",
        agent_id="k8s-orchestrator",
        tool_name="patch_k8s_resource",
        arguments={"name": "api", "namespace": "default"},
    )

    assert first.action_digest == second.action_digest
    assert first.matches("patch_k8s_resource", second.arguments)


def test_pending_action_rejects_changed_tool_arguments():
    pending = PendingAction.from_call(
        approval_id="ap-1",
        agent_id="k8s-orchestrator",
        tool_name="scale_k8s_deployment",
        arguments={"namespace": "default", "name": "api", "replicas": 2},
    )

    assert not pending.matches(
        "scale_k8s_deployment",
        {"namespace": "default", "name": "api", "replicas": 3},
    )
    assert not pending.matches("patch_k8s_resource", pending.arguments)
