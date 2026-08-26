import httpx
import pytest
from fastapi import FastAPI

from backend.security import validate_agent_url
from backend.settings import AppSettings, configure_http_security


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://agent.example",
        "http://user:pass@agent.example",
        "http://127.0.0.1:8050",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.2:8051",
    ],
)
async def test_agent_url_rejects_unsafe_targets(url):
    with pytest.raises(ValueError, match="Agent URL"):
        await validate_agent_url(url)


@pytest.mark.anyio
async def test_agent_url_rejects_hostname_resolving_to_private_address():
    async def resolve(_host, _port):
        return {"93.184.216.34", "192.168.1.8"}

    with pytest.raises(ValueError, match="Agent URL"):
        await validate_agent_url("https://agent.example", resolver=resolve)


@pytest.mark.anyio
async def test_private_agent_url_requires_explicit_override():
    assert await validate_agent_url(
        "http://127.0.0.1:8052", allow_private=True
    ) == "http://127.0.0.1:8052"
    assert await validate_agent_url(
        "localhost:8052",
        allow_private=True,
        resolver=lambda _host, _port: _async_value({"127.0.0.1", "::1"}),
    ) == "http://localhost:8052"
    assert await validate_agent_url(
        "http://k8s-ops:8052",
        allow_private=True,
        resolver=lambda _host, _port: _async_value({"172.20.0.2"}),
    ) == "http://k8s-ops:8052"


async def _async_value(value):
    return value


def make_secured_app(settings):
    app = FastAPI()
    configure_http_security(app, settings)

    @app.post("/api/ping")
    async def ping():
        return {"ok": True}

    @app.post("/api/private")
    async def private():
        return {"ok": True}

    return app


@pytest.mark.anyio
async def test_api_key_is_optional_when_unset():
    app = make_secured_app(AppSettings(api_key=None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/private")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_api_key_protects_api_except_ping():
    app = make_secured_app(AppSettings(api_key="secret"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post("/api/private")
        allowed = await client.post(
            "/api/private", headers={"Authorization": "Bearer secret"}
        )
        ping = await client.post("/api/ping")
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert ping.status_code == 200


def test_settings_parse_explicit_cors_origins(monkeypatch):
    monkeypatch.setenv(
        "PLAYGROUND_CORS_ORIGINS", "https://one.example, https://two.example"
    )
    assert AppSettings.from_env().cors_origins == (
        "https://one.example",
        "https://two.example",
    )
