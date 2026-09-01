"""Checker factory for the evals/resume/ fixture family.

Like `evals_escalation`, this family has a real pure-function oracle:
`aitk.checkpoint.reconcile_pending()` *is* the resume-after-interruption
decision rule — given a possibly-pending effect record, the idempotency
strategy declared for its key, and a `lookup(operation_id) -> digest|None`
callback standing in for "does the external system already show this
operation happened", it decides whether resuming a workflow should treat the
effect as already done, stop and ask the user, apply what was observed, or
retry the same operation ID. The checker calls the real function with the
fixture's inputs and compares its output to the fixture's expectation — a
genuine behavioral regression check on the resume logic itself, not a
structural proxy for it.

`reconcile_pending` is pure (`del root` below — no repo content is read), so
the checker builds a minimal single-key contract from the fixture's declared
`strategy` rather than resolving a real workflow contract from disk.
"""

from __future__ import annotations

from pathlib import Path

from .checkpoint import CheckpointError, reconcile_pending


def make_checker(root: Path):
    del root  # reconcile_pending is pure; no repo content to read

    def checker(fixture: dict) -> tuple[bool, str]:
        for field in ("effect", "strategy", "expect_action"):
            if field not in fixture:
                return False, f"fixture missing required field {field!r}"

        effect = dict(fixture["effect"])
        for field in ("status", "operation_id"):
            if field not in effect:
                return False, f"fixture effect missing required field {field!r}"
        effect.setdefault("result_digest", None)
        effect["key"] = "k"

        contract = {"idempotency_keys": [{"key": "k", "strategy": fixture["strategy"]}]}
        observed_digest = fixture.get("observed_digest")
        lookup = lambda operation_id: observed_digest  # noqa: E731

        try:
            action, digest = reconcile_pending(contract, effect, lookup)
        except CheckpointError as error:
            return False, f"reconcile_pending raised {error}"

        expect_action = fixture["expect_action"]
        if action != expect_action:
            return False, f"reconcile_pending returned action {action!r}, expected {expect_action!r}"

        expect_digest = fixture.get("expect_digest")
        if expect_digest is not None and digest != expect_digest:
            return False, f"reconcile_pending returned digest {digest!r}, expected {expect_digest!r}"
        if expect_digest is None and digest is not None:
            return False, f"reconcile_pending returned digest {digest!r}, expected None"

        return True, f"reconcile_pending(strategy={fixture['strategy']!r}, status={effect['status']!r}) -> {action!r}, {digest!r}"

    return checker
