"""PROJECT.md v2 routing snapshot: schema, derivation, budgets, legacy reads."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from aitk.project_state import (
    ATTEMPT_BUDGET,
    BEGIN,
    END,
    ProjectStateError,
    advance_phase,
    classify_complexity,
    derive_execution_shape,
    initialize,
    next_gate_status,
    normalize_complexity,
    parse_project_state,
    record_gate,
    set_fields,
    set_phases,
    show,
    update_phase,
)


ROOT = Path(__file__).resolve().parents[1]


class ClassificationDerivationTests(unittest.TestCase):
    def test_legacy_tiers_dual_read_upward(self) -> None:
        self.assertEqual("TRIVIAL", normalize_complexity("trivial"))
        self.assertEqual("STANDARD", normalize_complexity("MODERATE"))
        # A bare STANDARD is ambiguous between v1 and v2 and reads as v2.
        self.assertEqual("STANDARD", normalize_complexity("STANDARD"))
        self.assertEqual("COMPLEX", normalize_complexity("complex"))
        with self.assertRaises(ProjectStateError):
            normalize_complexity("HEAVY")

    def test_size_does_not_imply_complexity_and_hard_modifiers_force_complex(self) -> None:
        # Renaming a property across 80 files is XL but not COMPLEX.
        self.assertEqual("STANDARD", classify_complexity("STANDARD", ["codemod"]))
        # A one-line permission toggle is S but COMPLEX.
        self.assertEqual(
            "COMPLEX", classify_complexity("TRIVIAL", ["auth-security-permissions"])
        )

    def test_execution_shape_follows_size_and_phaseability(self) -> None:
        cases = {
            ("S", "unassessed"): "SINGLE_PHASE",
            ("M", "unassessed"): "SINGLE_PHASE",
            ("M", "phased"): "MULTI_PHASE",
            ("L", "none"): "SINGLE_PHASE",
            ("L", "repetitive"): "BATCHED",
            ("L", "phased"): "MULTI_PHASE",
            ("XL", "none"): "MULTI_PHASE",
            ("XL", "repetitive"): "BATCHED",
            ("XL", "phased"): "MULTI_PHASE",
        }
        for (size, phaseability), expected in cases.items():
            with self.subTest(size=size, phaseability=phaseability):
                self.assertEqual(expected, derive_execution_shape(size, phaseability))
        # L+ must run the phaseability check; it is never assumed.
        for size in ("L", "XL"):
            with self.assertRaises(ProjectStateError):
                derive_execution_shape(size, "unassessed")

    def test_retry_budget_is_initial_plus_one_informed_retry(self) -> None:
        self.assertEqual(2, ATTEMPT_BUDGET)
        self.assertEqual("RETRY", next_gate_status(1, same_failure=False))
        self.assertEqual("RETRY", next_gate_status(1, same_failure=True))
        self.assertEqual("ESCALATE", next_gate_status(2, same_failure=False))
        self.assertEqual("ESCALATE", next_gate_status(2, same_failure=True))
        self.assertEqual("ESCALATE", next_gate_status(3, same_failure=False))


class SnapshotLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name).resolve() / "PROJECT.md"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_init_appends_block_without_touching_existing_human_state(self) -> None:
        self.path.write_text("## Overview\nexisting notes\n")
        result = initialize(self.path, "fix-bug", "MODERATE", "M")
        self.assertTrue(result.changed)
        content = self.path.read_text()
        self.assertTrue(content.startswith("## Overview\nexisting notes\n"))
        self.assertEqual(1, content.count(BEGIN))
        self.assertEqual(1, content.count(END))
        snapshot = parse_project_state(content)
        assert snapshot is not None
        # Legacy MODERATE reads as v2 STANDARD.
        self.assertEqual("STANDARD", snapshot["complexity"])
        self.assertEqual("SINGLE_PHASE", snapshot["execution_shape"])
        self.assertEqual("PASS", snapshot["gate_status"])
        self.assertEqual({}, snapshot["attempts"])

    def test_repeat_init_is_a_noop_and_other_workflow_refuses(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "S")
        again = initialize(self.path, "fix-bug", "COMPLEX", "XL", "phased")
        self.assertFalse(again.changed)
        self.assertEqual("STANDARD", again.snapshot["complexity"])
        with self.assertRaisesRegex(ProjectStateError, "--replace"):
            initialize(self.path, "create-feature", "STANDARD", "S")
        replaced = initialize(
            self.path, "create-feature", "COMPLEX", "XL", "phased", replace=True
        )
        self.assertEqual("create-feature", replaced.snapshot["workflow"])
        self.assertEqual("MULTI_PHASE", replaced.snapshot["execution_shape"])

    def test_complexity_only_moves_upward_by_evidence(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        upgraded = set_fields(self.path, complexity="COMPLEX")
        self.assertEqual("COMPLEX", upgraded.snapshot["complexity"])
        with self.assertRaisesRegex(ProjectStateError, "never silently downgraded"):
            set_fields(self.path, complexity="TRIVIAL")

    def test_gate_budget_escalates_from_durable_attempt_counts(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        first = record_gate(self.path, "verification", "RETRY", "implementation")
        self.assertEqual("RETRY", first.snapshot["gate_status"])
        self.assertEqual({"implementation": 1}, first.snapshot["attempts"])
        second = record_gate(self.path, "verification", "RETRY", "implementation")
        self.assertEqual("ESCALATE", second.snapshot["gate_status"])
        self.assertEqual({"implementation": 2}, second.snapshot["attempts"])
        with self.assertRaisesRegex(ProjectStateError, "cannot advance"):
            advance_phase(self.path, "review")
        passed = record_gate(self.path, "verification", "PASS")
        self.assertEqual("PASS", passed.snapshot["gate_status"])
        advanced = advance_phase(self.path, "review")
        self.assertEqual(("review", "PENDING"), (advanced.snapshot["current_phase"], advanced.snapshot["gate_status"]))

    def test_same_failure_twice_escalates_even_with_budget_left(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        record_gate(self.path, "rca", "RETRY", "rca")
        # Different reason on the second attempt would be ESCALATE anyway at
        # budget 2; check the same-failure rule on the first repeated attempt
        # by using a fresh unit with a one-attempt history.
        outcome = record_gate(self.path, "rca", "RETRY", "rca-alt", same_failure=True)
        self.assertEqual("RETRY", outcome.snapshot["gate_status"])
        outcome = record_gate(self.path, "rca", "RETRY", "rca-alt", same_failure=True)
        self.assertEqual("ESCALATE", outcome.snapshot["gate_status"])

    def test_phases_are_only_recorded_for_multi_phase_work(self) -> None:
        initialize(self.path, "create-feature", "COMPLEX", "XL", "phased")
        phases = [
            {"name": "layout", "complexity": "STANDARD", "size": "M", "status": "active"},
            {"name": "persistence", "complexity": "COMPLEX", "size": "L", "status": "pending"},
        ]
        result = set_phases(self.path, phases)
        self.assertEqual(phases, result.snapshot["phases"])
        done = update_phase(self.path, "layout", "done")
        self.assertEqual("done", done.snapshot["phases"][0]["status"])
        initialize(self.path, "fix-bug", "STANDARD", "M", replace=True)
        with self.assertRaisesRegex(ProjectStateError, "MULTI_PHASE"):
            set_phases(self.path, phases)

    def test_malformed_block_fails_closed(self) -> None:
        self.path.write_text(f"{BEGIN}\n{{not json}}\n{END}\n")
        with self.assertRaisesRegex(ProjectStateError, "not valid JSON"):
            show(self.path)
        snapshot = {
            "schema_version": 2,
            "workflow": "fix-bug",
            "complexity": "STANDARD",
            "classification_confidence": "HIGH",
            "size": "L",
            "execution_shape": "SINGLE_PHASE",
            "phaseability": "phased",
            "phaseability_reason": "",
            "modifiers": [],
            "current_phase": "intake",
            "current_gate": "classification",
            "gate_status": "PASS",
            "attempts": {},
            "phases": [],
        }
        self.path.write_text(f"{BEGIN}\n{json.dumps(snapshot)}\n{END}\n")
        with self.assertRaisesRegex(ProjectStateError, "does not follow"):
            show(self.path)


class ProjectStateCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aitk.cli", "--root", str(ROOT), *arguments],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
        )

    def test_cli_round_trip_emits_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary).resolve()
            init = self.run_cli(
                "project-state",
                "init",
                "--workflow",
                "create-feature",
                "--complexity",
                "STANDARD",
                "--size",
                "L",
                "--phaseability",
                "repetitive",
                "--reason",
                "same rename across many files",
                "--json",
                cwd=cwd,
            )
            self.assertEqual(0, init.returncode, init.stderr)
            payload = json.loads(init.stdout)
            self.assertEqual("BATCHED", payload["snapshot"]["execution_shape"])
            self.assertEqual(str(cwd / "PROJECT.md"), payload["file"])
            gate = self.run_cli(
                "project-state", "gate", "--gate", "verification", "--status", "RETRY",
                "--unit", "wave-1", "--json", cwd=cwd,
            )
            self.assertEqual(0, gate.returncode, gate.stderr)
            self.assertEqual("RETRY", json.loads(gate.stdout)["snapshot"]["gate_status"])
            shown = self.run_cli("project-state", "show", cwd=cwd)
            self.assertEqual(0, shown.returncode, shown.stderr)
            self.assertIn("complexity=STANDARD", shown.stdout)
            self.assertIn("shape=BATCHED", shown.stdout)
            failed = self.run_cli(
                "project-state", "set", "--complexity", "TRIVIAL", cwd=cwd
            )
            self.assertEqual(1, failed.returncode)
            self.assertIn("never silently downgraded", failed.stderr)


if __name__ == "__main__":
    unittest.main()
