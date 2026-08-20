from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_defines_optional_independent_agents():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load(
        (root / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]

    assert set(services) == {
        "backend",
        "frontend",
        "k8s-ops",
        "k8s-orchestrator",
        "k8s-security",
        "k8s-infrastructure",
        "k8s-helm",
        "k8s-incident-responder",
        "k8s-capacity-planner",
        "k8s-gpu-specialist",
    }
    for name in set(services) - {"backend", "frontend"}:
        assert services[name]["healthcheck"]
        assert services[name]["environment"]["AGENT_PUBLIC_URL"].startswith(
            f"http://{name}:"
        )
    assert not services["backend"].get("depends_on")
    assert services["backend"]["volumes"] == ["backend_data:/app/data"]
