"""Checker factory for the evals/decomposition/ fixture family.

`skills/planning/references/decompose-work.md` names the five things an
architecture decomposition must produce for `MULTI_PHASE` work:
boundaries, dependencies/ordering, global invariants, risks, and phase
exit goals. Structural mode can only check that a fixture actually
populates all five as non-empty lists — not that the decomposition itself
is a *good* one. Whether the boundaries are the right boundaries needs a
model in the loop (`aitk evals-run --live`).
"""

from __future__ import annotations

from pathlib import Path

from .evals_common import require_scenario

_REQUIRED_LIST_FIELDS = (
    "boundaries",
    "dependencies",
    "invariants",
    "risks",
    "phase_exit_goals",
)


def make_checker(root: Path):
    del root

    def checker(fixture: dict) -> tuple[bool, str]:
        error = require_scenario(fixture)
        if error:
            return False, error
        for field in _REQUIRED_LIST_FIELDS:
            value = fixture.get(field)
            if not isinstance(value, list) or not value:
                return False, f"fixture field {field!r} must be a non-empty list"
        return True, (
            "all five decomposition fields present as non-empty lists "
            "(structural mode validates fixture shape only — whether these "
            "are the *right* boundaries needs `aitk evals-run --live`)"
        )

    return checker
