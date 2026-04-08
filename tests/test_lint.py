"""Lint enforcement test.

Runs ruff check on the project source and test tree as part of the normal
pytest suite.  This ensures E501 (line too long) and other ruff rules are
caught during `pytest` runs, not only at pre-commit time.

Line limit is 100 characters (see pyproject.toml [tool.ruff] line-length).
Docstrings and inline comments must also respect this limit — ruff-format
does not reflow prose.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_ruff_check_passes() -> None:
    """ruff must report zero violations across src/ and tests/."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/", "tests/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "ruff check found violations — fix them before committing.\n\n"
        + result.stdout
        + result.stderr
    )
