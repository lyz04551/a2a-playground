import os
import subprocess
import sys
from pathlib import Path


def test_main_imports_when_backend_is_used_as_app_dir():
    root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([
            str(root / "backend"),
            str(root / "agents" / "shared-runtime"),
        ]),
        "PLAYGROUND_DB_PATH": str(root / "backend" / "data" / "playground-local.db"),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import main; "
                "assert main.relay_agent_events; "
                "assert main.build_event_feed"
            ),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
