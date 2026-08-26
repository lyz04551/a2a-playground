from backend.llm_config import load_llm_config
from backend.settings import AppSettings


def test_host_llm_uses_its_own_configuration(monkeypatch):
    monkeypatch.setenv("HOST_LLM_PROVIDER", "vllm")
    monkeypatch.setenv("HOST_LLM_BASE_URL", "http://host-model:4000/v1/")
    monkeypatch.setenv("HOST_LLM_MODEL", "host-model")
    monkeypatch.setenv("HOST_LLM_API_KEY", "host-secret")
    monkeypatch.setenv("AGENT_LLM_MODEL", "agent-model")

    config = load_llm_config("HOST")

    assert config.provider == "vllm"
    assert config.base_url == "http://host-model:4000/v1"
    assert config.model == "host-model"
    assert config.api_key == "host-secret"
    assert "agent-model" not in str(config)


def test_host_llm_keeps_legacy_deepseek_fallback(monkeypatch):
    for name in ("HOST_LLM_API_KEY", "HOST_LLM_BASE_URL", "HOST_LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "legacy-secret")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://legacy.example/v1")

    config = load_llm_config("HOST")

    assert config.api_key == "legacy-secret"
    assert config.base_url == "https://legacy.example/v1"
    assert config.model == "deepseek-chat"


def test_host_react_limits_have_bounded_defaults(monkeypatch):
    for name in ("HOST_MAX_TASKS", "HOST_MAX_ROUNDS"):
        monkeypatch.delenv(name, raising=False)

    settings = AppSettings.from_env()

    assert settings.host_max_tasks == 12
    assert settings.host_max_rounds == 8


def test_host_react_limits_can_be_configured(monkeypatch):
    monkeypatch.setenv("HOST_MAX_TASKS", "20")
    monkeypatch.setenv("HOST_MAX_ROUNDS", "10")

    settings = AppSettings.from_env()

    assert settings.host_max_tasks == 20
    assert settings.host_max_rounds == 10
