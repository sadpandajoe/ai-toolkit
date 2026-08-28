"""Checker factory for the evals/review_remediation/ fixture family.

`agents/codex/plan-validator.md:57-58` documents a real mapping from its
three review verdicts to `aitk.gates`' six-state vocabulary: `APPROVE` ->
`PASS`, `CHANGES REQUIRED` -> `RETRY`, `REPLAN` -> `RECLASSIFY` or
`ESCALATE` (verdict-dependent, unlike the other two which map to exactly
one state). That mapping is documented prose, not a callable function
(unlike `escalation`'s `aitk.gates.decide_failure()`), so this checker
hardcodes it as ground truth rather than parsing the markdown — a
genuine behavioral check, not schema-only, but one that will drift silently
if the doc's mapping ever changes without this file changing too.
"""

from __future__ import annotations

from pathlib import Path

from .evals_common import require_scenario
from .gates import GATE_STATES

_VERDICT_TO_STATES = {
    "APPROVE": {"PASS"},
    "CHANGES REQUIRED": {"RETRY"},
    "REPLAN": {"RECLASSIFY", "ESCALATE"},
}


def make_checker(root: Path):
    del root

    def checker(fixture: dict) -> tuple[bool, str]:
        error = require_scenario(fixture)
        if error:
            return False, error
        verdict = fixture.get("review_verdict")
        if verdict not in _VERDICT_TO_STATES:
            return False, (
                f"review_verdict {verdict!r} is not one of "
                f"{sorted(_VERDICT_TO_STATES)}"
            )
        expect_state = fixture.get("expect_gate_state")
        if expect_state not in GATE_STATES:
            return False, f"expect_gate_state {expect_state!r} is not a valid gate state"
        allowed = _VERDICT_TO_STATES[verdict]
        if expect_state not in allowed:
            return False, (
                f"review_verdict {verdict!r} maps to {sorted(allowed)}, "
                f"not {expect_state!r} (agents/codex/plan-validator.md:57-58)"
            )
        return True, f"review_verdict {verdict!r} correctly maps to expect_gate_state {expect_state!r}"

    return checker
