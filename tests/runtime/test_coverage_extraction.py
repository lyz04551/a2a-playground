from a2a_runtime.agent import _extract_coverage, _stream_visible_content


def test_json_fenced_coverage_is_hidden_even_when_citations_are_invalid():
    report = 'Report\n```json\n{"scope":"widgets","expected_targets":["one"],"inspected_targets":["one"],"enumeration_complete":true,"evidence_call_ids":["list_widgets"]}\n```'
    assert _extract_coverage(report, {"call-1"}) == ("Report", None)


def test_trailing_unfenced_coverage_is_hidden_without_removing_report_json():
    report = 'Report\n```json\n{"event_count": 2}\n```\n{"scope":"widgets","expected_targets":["one"],"inspected_targets":["one"],"enumeration_complete":true,"evidence_call_ids":["call-1"]}'
    visible, manifest = _extract_coverage(report, {"call-1"})
    assert visible == 'Report\n```json\n{"event_count": 2}\n```'
    assert manifest["scope"] == "widgets"


def test_named_coverage_and_regular_json_keep_distinct_meanings():
    report = 'Report\n```coverage\n{"scope":"widgets","expected_targets":["one"],"inspected_targets":["one"],"enumeration_complete":true,"evidence_call_ids":["call-1"]}\n```'
    assert _extract_coverage(report, {"call-1"})[0] == "Report"
    normal_json = 'Report\n```json\n{"event_count": 2}\n```'
    assert _extract_coverage(normal_json, {"call-1"}) == (normal_json, None)


def test_coverage_json_is_not_emitted_while_streaming():
    prefix = "Checked widgets.\n"
    block = '```json\n{"scope":"widgets","expected_targets":["one"],"inspected_targets":["one"],"enumeration_complete":true,"evidence_call_ids":["list_widgets"]}\n```'
    for length in range(1, len(block) + 1):
        visible = _stream_visible_content(prefix + block[:length])
        assert "scope" not in visible
        assert "expected_targets" not in visible
