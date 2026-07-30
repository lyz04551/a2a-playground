import asyncio

from backend.events.single_agent import relay_agent_events, stream_step


def test_relay_persists_completion_before_emitting_done():
    async def scenario():
        order = []

        async def upstream():
            yield {"type": "tool_call", "tool": "list_clusters", "task_id": "task-1"}
            yield {"type": "text", "text": "当前有 1 个集群", "task_id": "task-1"}
            yield {"type": "done", "text": "当前有 1 个集群", "task_id": "task-1"}

        async def persist_event(event):
            order.append(("event", event["type"]))

        async def persist_completion(result):
            order.append(("persisted", result["text"]))

        output = [
            event async for event in relay_agent_events(
                upstream(),
                persist_event=persist_event,
                persist_completion=persist_completion,
            )
        ]
        return output, order

    output, order = asyncio.run(scenario())
    assert [event["type"] for event in output] == [
        "tool_call",
        "text",
        "done",
    ]
    assert output[-1]["text"] == "当前有 1 个集群"
    assert order[-1] == ("persisted", "当前有 1 个集群")


def test_relay_recovers_final_text_from_done_event():
    async def scenario():
        persisted = []

        async def upstream():
            yield {"type": "done", "text": "最终总结", "task_id": "task-2"}

        async def persist_completion(result):
            persisted.append(result)

        output = [
            event async for event in relay_agent_events(
                upstream(),
                persist_completion=persist_completion,
            )
        ]
        return output, persisted

    output, persisted = asyncio.run(scenario())
    assert output[0] == {
        "type": "text",
        "text": "最终总结",
        "state": "completed",
        "task_id": "task-2",
    }
    assert output[-1]["type"] == "done"
    assert persisted[0]["text"] == "最终总结"


def test_stream_step_keeps_final_text_alongside_tool_steps():
    assert stream_step({"type": "text", "text": "集群共有 1 个节点"}) == {
        "type": "text",
        "content": "集群共有 1 个节点",
    }
