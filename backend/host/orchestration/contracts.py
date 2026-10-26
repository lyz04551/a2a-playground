"""Evidence requirements for common Kubernetes inspection workflows."""

from __future__ import annotations

import json


_GUIDANCE = {
    "pod_pending": (
        "Read the raw Pod object with get_k8s_resource to inspect status.conditions "
        "and spec.schedulingGates; check Pod scheduling events and read the candidate "
        "Node's taints, conditions, and allocatable capacity. If the scheduler's "
        "reason is absent, label the direct cause unknown. NetworkPolicy controls "
        "traffic, not scheduling; an NFS mount failure after node assignment is "
        "not proof of a Pod with Node: <none> being unschedulable."
    ),
    "workload_security": (
        "Read workload configuration, its ServiceAccount, matching RBAC bindings "
        "and rules, and namespace NetworkPolicy. Mark image contents, runtime UID, "
        "and external registry reachability unknown unless separately observed."
    ),
}


def contract_guidance(contract_id: str | None) -> str:
    return _GUIDANCE.get(contract_id or "", "")


def missing_contract_checks(contract_id: str, evidence: list[dict]) -> list[str]:
    successful = [item for item in evidence if item.get("result_state") in {"returned", "empty"}]

    def has(tool_names: set[str], kinds: tuple[str, ...] = ()) -> bool:
        for item in successful:
            if item.get("tool") not in tool_names:
                continue
            if not kinds or any(str(target).startswith(kinds) for target in item.get("resource_ids", [])):
                return True
            if item.get("tool") == "list_k8s_resource":
                try:
                    arguments = json.loads(item.get("arguments_excerpt") or "{}")
                except (TypeError, ValueError):
                    continue
                if f"{arguments.get('kind')}/" in kinds:
                    return True
        return False

    if contract_id == "pod_pending":
        checks = {
            "pod_status_and_scheduling_gates": has({"get_k8s_resource"}, ("Pod/",)),
            "scheduling_events": has({"list_k8s_pod_event", "list_k8s_event"}),
            "node_fit": has({"get_k8s_resource", "describe_k8s_resource"}, ("Node/",)),
        }
    elif contract_id == "workload_security":
        checks = {
            "workload_configuration": has({"get_k8s_resource", "describe_k8s_resource"}, ("Pod/", "Deployment/", "StatefulSet/", "DaemonSet/")),
            "service_account": has({"get_k8s_resource", "describe_k8s_resource"}, ("ServiceAccount/",)),
            "rbac_bindings_and_rules": (
                has({"get_k8s_resource", "describe_k8s_resource"}, ("RoleBinding/", "ClusterRoleBinding/"))
                and has({"get_k8s_resource", "describe_k8s_resource"}, ("Role/", "ClusterRole/"))
            ),
            "network_policy": has({"list_k8s_resource", "get_k8s_resource"}, ("NetworkPolicy/",)),
        }
    else:
        return []
    return [name for name, verified in checks.items() if not verified]
