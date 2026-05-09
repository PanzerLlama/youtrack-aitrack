"""Smoke test for scripts/verify-hooks.sh."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify-hooks.sh"


def test_verify_hooks_exits_zero_on_intact_chain() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"verify-hooks.sh failed unexpectedly\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
