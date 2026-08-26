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


def assert_independent_verification(author: str, verifier: str) -> None:
    """Raise if the same identity both produced and verified an artifact.

    Machine-checkable slice of rules/specialist-handoff.md's "never review
    your own work" rule (also stated per-workflow, e.g. fix-bug's and
    create-feature's "never implement from an unreviewed plan the planner
    itself approved"): identity equality is the one thing this function can
    decide deterministically. Whether a fresh reviewer's findings are
    actually correct, or a validator caught a real problem, is eval
    territory -- not this function's job.
    """
    if not isinstance(author, str) or not author:
        raise ValueError("author must be a nonempty string")
    if not isinstance(verifier, str) or not verifier:
        raise ValueError("verifier must be a nonempty string")
    if author == verifier:
        raise ValueError(
            f"verifier must be independent of author (both were {author!r})"
        )
