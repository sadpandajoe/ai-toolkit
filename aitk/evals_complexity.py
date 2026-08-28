"""Checker factory for the evals/complexity/ fixture family.

Whether a scenario is actually TRIVIAL/STANDARD/COMPLEX is a judgment call
(`rules/complexity-gate.md`) — there is no pure function to call the way
`escalation`'s checker calls `aitk.gates.decide_failure()`. Structural mode
(the CI default) can only validate that a fixture is well-formed: it has a
non-empty scenario and its `expect_complexity` is a real enum member. It
cannot tell you whether that expectation is the *correct* classification for
the scenario — that requires a model in the loop, which `aitk evals-run
--live` provides once a dispatch path exists for it (see
`aitk/evals_live.py`).
"""

from __future__ import annotations

from pathlib import Path

from .evals_common import make_enum_checker
from .size_axis import COMPLEXITY_VALUES


def make_checker(root: Path):
    del root
    return make_enum_checker("expect_complexity", COMPLEXITY_VALUES)
