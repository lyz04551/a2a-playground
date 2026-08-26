from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class AppSettings:
    api_key: str | None = None
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    allow_private_agents: bool = False
    host_max_tasks: int = 12
    host_max_rounds: int = 8
    host_max_concurrency: int = 3
    host_max_attempts: int = 2

    @classmethod
    def from_env(cls) -> "AppSettings":
        origins = os.getenv("PLAYGROUND_CORS_ORIGINS", "")
        host_max_tasks = _bounded_env("HOST_MAX_TASKS", 12, 1, 30)
        host_max_rounds = _bounded_env("HOST_MAX_ROUNDS", 8, 1, 20)
        host_max_concurrency = _bounded_env(
            "HOST_MAX_CONCURRENCY", 3, 1, 5
        )
        host_max_attempts = _bounded_env("HOST_MAX_ATTEMPTS", 2, 1, 2)
        return cls(
            api_key=os.getenv("PLAYGROUND_API_KEY") or None,
            cors_origins=(
                tuple(item.strip() for item in origins.split(",") if item.strip())
                if origins
                else cls.cors_origins
            ),
            allow_private_agents=os.getenv(
                "PLAYGROUND_ALLOW_PRIVATE_AGENTS", ""
            ).lower() in {"1", "true", "yes"},
            host_max_tasks=host_max_tasks,
            host_max_rounds=host_max_rounds,
            host_max_concurrency=host_max_concurrency,
            host_max_attempts=host_max_attempts,
        )


def _bounded_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw in {None, ""} else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def configure_http_security(app: FastAPI, settings: AppSettings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        if (
            settings.api_key
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/ping"
        ):
            scheme, _, token = request.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(
                token, settings.api_key
            ):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "error": "Unauthorized"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)
