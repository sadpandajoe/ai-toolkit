"""Checker factory for the evals/size/ fixture family.

Sibling to `evals_complexity.py` — see that module's docstring for why
structural mode can only validate fixture shape, not correctness of the
size estimate itself.
"""

from __future__ import annotations

from pathlib import Path

from .evals_common import make_enum_checker
from .size_axis import SIZE_VALUES


def make_checker(root: Path):
    del root
    return make_enum_checker("expect_size", SIZE_VALUES)
