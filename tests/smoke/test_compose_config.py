from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_defines_independent_agents_and_health_gates():
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
    }
    for name in ("k8s-ops", "k8s-orchestrator", "k8s-security"):
        assert services[name]["healthcheck"]
        assert services[name]["environment"]["AGENT_PUBLIC_URL"].startswith(
            f"http://{name}:"
        )
    assert services["backend"]["depends_on"]["k8s-ops"]["condition"] == "service_healthy"
    assert services["backend"]["volumes"] == ["backend_data:/app/data"]

