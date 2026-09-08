from __future__ import annotations

import os
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from backend.llm_config import LLMConfig, load_llm_config

SETTING_KEY = "host_model"


class ModelConfigService:
    def __init__(self, repository, encryption_key: str | None = None):
        self.repository = repository
        self._key = encryption_key if encryption_key is not None else os.getenv("HOST_MODEL_CONFIG_KEY", "")

    def _fernet(self) -> Fernet:
        if not self._key:
            raise ValueError("HOST_MODEL_CONFIG_KEY is required to replace the API key")
        try:
            return Fernet(self._key.encode())
        except (TypeError, ValueError) as exc:
            raise ValueError("HOST_MODEL_CONFIG_KEY must be a valid Fernet key") from exc

    def _decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            return self._fernet().decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Stored Host model API key cannot be decrypted") from exc

    def resolve(self) -> LLMConfig:
        default = load_llm_config("HOST")
        saved = self.repository.get_runtime_setting(SETTING_KEY)
        if not saved:
            return default
        return LLMConfig(
            provider=saved["provider"], base_url=saved["base_url"], model=saved["model"],
            api_key=self._decrypt(saved.get("api_key_encrypted", "")) or default.api_key,
        )

    def public(self) -> dict:
        saved = self.repository.get_runtime_setting(SETTING_KEY)
        config = self.resolve()
        return {
            **config.public(),
            "source": "runtime" if saved else "environment",
            "api_key_configured": bool(config.api_key),
        }

    def update(self, data: dict) -> dict:
        provider = str(data.get("provider", "")).strip()
        base_url = str(data.get("base_url", "")).strip().rstrip("/")
        model = str(data.get("model", "")).strip()
        parsed = urlparse(base_url)
        if not provider or not model or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("provider, model, and a valid HTTP(S) base_url are required")
        current = self.repository.get_runtime_setting(SETTING_KEY) or {}
        encrypted = current.get("api_key_encrypted", "")
        api_key = str(data.get("api_key", "")).strip()
        if api_key:
            encrypted = self._fernet().encrypt(api_key.encode()).decode()
        self.repository.set_runtime_setting(SETTING_KEY, {
            "provider": provider, "base_url": base_url, "model": model,
            "api_key_encrypted": encrypted,
        })
        return self.public()

    def reset(self) -> dict:
        self.repository.delete_runtime_setting(SETTING_KEY)
        return self.public()
