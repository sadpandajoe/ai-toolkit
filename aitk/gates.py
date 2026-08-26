"""Pure gate-decision logic: the RETRY/ESCALATE repeat-failure counting rule.

Mirrors aitk.routing's pure-helper shape: no I/O, no PROJECT.md access.
Persistence for gate history lives in a separate sibling module.
"""

from __future__ import annotations

GATE_STATES = {"PASS", "RETRY", "ESCALATE", "USER_DECISION", "BLOCKED", "RECLASSIFY"}


def decide_failure(
    previous_reason: str | None,
    previous_count: int,
    reason: str,
) -> tuple[str, int]:
    """Decide the gate state for a new failure and the updated repeat count.

    A gate that fails for the same reason it failed last time increments the
    repeat count; a different reason (or no prior failure) resets it to 1.
    The first failure for a reason is RETRY; a second or later consecutive
    failure for the same reason is ESCALATE.
    """
    if not isinstance(reason, str) or not reason:
        raise ValueError("gate failure reason must be a nonempty string")
    if not isinstance(previous_count, int) or isinstance(previous_count, bool) or previous_count < 0:
        raise ValueError("previous_count must be a non-negative integer")
    count = previous_count + 1 if previous_reason == reason else 1
    state = "RETRY" if count == 1 else "ESCALATE"
    return state, count
