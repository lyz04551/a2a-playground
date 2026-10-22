from __future__ import annotations

from langchain_openai import ChatOpenAI


class ReasoningChatOpenAI(ChatOpenAI):
    """Preserve OpenAI-compatible reasoning deltas in the message stream."""

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        generated = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices") or []
        if generated is not None and choices:
            reasoning = (choices[0].get("delta") or {}).get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                generated.message.additional_kwargs["reasoning_content"] = reasoning
        return generated
