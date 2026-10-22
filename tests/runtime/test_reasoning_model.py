from langchain_core.messages import AIMessageChunk

from a2a_runtime.reasoning_model import ReasoningChatOpenAI


def test_reasoning_delta_is_preserved_separately_from_visible_content():
    model = ReasoningChatOpenAI(model="test", api_key="test", base_url="http://localhost")
    chunk = {
        "choices": [{
            "delta": {"role": "assistant", "content": "answer", "reasoning_content": "analysis"},
            "finish_reason": None,
        }],
    }
    result = model._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)
    assert result.message.content == "answer"
    assert result.message.additional_kwargs["reasoning_content"] == "analysis"
