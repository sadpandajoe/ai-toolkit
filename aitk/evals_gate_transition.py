"""Checker factory for the evals/gate_transition/ fixture family.

The oracle here is `aitk.checkpoint.advance()` run against a real workflow
contract resolved from `interfaces/contracts.json` — the actual function a
durable workflow calls to move its checkpoint's `phase` forward. `advance()`
raises `CheckpointError` unless the target phase is both declared resumable
(`resume_from`) and reachable from the checkpoint's current phase via a
declared edge in `transitions`. A fixture names a workflow and a target
phase to advance to from that workflow's fresh-`initialize()` starting phase
(`phases[0]`), and the checker asserts whether the real transition graph
calls that legal or illegal — a genuine regression check against the live
contract, not a hand-copied snapshot of its phase list that could drift out
of sync with `interfaces/contracts.json`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import checkpoint


def make_checker(root: Path):
    def checker(fixture: dict) -> tuple[bool, str]:
        for field in ("workflow", "to_phase", "expect_result"):
            if field not in fixture:
                return False, f"fixture missing required field {field!r}"

        workflow = fixture["workflow"]
        to_phase = fixture["to_phase"]
        expect = fixture["expect_result"]
        if expect not in {"legal", "illegal"}:
            return False, f"expect_result {expect!r} must be 'legal' or 'illegal'"

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "PROJECT.md"
            try:
                checkpoint.initialize(root, workflow, path)
            except checkpoint.CheckpointError as error:
                return False, f"initialize({workflow!r}) raised {error}"
            try:
                checkpoint.advance(root, workflow, path, to_phase)
                actual = "legal"
            except checkpoint.CheckpointError:
                actual = "illegal"

        if actual != expect:
            return False, f"advance({workflow!r} -> {to_phase!r}) was {actual!r}, fixture expected {expect!r}"
        return True, f"advance({workflow!r} -> {to_phase!r}) was {actual!r} as expected"

    return checker
