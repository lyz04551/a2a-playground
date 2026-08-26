from __future__ import annotations

import json
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_AGENT_SERVICES = {
    "k8s-orchestrator",
    "k8s-ops",
    "k8s-security",
}


def _compose():
    return yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )


def test_compose_offers_all_local_agents_without_backend_startup_dependency():
    services = _compose()["services"]

    assert EXPECTED_AGENT_SERVICES <= set(services)
    backend_dependencies = set((services["backend"].get("depends_on") or {}))
    assert backend_dependencies.isdisjoint(EXPECTED_AGENT_SERVICES)
    assert backend_dependencies == {"backend-migrate"}


def test_optional_bootstrap_catalog_has_three_unique_local_agents():
    raw = _compose()["services"]["backend"]["environment"]["BOOTSTRAP_AGENTS"]
    definitions = json.loads(raw)

    assert {item["id"] for item in definitions} == EXPECTED_AGENT_SERVICES
    assert len(definitions) == len(EXPECTED_AGENT_SERVICES)
