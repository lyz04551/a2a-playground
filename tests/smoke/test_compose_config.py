from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_defines_postgres_and_migrated_services():
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
        "postgres",
        "backend-migrate",
        "checkpoint-migrate",
    }
    for name in {"k8s-ops", "k8s-orchestrator", "k8s-security"}:
        assert services[name]["healthcheck"]
        assert services[name]["environment"]["AGENT_PUBLIC_URL"].startswith(
            f"http://{name}:"
        )
        assert "AGENT_CHECKPOINT_DATABASE_URL" in services[name][
            "environment"
        ]
        assert services[name]["depends_on"]["checkpoint-migrate"][
            "condition"
        ] == "service_completed_successfully"

    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert services["postgres"]["volumes"]
    assert services["backend"]["environment"]["DATABASE_URL"]
    assert "PLAYGROUND_DB_PATH" not in services["backend"]["environment"]
    assert services["backend"]["depends_on"]["backend-migrate"][
        "condition"
    ] == "service_completed_successfully"
    assert services["backend-migrate"]["depends_on"]["postgres"][
        "condition"
    ] == "service_healthy"
    assert services["checkpoint-migrate"]["depends_on"]["postgres"][
        "condition"
    ] == "service_healthy"
    assert "backend_data" not in compose["volumes"]
    assert "postgres_data" in compose["volumes"]
