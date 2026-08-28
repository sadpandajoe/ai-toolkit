"""Checker factory for the evals/escalation/ fixture family.

Unlike the other eval families, this one has a real pure-function oracle:
`aitk.gates.decide_failure()` *is* the repeat-failure counting rule
(`rules/gates.md`'s Repeat-Failure Counting Rule), not a proxy for it. The
checker calls the real function with the fixture's inputs and compares its
output to the fixture's expectation — a genuine behavioral regression check,
not a documentation-consistency check.

A candidate fixture written by `skills/reflection` step 8 only carries
`gate`/`reason`/`skill` (the fields available from a live `gate-repeat`
observation). Promoting a candidate into a live fixture here means adding
`kind`, `previous_count`, `expect_state`, and `expect_count` — the inputs and
expected outputs `decide_failure()` needs — since the observation alone
doesn't record where the repeat count stood.
"""

from __future__ import annotations

from pathlib import Path

from .gates import decide_failure


def make_checker(root: Path):
    del root  # decide_failure is pure; no repo content to read

    def checker(fixture: dict) -> tuple[bool, str]:
        for field in ("reason", "kind", "previous_count", "expect_state"):
            if field not in fixture:
                return False, f"fixture missing required field {field!r}"
        try:
            state, count = decide_failure(
                fixture["previous_count"],
                fixture["reason"],
                kind=fixture["kind"],
            )
        except ValueError as error:
            return False, f"decide_failure raised {error}"

        expect_state = fixture["expect_state"]
        if state != expect_state:
            return False, f"decide_failure returned state {state!r}, expected {expect_state!r}"

        expect_count = fixture.get("expect_count")
        if expect_count is not None and count != expect_count:
            return False, f"decide_failure returned count {count!r}, expected {expect_count!r}"

        return True, f"decide_failure({fixture['previous_count']!r}, kind={fixture['kind']!r}) -> {state!r}, {count!r}"

    return checker
