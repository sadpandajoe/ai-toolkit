"""Deterministic eval cases: routing, classification derivation, gate budgets.

Judgment-mode cases are model work and are skipped here; they are documented
in `evals/README.md`.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from aitk.conformance import route_workflow
from aitk.project_state import (
    ProjectStateError,
    classify_complexity,
    derive_execution_shape,
    next_gate_status,
)


ROOT = Path(__file__).resolve().parents[1]


def cases(family: str) -> list[dict[str, object]]:
    path = ROOT / "evals" / family / "cases.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class EvalCorpusTests(unittest.TestCase):
    def test_every_family_has_cases_with_stable_shape(self) -> None:
        families = sorted(p.name for p in (ROOT / "evals").iterdir() if p.is_dir())
        self.assertEqual(
            ["complexity", "gates", "planning", "skill_routing", "workflows"], families
        )
        for family in families:
            rows = cases(family)
            self.assertTrue(rows, family)
            ids = [row["id"] for row in rows]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate ids in {family}")
            for row in rows:
                self.assertEqual({"id", "mode", "input", "expected", "source"}, set(row))
                self.assertIn(row["mode"], {"deterministic", "judgment"})

    def test_skill_routing_cases(self) -> None:
        for case in cases("skill_routing"):
            if case["mode"] != "deterministic":
                continue
            with self.subTest(case=case["id"]):
                match = route_workflow(ROOT, str(case["input"]))
                expected = case["expected"]["workflow"]
                actual = match.workflow.name if match is not None and match.workflow else None
                self.assertEqual(expected, actual)

    def test_complexity_cases(self) -> None:
        for case in cases("complexity"):
            if case["mode"] != "deterministic":
                continue
            payload = case["input"]
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                if "error" in expected:
                    with self.assertRaisesRegex(ProjectStateError, str(expected["error"])):
                        derive_execution_shape(payload["size"], payload["phaseability"])
                    continue
                self.assertEqual(
                    expected["complexity"],
                    classify_complexity(payload["proposed"], list(payload["modifiers"])),
                )
                if "shape" in expected:
                    self.assertEqual(
                        expected["shape"],
                        derive_execution_shape(payload["size"], payload["phaseability"]),
                    )

    def test_gate_cases(self) -> None:
        for case in cases("gates"):
            if case["mode"] != "deterministic":
                continue
            payload = case["input"]
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    case["expected"]["status"],
                    next_gate_status(int(payload["attempts"]), bool(payload["same_failure"])),
                )


if __name__ == "__main__":
    unittest.main()
