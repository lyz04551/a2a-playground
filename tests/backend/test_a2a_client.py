from backend.a2a_client import _unwrap_artifact_text


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
