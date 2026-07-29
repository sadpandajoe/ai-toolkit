from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "bin/aitk"), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_build_check_reports_json(self) -> None:
        result = self.run_cli("build", "--check", "--json")
        self.assertIn(result.returncode, (0, 1))
        payload = json.loads(result.stdout)
        self.assertEqual("build", payload["command"])
        self.assertIn("differences", payload)

    def test_doctor_reports_json(self) -> None:
        result = self.run_cli("doctor", "--json")
        self.assertIn(result.returncode, (0, 1))
        payload = json.loads(result.stdout)
        self.assertEqual("doctor", payload["command"])
        self.assertIn("summary", payload)
        self.assertIn("findings", payload)

    def test_optional_workflows_are_listed_and_routed_explicitly(self) -> None:
        listing = self.run_cli("list", "--with-pgm", "--details", "--json")
        self.assertEqual(0, listing.returncode, listing.stderr)
        items = json.loads(listing.stdout)["workflows"]
        names = {item["name"] for item in items}
        self.assertIn("create-status-report", names)
        pgm = next(item for item in items if item["name"] == "create-status-report")
        self.assertEqual("pgm", pgm["owner_skill"])
        self.assertEqual("local_mutation", pgm["effect"])
        self.assertTrue(pgm["resumable"])

        routed = self.run_cli("route", "--with-pgm", "program health report", "--json")
        self.assertEqual(0, routed.returncode, routed.stderr)
        match = json.loads(routed.stdout)["match"]
        self.assertEqual("create-status-report", match["workflow"])
        self.assertIn("Use $pgm", match["invoke"])

        explicit = self.run_cli(
            "route", "--with-pgm", "$pgm", "create-velocity-report", "--json"
        )
        self.assertEqual(0, explicit.returncode, explicit.stderr)
        self.assertEqual(
            "create-velocity-report", json.loads(explicit.stdout)["match"]["workflow"]
        )

    def test_root_is_discovered_from_a_repository_subdirectory(self) -> None:
        result = subprocess.run(
            [str(ROOT / "bin/aitk"), "list", "--json"],
            cwd=ROOT / "docs",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            "fix-bug", {item["name"] for item in json.loads(result.stdout)["workflows"]}
        )

    def test_model_route_resolves_and_rejects_exactly(self) -> None:
        resolved = self.run_cli(
            "model-route",
            "deep-review",
            "--provider",
            "claude",
            "--boundary",
            "workflows.review-plan-fresh",
            "--json",
        )
        self.assertEqual(0, resolved.returncode, resolved.stderr)
        payload = json.loads(resolved.stdout)
        self.assertEqual("fable", payload["family"])
        self.assertEqual("xhigh", payload["effort"])
        self.assertEqual("plan", payload["controls"]["permission_mode"])
        for contract in (
            "rules/model-assignment.md",
            "rules/stop-rules.md",
            "skills/workflows/SKILL.md",
            "skills/workflows/references/review-plan.md",
            "skills/plan-review/references/architecture.md",
            "skills/testing/references/review-testplan.md",
            "rules/scoring.md",
            "rules/severity.md",
        ):
            self.assertIn(contract, payload["required_contracts"])
        # This boundary reviews *plans*. It rides the review route but is owned
        # by the workflows skill, so the shipped-code review umbrella — and the
        # code-review grading contract it used to drag along — must not reach it.
        for leaked in ("skills/review/SKILL.md", "rules/code-review.md"):
            self.assertNotIn(leaked, payload["required_contracts"])

        rejected = self.run_cli(
            "model-route", "unknown", "--provider", "codex", "--json"
        )
        self.assertEqual(2, rejected.returncode)
        error = json.loads(rejected.stdout)["error"]
        self.assertEqual("MODEL_ROUTE_INVALID", error["code"])


if __name__ == "__main__":
    unittest.main()
