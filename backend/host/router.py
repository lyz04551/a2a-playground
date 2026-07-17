"""Host Agent — LLM-powered router that selects the best sub-agent for each request."""

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ROUTER_MODEL = os.getenv("ROUTER_MODEL", "deepseek-chat")
ROUTER_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
ROUTER_BASE_URL = os.getenv("ROUTER_BASE_URL", "https://api.deepseek.com/v1")


async def select_best_agent(message: str, agents: list[dict]) -> Optional[dict]:
    """LLM-based router: pick the best agent for a user message."""
    if not agents:
        return None
    if len(agents) == 1:
        return agents[0]

    lines = []
    for a in agents:
        skills = a.get("skills") or []
        skills_str = "; ".join(
            f"{s.get('name','')}: {s.get('description','')}"
            for s in skills if s.get("name") or s.get("description")
        ) or "general"
        lines.append(f"- {a['name']}: {a.get('description','')} [{skills_str}]")

    prompt = (
        "You are a smart router for a multi-agent system. "
        "Select the single best agent for the user's request.\n\n"
        f"Available agents:\n" + "\n".join(lines) + "\n\n"
        f"User: \"{message}\"\n\n"
        "Reply with ONLY the agent name. If none fit, reply \"none\"."
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{ROUTER_BASE_URL}/chat/completions",
            json={
                "model": ROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 50,
            },
            headers={"Authorization": f"Bearer {ROUTER_API_KEY}"},
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]["content"].strip().strip("\"'")

    if choice.lower() == "none":
        return None

    for a in agents:
        if a["name"] == choice:
            return a
    # Fuzzy match fallback
    for a in agents:
        if choice.lower() in a["name"].lower():
            return a
    return agents[0]
