"""Run the test suite before every estimate.

The tests run in their own Python process, so nothing they do (fixed inputs, patched
functions) can leak into the real run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNING_FLAG = "BOND_ESTIMATOR_SELF_TEST"


@dataclass(frozen=True)
class Result:
    passed: bool
    summary: str  # pytest's last line, e.g. "34 passed in 0.21s"
    output: str


def run() -> Result:
    if os.environ.get(RUNNING_FLAG):
        # A test reached the real gate instead of a patched one; fail rather than recurse.
        raise RuntimeError("self-tests tried to start the self-tests again")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env={**os.environ, RUNNING_FLAG: "1"},
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    last_line = output.strip().splitlines()[-1] if output.strip() else "no output"
    # Exit code 0 only when tests ran and all passed (5 means none were collected).
    return Result(proc.returncode == 0, last_line, output)
