from backend.events.feed import build_event_feed


def test_event_feed_enriches_single_and_multi_agent_events():
    conversations = [
        {
            "id": "single-1",
            "agent_id": "ops-1",
            "title": "集群检查",
            "type": "single",
        },
        {
            "id": "multi-1",
            "agent_id": "host",
            "title": "扩容工作流",
            "type": "multi",
        },
    ]
    agents = [{"id": "ops-1", "name": "K8s Ops Agent"}]
    events = [
        {
            "id": "evt-1",
            "conversation_id": "single-1",
            "task_id": "task-1",
            "event_type": "completed",
            "state": "completed",
            "content": "检查完成",
            "timestamp": "2026-07-29T10:00:00",
        },
        {
            "id": "evt-2",
            "conversation_id": "multi-1",
            "task_id": "run-1",
            "event_type": "tool_call",
            "state": "working",
            "content": '{"tool":"list_k8s_resources","agent":"K8s Ops Agent"}',
            "timestamp": "2026-07-29T10:01:00",
        },
    ]

    result = build_event_feed(events, conversations, agents)

    assert [event["id"] for event in result] == ["evt-2", "evt-1"]
    assert result[0]["conversation_type"] == "multi"
    assert result[0]["source"] == "multi-agent"
    assert result[0]["agent_name"] == "K8s Ops Agent"
    assert result[0]["payload"]["tool"] == "list_k8s_resources"
    assert result[1]["conversation_type"] == "single"
    assert result[1]["source"] == "single-agent"
    assert result[1]["agent_name"] == "K8s Ops Agent"

