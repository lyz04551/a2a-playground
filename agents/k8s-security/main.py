from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from a2a_runtime import (
    RuntimeAgentExecutor,
    RuntimeMCPAgent,
    create_a2a_app,
    load_agent_config,
    load_prompt,
)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("AGENT_PUBLIC_URL", "http://127.0.0.1:8053")
os.environ.setdefault("K8S_MCP_URL", "http://10.2.0.57:9096/sse")

config = load_agent_config(BASE_DIR / "agent.yaml")
agent = RuntimeMCPAgent(config, load_prompt(BASE_DIR / "prompt.md"))


@asynccontextmanager
async def lifespan(_app):
    await agent.ensure_ready()
    yield
    await agent.shutdown()


app = create_a2a_app(
    config,
    RuntimeAgentExecutor(agent),
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.port)
