"""Golden-master regression check of the whole CLI (opt-in: ~1-2 minutes).

Run with:  python -m pytest -m historical tests/test_golden.py -q
or directly:  python scripts/golden.py compare
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.historical
def test_cli_matches_golden_snapshot():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "golden.py"), "compare"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout[-20000:] + proc.stderr[-5000:]
