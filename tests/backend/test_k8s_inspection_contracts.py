from backend.host.orchestration.contracts import contract_guidance, missing_contract_checks


def evidence(tool, resource_ids=(), state="returned"):
    return {"tool": tool, "resource_ids": list(resource_ids), "result_state": state, "call_id": tool}


def test_pending_pod_contract_requires_raw_status_events_and_node_evidence():
    items = [
        evidence("describe_k8s_pod", ["Pod/default/pod-a"]),
        evidence("list_k8s_pod_event"),
    ]
    assert missing_contract_checks("pod_pending", items) == ["pod_status_and_scheduling_gates", "node_fit"]
    items.extend([
        evidence("get_k8s_resource", ["Pod/default/pod-a"]),
        evidence("describe_k8s_resource", ["Node/master1"]),
    ])
    assert missing_contract_checks("pod_pending", items) == []


def test_security_contract_requires_workload_service_account_rbac_and_policy():
    items = [evidence("get_k8s_resource", ["Deployment/default/app"])]
    assert missing_contract_checks("workload_security", items) == ["service_account", "rbac_bindings_and_rules", "network_policy"]
    items.extend([
        evidence("get_k8s_resource", ["ServiceAccount/default/app"]),
        evidence("get_k8s_resource", ["RoleBinding/default/app"]),
        evidence("get_k8s_resource", ["Role/default/app"]),
        evidence("list_k8s_resource", ["NetworkPolicy/default/app"]),
    ])
    assert missing_contract_checks("workload_security", items) == []


def test_empty_network_policy_list_still_counts_as_checked():
    items = [
        evidence("get_k8s_resource", ["Deployment/default/app"]),
        evidence("get_k8s_resource", ["ServiceAccount/default/app"]),
        evidence("get_k8s_resource", ["RoleBinding/default/app"]),
        evidence("get_k8s_resource", ["Role/default/app"]),
        {"tool": "list_k8s_resource", "resource_ids": [], "result_state": "returned", "arguments_excerpt": '{"kind": "NetworkPolicy", "namespace": "default"}'},
    ]
    assert missing_contract_checks("workload_security", items) == []


def test_pending_contract_guidance_separates_unknown_cause_from_checked_inputs():
    guidance = contract_guidance("pod_pending")
    assert "schedulingGates" in guidance
    assert "unknown" in guidance
