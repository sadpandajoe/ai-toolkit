"""Extract the executable fenced blocks from create-pr.md for the contract tests.

The identity and lookup tests run the exact shell the workflow doc tells an
agent to run, so the doc cannot drift from tested behavior. `CREATE_PR_DOC`
points the extraction at another file; it exists only so the tests can be
proven against a fixture before the doc lands.
"""

from __future__ import annotations

import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^```(\w*)[ \t]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)


def create_pr_text() -> str:
    override = os.environ.get("CREATE_PR_DOC")
    path = Path(override) if override else ROOT / "skills/workflows/references/create-pr.md"
    return path.read_text()


def fenced_block(marker: str) -> str:
    """The first fenced block containing ``marker``; AssertionError when none does."""
    for _language, body in FENCE.findall(create_pr_text()):
        if marker in body:
            return body
    raise AssertionError(f"create-pr.md has no fenced block containing {marker!r}")
