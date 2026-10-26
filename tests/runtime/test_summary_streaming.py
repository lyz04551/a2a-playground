import asyncio
from types import SimpleNamespace

from a2a_runtime.agent import RuntimeMCPAgent, _display_content, _final_stream_delta, _stream_visible_content


class FakeStreamingModel:
    def __init__(self):
        self.bound = None

    def bind(self, **kwargs):
        self.bound = kwargs
        return self

    async def astream(self, _messages):
        for content in ('{"status":"partial","summary":"第一段', '，第二段\\n结论"}'):
            yield SimpleNamespace(content=content)


def test_forced_summary_uses_streaming_model_and_exposes_summary_incrementally():
    model = FakeStreamingModel()
    agent = SimpleNamespace(_model=model, summary_reserve_seconds=2, summary_max_tokens=128)

    async def collect():
        return [part async for part in RuntimeMCPAgent._force_summary_chunks(agent, '检查', '证据')]

    chunks = asyncio.run(collect())
    raw = ''
    emitted = ''
    updates = []
    for chunk in chunks:
        raw += chunk
        visible = _stream_visible_content(raw)
        if visible.startswith(emitted):
            updates.append(visible[len(emitted):])
            emitted = visible
    reset, tail = _final_stream_delta(_display_content(raw), emitted)
    assert model.bound['max_tokens'] == 128
    assert any(updates)
    assert reset is False
    assert ''.join(updates) + tail == '第一段，第二段\n结论'
