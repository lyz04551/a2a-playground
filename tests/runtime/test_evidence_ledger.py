from a2a_runtime.evidence import build_evidence_ledger, build_assessment
from a2a_runtime.agent import _runtime_result


def test_runtime_binds_real_call_ids_and_resource_targets():
    calls = {
        "list-1": {"tool": "list_k8s_pod", "arguments": {"namespace": "default"}},
        "read-1": {"tool": "describe_k8s_pod", "arguments": {"namespace": "default", "name": "pod-a"}},
    }
    results = {
        "list-1": '[{"name":"pod-a","namespace":"default"},{"name":"pod-b","namespace":"default"}]',
        "read-1": "Name: pod-a\nStatus: Running",
    }

    evidence, coverage = build_evidence_ledger(calls, results)

    assert [item["call_id"] for item in evidence] == ["list-1", "read-1"]
    assert evidence[1]["resource_ids"] == ["Pod/default/pod-a"]
    assert coverage["expected_targets"] == ["Pod/default/pod-a", "Pod/default/pod-b"]
    assert coverage["inspected_targets"] == ["Pod/default/pod-a"]
    assert coverage["evidence_call_ids"] == ["list-1", "read-1"]
    assert coverage["enumeration_complete"] is True


def test_failed_tool_cannot_verify_resource_and_unknown_list_stays_incomplete():
    calls = {
        "list-1": {"tool": "list_k8s_pod", "arguments": {"namespace": "default"}},
        "read-1": {"tool": "describe_k8s_pod", "arguments": {"namespace": "default", "name": "pod-a"}},
    }
    evidence, coverage = build_evidence_ledger(calls, {
        "list-1": "工具执行失败：connection refused",
        "read-1": "工具执行失败：timeout",
    })

    assert [item["result_state"] for item in evidence] == ["error", "error"]
    assert coverage["inspected_targets"] == []
    assert coverage["enumeration_complete"] is False


def test_runtime_result_ignores_model_coverage_and_attaches_observed_ids():
    report = 'Checked pod.\n```coverage\n{"scope":"fake","expected_targets":["invented"],"inspected_targets":["invented"],"enumeration_complete":true,"evidence_call_ids":["fake-call"]}\n```'
    visible, evidence, coverage = _runtime_result(
        report,
        {"real-call": {"tool": "describe_k8s_pod", "arguments": {"name": "pod-a", "namespace": "default"}}},
        {"real-call": "Name: pod-a"},
    )

    assert visible == "Checked pod."
    assert coverage["evidence_call_ids"] == ["real-call"]
    assert coverage["inspected_targets"] == ["Pod/default/pod-a"]
    assert evidence[0]["resource_ids"] == ["Pod/default/pod-a"]


def test_assessment_separates_observed_returns_from_missing_targets():
    evidence, coverage = build_evidence_ledger(
        {
            "list-1": {"tool": "list_k8s_pod", "arguments": {"namespace": "default"}},
            "read-1": {"tool": "describe_k8s_pod", "arguments": {"namespace": "default", "name": "pod-a"}},
        },
        {"list-1": '[{"name":"pod-a"},{"name":"pod-b"}]', "read-1": "Name: pod-a"},
    )
    assessment = build_assessment(evidence, coverage)
    assert assessment["facts"][1]["evidence_call_ids"] == ["read-1"]
    assert assessment["inferences"] == []
    assert assessment["unknowns"] == [{"resource_id": "Pod/default/pod-b", "reason": "not inspected"}]
