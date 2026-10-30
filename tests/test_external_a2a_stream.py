from types import SimpleNamespace


def test_external_agent_progress_is_not_chat_body_and_final_artifact_wins(monkeypatch):
    import asyncio
    from a2a.types import Task, TaskStatusUpdateEvent
    import backend.a2a_client as client_module

    task = Task.model_validate({
        "id": "remote-task", "contextId": "remote-context", "kind": "task",
        "status": {"state": "completed"},
        "artifacts": [{"artifactId": "report-1", "name": "diagnosis.md",
                       "parts": [{"kind": "text", "text": "## 最终诊断报告"}]}],
    })
    progress = TaskStatusUpdateEvent.model_validate({
        "taskId": "remote-task", "contextId": "remote-context", "kind": "status-update",
        "final": False,
        "status": {"state": "working", "message": {
            "messageId": "progress-1", "role": "agent",
            "parts": [{"kind": "text", "text": "正在采集证据"}],
        }},
    })
    final = TaskStatusUpdateEvent.model_validate({
        "taskId": "remote-task", "contextId": "remote-context", "kind": "status-update",
        "final": True, "status": {"state": "completed"},
    })

    class FakeClient:
        async def send_message(self, message):
            yield task, progress
            yield task, final

        async def close(self):
            pass

    monkeypatch.setattr(client_module, "ClientFactory", lambda config: SimpleNamespace(create=lambda card: FakeClient()))
    monkeypatch.setattr(client_module, "fetch_agent_card", lambda url: asyncio.sleep(0, result=object()))

    async def collect():
        return [event async for event in client_module.stream_message_to_agent(
            "http://example.com/", "诊断", "context-1"
        )]

    events = asyncio.run(collect())
    assert [event["text"] for event in events if event["type"] == "text"] == ["## 最终诊断报告"]
    assert events[-1]["text"] == "## 最终诊断报告"
    assert any(event["type"] == "thinking" and event["text"] == "正在采集证据" for event in events)


def test_project_agent_explicit_text_events_remain_chat_text(monkeypatch):
    import asyncio
    from a2a.types import Task, TaskStatusUpdateEvent
    import backend.a2a_client as client_module

    task = Task.model_validate({
        "id": "source-task", "contextId": "source-context", "kind": "task",
        "status": {"state": "working"},
    })
    update = TaskStatusUpdateEvent.model_validate({
        "taskId": "source-task", "contextId": "source-context", "kind": "status-update",
        "final": False,
        "status": {"state": "working", "message": {
            "messageId": "source-msg", "role": "agent",
            "metadata": {"event_type": "text"},
            "parts": [{"kind": "text", "text": "内置 agent 正文"}],
        }},
    })

    class FakeClient:
        async def send_message(self, message):
            yield task, update

        async def close(self):
            pass

    monkeypatch.setattr(client_module, "ClientFactory", lambda config: SimpleNamespace(create=lambda card: FakeClient()))
    monkeypatch.setattr(client_module, "fetch_agent_card", lambda url: asyncio.sleep(0, result=object()))

    async def collect():
        return [event async for event in client_module.stream_message_to_agent(
            "http://example.com/", "诊断", "context-1"
        )]

    events = asyncio.run(collect())
    assert [event["text"] for event in events if event["type"] == "text"] == ["内置 agent 正文"]
    assert events[-1]["text"] == "内置 agent 正文"
