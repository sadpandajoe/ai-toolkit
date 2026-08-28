"""Shared structural-mode validation helpers for the `evals_*.py` checkers.

Several fixture families (complexity, size, execution_shape, phaseability)
share the same structural-mode shape: a non-empty `scenario`, optionally a
few other non-empty text fields, then membership of one field in a fixed
enum. `require_scenario` alone is also reused by decomposition and
review_remediation, which have distinct core logic beyond the scenario check.
None of this validates that the fixture's expectation is *correct* — only a
model in the loop (`aitk evals-run --live`) can do that; see each family's
own module docstring for why.
"""

from __future__ import annotations

from typing import Callable, Collection, Iterable

Checker = Callable[[dict], tuple[bool, str]]


def require_scenario(fixture: dict) -> str | None:
    """Return an error message if `scenario` is missing/empty, else None."""
    if not fixture.get("scenario"):
        return "fixture missing non-empty 'scenario' text"
    return None


def require_fields(fixture: dict, fields: Iterable[str]) -> str | None:
    """Return an error message for the first missing/empty field, else None."""
    for field in fields:
        if not fixture.get(field):
            return f"fixture missing non-empty {field!r}"
    return None


def make_enum_checker(
    field: str,
    values: Collection[str],
    *,
    extra_required: tuple[str, ...] = (),
    verb: str = "classification",
    detail: str = "is a valid enum member",
) -> Checker:
    """Build a structural checker: scenario -> extra_required -> field in values.

    `detail` describes what the PASS reason says backs the expectation
    (e.g. "is a valid enum member", or phaseability's "backed by
    signal_summary and expect_reason"). `verb` names what real validation
    would need ("classification", "reasoning").
    """

    def checker(fixture: dict) -> tuple[bool, str]:
        error = require_scenario(fixture)
        if error:
            return False, error
        error = require_fields(fixture, extra_required)
        if error:
            return False, error
        expect = fixture.get(field)
        if expect not in values:
            return False, f"{field} {expect!r} is not one of {sorted(values)}"
        return True, (
            f"{field} {expect!r} {detail} (structural mode validates fixture "
            f"shape only — real {verb} needs `aitk evals-run --live`)"
        )

    return checker
