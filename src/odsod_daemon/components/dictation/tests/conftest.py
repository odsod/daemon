import os
from pathlib import Path

import pytest


@pytest.fixture
def desktop(temp_root, monkeypatch):
    monkeypatch.setenv("PATH", f"{Path(__file__).parent / 'bin'}:{os.environ['PATH']}")
    path = temp_root / "desktop"
    path.mkdir()
    return path
