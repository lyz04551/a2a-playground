from types import SimpleNamespace

from a2a.types import TextPart

from backend.a2a_client import (
    _extract_text_from_artifact,
    _normalize_readiness,
    _unwrap_artifact_text,
)


def test_normalize_readiness_rejects_unknown_states_and_malformed_checks():
    assert _normalize_readiness({"state": "surprising", "checks": {"mcp": "bad"}}) == {
        "state": "degraded",
        "checks": {},
    }


def test_final_result_artifact_is_unwrapped_to_plain_text():
    text = _unwrap_artifact_text(
        '{"text":"当前集群中有 1 个节点。"}'
    )

    assert text == "当前集群中有 1 个节点。"


def test_nested_json_string_result_is_unwrapped():
    text = _unwrap_artifact_text(
        '{"result":"\\"Successfully scaled deployment\\""}'
    )

    assert text == "Successfully scaled deployment"


def test_pending_action_artifact_is_not_public_message_text():
    artifact = SimpleNamespace(
        name="pending_action",
        parts=[TextPart(
            text='{"approval_id":"ap-1","tool_name":"delete_resource"}'
        )],
    )

    assert _extract_text_from_artifact(artifact) == ""
