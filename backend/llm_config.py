from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def public(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "configured": self.configured,
        }


def load_llm_config(scope: str = "HOST") -> LLMConfig:
    prefix = f"{scope.upper()}_LLM_"
    base_url = (
        os.getenv(f"{prefix}BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")
    model = (
        os.getenv(f"{prefix}MODEL")
        or os.getenv("LLM_MODEL")
        or "deepseek-chat"
    )
    api_key = (
        os.getenv(f"{prefix}API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or ""
    )
    provider = (
        os.getenv(f"{prefix}PROVIDER")
        or os.getenv("LLM_PROVIDER")
        or ("deepseek" if "deepseek.com" in base_url else "openai-compatible")
    )
    return LLMConfig(provider=provider, base_url=base_url, model=model, api_key=api_key)
