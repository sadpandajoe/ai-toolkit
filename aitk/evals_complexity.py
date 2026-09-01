"""Checker factory for the evals/complexity/ fixture family.

Whether a scenario is actually TRIVIAL/STANDARD/COMPLEX is a judgment call
(`rules/complexity-gate.md`) — there is no pure function to call the way
`escalation`'s checker calls `aitk.gates.decide_failure()`. Structural mode
(the CI default) can only validate that a fixture is well-formed: it has a
non-empty scenario and its `expect_complexity` is a real enum member. It
cannot tell you whether that expectation is the *correct* classification for
the scenario — that requires a model in the loop, which the `evals` skill
(`skills/evals/SKILL.md`) provides: an agent follows it to dispatch this
family's fixtures through the routed transport and compare verdicts. There
is no CLI `--live` mode for this family — a bare Python harness has no
skill file to host a real dispatch-boundary marker; see `aitk/cli.py`'s
`_evals_run`.
"""

from __future__ import annotations

from pathlib import Path

from .evals_common import make_enum_checker
from .size_axis import COMPLEXITY_VALUES


def make_checker(root: Path):
    del root
    return make_enum_checker("expect_complexity", COMPLEXITY_VALUES)
