import pytest

from backend.host.orchestration.models import CoverageManifest
from a2a_runtime.agent import _extract_coverage, _tool_evidence


def test_manifest_is_generic_and_requires_declared_targets():
    manifest = CoverageManifest(
        scope="tenant-a/widgets", expected_targets=["one", "two"],
        inspected_targets=["one"], enumeration_complete=True,
        evidence_call_ids=["call-1"],
    )
    assert not manifest.complete
    assert manifest.scope == "tenant-a/widgets"
    with pytest.raises(ValueError):
        CoverageManifest(scope="widgets", expected_targets=["one"], inspected_targets=["two"])


def test_matching_batch_manifests_accumulate_without_rechecking_prior_targets():
    first = CoverageManifest(
        scope="tenant-a/widgets", expected_targets=["one", "two"],
        inspected_targets=["one"], enumeration_complete=True,
        evidence_call_ids=["call-1"],
    )
    second = CoverageManifest(
        scope="tenant-a/widgets", expected_targets=["one", "two"],
        inspected_targets=["two"], enumeration_complete=True,
        evidence_call_ids=["call-2"],
    )
    merged = second.merge(first)
    assert merged.complete
    assert merged.inspected_targets == ["one", "two"]
    assert merged.evidence_call_ids == ["call-1", "call-2"]
    assert second.merge(first.model_copy(update={"scope": "other"})).inspected_targets == ["two"]


def test_coverage_block_requires_observed_call_ids():
    report = 'Report\n```coverage\n{"scope":"widgets","expected_targets":["one"],"inspected_targets":["one"],"enumeration_complete":true,"evidence_call_ids":["call-1"]}\n```'
    visible, manifest = _extract_coverage(report, {"call-1"})
    assert visible == "Report"
    assert manifest["scope"] == "widgets"
    assert _extract_coverage(report, set()) == ("Report", None)


def test_tool_evidence_marks_empty_and_redacts_json_fields():
    evidence = _tool_evidence(
        {"call-1": {"tool": "inspect", "arguments": {"name": "one"}, "called_at": "2026-10-21T00:00:00Z"}},
        {"call-1": '{"name":"one","token":"private"}'},
    )
    assert evidence[0]["call_id"] == "call-1"
    assert "private" not in evidence[0]["result_excerpt"]
    assert _tool_evidence({}, {"call-2": ""})[0]["result_state"] == "empty"
