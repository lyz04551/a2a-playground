from langchain_core.messages import AIMessage
from a2a_runtime.agent import _display_content, _extract_coverage, _final_stream_delta, _stream_visible_content, _truncated_report


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


def test_final_stream_only_appends_missing_tail():
    assert _final_stream_delta("完整报告", "完整报") == (False, "告")
    assert _final_stream_delta("更正后的报告", "旧草稿") == (True, "更正后的报告")


def test_structured_summary_can_stream_before_json_object_is_complete():
    report = '{"status":"partial","summary":"第一行\\n第二行：检查中，尚未完成","evidence":[]}'
    partial = report[:report.index('尚未完成') + len('尚未')]
    assert _stream_visible_content(partial) == '第一行\n第二'
    assert _display_content(report) == '第一行\n第二行：检查中，尚未完成'


def test_truncated_report_is_not_accepted_as_complete():
    assert _truncated_report(AIMessage(content='报告', response_metadata={'finish_reason': 'length'}), '报告')
    assert _truncated_report(AIMessage(content='报告', usage_metadata={'input_tokens': 10, 'output_tokens': 4096, 'total_tokens': 4106}), '报告', 4096)
    assert not _truncated_report(AIMessage(content='完成。'), '完成。')
