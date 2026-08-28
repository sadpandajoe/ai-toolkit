"""Checker factory for the evals/phaseability/ fixture family.

Phaseability is the *reasoning* behind an execution_shape pick, not the
pick itself (that's `evals_execution_shape.py`). A fixture here must carry
a `signal_summary` — the observable signals a human or model would weigh
(file count, cross-module coupling, whether steps can run independently)
— and an `expect_reason` string explaining why those signals justify
`expect_execution_shape`. Structural mode can only check that both are
present and non-empty; whether the reasoning is actually sound needs
`aitk evals-run --live`.
"""

from __future__ import annotations

from pathlib import Path

from .evals_common import make_enum_checker
from .size_axis import EXECUTION_SHAPE_VALUES


def make_checker(root: Path):
    del root
    return make_enum_checker(
        "expect_execution_shape",
        EXECUTION_SHAPE_VALUES,
        extra_required=("signal_summary", "expect_reason"),
        verb="reasoning",
        detail="backed by signal_summary and expect_reason",
    )
