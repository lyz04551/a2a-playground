import os
import subprocess
import sys
from pathlib import Path


def test_backend_uses_one_canonical_package_namespace():
    root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([
            str(root),
            str(root / "agents" / "shared-runtime"),
        ]),
        "PLAYGROUND_DB_PATH": str(root / "backend" / "data" / "playground-local.db"),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import backend.main as main; "
                "from backend.api.runs import RunEvent as ApiEvent; "
                "from backend.orchestration.service import RunEvent as ServiceEvent; "
                "from backend.orchestration.strategies import RunEvent as StrategyEvent; "
                "from backend.persistence.repository import RunEvent as RepositoryEvent; "
                "assert main.relay_agent_events; "
                "assert main.build_event_feed; "
                "assert ApiEvent is ServiceEvent is StrategyEvent is RepositoryEvent; "
                "assert not any(name in sys.modules for name in "
                "['main', 'orchestration.events', 'api.runs', 'persistence.repository'])"
            ),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
