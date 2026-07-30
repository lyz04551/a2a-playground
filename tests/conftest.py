from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_RUNTIME = PROJECT_ROOT / "agents" / "shared-runtime"
BACKEND = PROJECT_ROOT / "backend"

for path in (BACKEND, SHARED_RUNTIME, PROJECT_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


@pytest.fixture
def anyio_backend():
    return "asyncio"
