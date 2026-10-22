import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

@pytest.fixture(autouse=True)
def isolate_persisted_working_schedule():
    """Keep UI tests deterministic and do not leak a test approval into local data."""
    import backend
    path = backend.ROOT / "working_appointments.csv"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()
