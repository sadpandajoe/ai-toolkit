"""Checker factory for the evals/safety_effects/ fixture family.

The oracle here is `aitk.checkpoint.reserve()`/`apply()` run in sequence
against a real workflow checkpoint — the actual functions that stop a
durable workflow from double-executing an external effect (a PR comment
reply, a publish) across a resume. A fixture declares an ordered `steps`
list of `reserve`/`apply` calls against the `address-feedback` workflow's
one declared idempotency key (`provider_operation`, strategy
`provider_idempotency` — see `interfaces/contracts.json`) and asserts
whether every step succeeds or a specific step raises `CheckpointError`
with a given message substring. This is a genuine behavioral check on the
real effect-safety invariants — reserve-before-apply, idempotent re-reserve,
idempotent re-apply-with-same-digest, and rejection of a changed digest or a
malformed operation ID/digest — not a documentation-consistency check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import checkpoint

WORKFLOW = "address-feedback"
KEY = "provider_operation"


def make_checker(root: Path):
    def checker(fixture: dict) -> tuple[bool, str]:
        for field in ("steps", "expect_outcome"):
            if field not in fixture:
                return False, f"fixture missing required field {field!r}"

        steps = fixture["steps"]
        if not isinstance(steps, list) or not steps:
            return False, "fixture 'steps' must be a nonempty list"
        expect_outcome = fixture["expect_outcome"]
        expect_fail_step = fixture.get("expect_fail_step")
        if expect_outcome != "ok" and expect_fail_step is None:
            return False, "fixture expects a failure but is missing 'expect_fail_step'"

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "PROJECT.md"
            try:
                checkpoint.initialize(root, WORKFLOW, path)
            except checkpoint.CheckpointError as error:
                return False, f"initialize({WORKFLOW!r}) raised {error}"

            for index, step in enumerate(steps):
                action = step.get("action")
                operation_id = step.get("operation_id")
                if action not in {"reserve", "apply"} or not operation_id:
                    return False, f"step {index} has an invalid action/operation_id"
                try:
                    if action == "reserve":
                        checkpoint.reserve(root, WORKFLOW, path, KEY, operation_id)
                    else:
                        checkpoint.apply(
                            root, WORKFLOW, path, KEY, operation_id, step.get("result_digest", "")
                        )
                except checkpoint.CheckpointError as error:
                    if expect_outcome == "ok":
                        return False, f"step {index} ({action}) unexpectedly raised: {error}"
                    if index != expect_fail_step:
                        return False, (
                            f"step {index} ({action}) raised {error!r}, "
                            f"but fixture expected the failure at step {expect_fail_step}"
                        )
                    if expect_outcome not in str(error):
                        return False, (
                            f"step {index} ({action}) raised {error!r}, which does not "
                            f"contain expected substring {expect_outcome!r}"
                        )
                    return True, f"step {index} ({action}) raised as expected: {error}"

        if expect_outcome != "ok":
            return False, f"fixture expected step {expect_fail_step} to fail, but all steps succeeded"
        return True, f"all {len(steps)} steps succeeded as expected"

    return checker
