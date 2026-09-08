import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI

from backend.api.runs import create_router
from backend.model_config import ModelConfigService
from backend.host.langgraph.decisions import LangGraphDecisionPort


class Repository:
    def __init__(self): self.value = None
    def get_runtime_setting(self, key): return self.value
    def set_runtime_setting(self, key, data): self.value = dict(data)
    def delete_runtime_setting(self, key): self.value = None; return True


def test_model_config_redacts_retains_and_resets_secret(monkeypatch):
    monkeypatch.setenv("HOST_LLM_API_KEY", "environment-secret")
    monkeypatch.setenv("HOST_LLM_MODEL", "environment-model")
    repository = Repository()
    service = ModelConfigService(repository, Fernet.generate_key().decode())
    result = service.update({"provider": "openai-compatible", "base_url": "https://models.example/v1/", "model": "new-model", "api_key": "new-secret"})
    assert result["source"] == "runtime" and "api_key" not in result
    assert "new-secret" not in str(repository.value)
    service.update({"provider": "openai-compatible", "base_url": "https://models.example/v1", "model": "next-model", "api_key": ""})
    assert service.resolve().api_key == "new-secret"
    assert service.reset()["model"] == "environment-model"


def test_model_config_validates_url_and_encryption_key():
    service = ModelConfigService(Repository(), "")
    with pytest.raises(ValueError, match="valid HTTP"):
        service.update({"provider": "x", "base_url": "file:///tmp/model", "model": "m"})
    with pytest.raises(ValueError, match="HOST_MODEL_CONFIG_KEY"):
        service.update({"provider": "x", "base_url": "https://example.test/v1", "model": "m", "api_key": "secret"})


@pytest.mark.anyio
async def test_model_config_api_never_returns_secret():
    service = ModelConfigService(Repository(), Fernet.generate_key().decode())
    app = FastAPI()
    app.include_router(create_router(object(), service))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/model-config/update", json={"provider": "p", "base_url": "https://example.test/v1", "model": "m", "api_key": "secret"})
        assert response.status_code == 200
        assert "secret" not in response.text
        assert response.json()["result"]["api_key_configured"] is True


def test_host_decision_port_resolves_the_latest_model():
    models = [object(), object()]
    current = {"model": models[0]}
    port = LangGraphDecisionPort(model_factory=lambda: current["model"])
    assert port._current_model() is models[0]
    current["model"] = models[1]
    assert port._current_model() is models[1]
