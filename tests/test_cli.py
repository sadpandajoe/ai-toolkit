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
            "--lens",
            "skills/plan-review/references/architecture.md",
            "--json",
        )
        self.assertEqual(0, resolved.returncode, resolved.stderr)
        payload = json.loads(resolved.stdout)
        self.assertEqual("fable", payload["family"])
        self.assertEqual("xhigh", payload["effort"])
        self.assertEqual("plan", payload["controls"]["permission_mode"])
        self.assertEqual("plan", payload["lens_domain"])
        for contract in (
            "rules/model-assignment.md",
            "rules/stop-rules.md",
            "skills/workflows/SKILL.md",
            "skills/workflows/references/review-plan.md",
            "skills/plan-review/references/architecture.md",
            "rules/scoring.md",
            "rules/severity.md",
        ):
            self.assertIn(contract, payload["required_contracts"])
        # This boundary reviews *plans*. It rides the review route but is owned
        # by the workflows skill, so the shipped-code review umbrella — and the
        # code-review grading contract it used to drag along — must not reach it.
        # The grading contract is declared on the code fan-out boundaries rather
        # than in these lens documents precisely so this stays true: the lenses
        # are shared with code review, and a document cannot declare a contract
        # for one of its two domains only.
        for leaked in ("skills/review/SKILL.md", "rules/code-review.md"):
            self.assertNotIn(leaked, payload["required_contracts"])
        # One dispatch, one lens. The sibling lenses on this boundary's menu are
        # what the worker must *not* receive: handing it all six made it review
        # under six conflicting output formats at once.
        for sibling in (
            "skills/plan-review/references/implementation.md",
            "skills/plan-review/references/frontend.md",
            "skills/plan-review/references/backend.md",
            "skills/testing/references/review-testplan.md",
            "skills/pm/references/review-feature-brief.md",
        ):
            self.assertNotIn(sibling, payload["required_contracts"])

        rejected = self.run_cli(
            "model-route", "unknown", "--provider", "codex", "--json"
        )
        self.assertEqual(2, rejected.returncode)
        error = json.loads(rejected.stdout)["error"]
        self.assertEqual("MODEL_ROUTE_INVALID", error["code"])

    def test_model_route_rejects_a_lens_below_its_declared_floor(self) -> None:
        """The architecture lens must not resolve to the cheap route.

        Both fan-out routes are on the boundary's `routes` list, so membership
        alone let an architecture or adversarial dispatch land on Opus/high with
        no complaint — the lens documents say `deep-review` and nothing enforced
        it. The floor lives in the manifest so the resolver checks data rather
        than trusting a dispatcher to have read the prose.
        """
        rejected = self.run_cli(
            "model-route",
            "review",
            "--provider",
            "claude",
            "--boundary",
            "review.pr-standard",
            "--lens",
            "skills/review/references/adversarial.md",
            "--json",
        )
        self.assertEqual(2, rejected.returncode)
        error = json.loads(rejected.stdout)["error"]
        self.assertEqual("MODEL_ROUTE_INVALID", error["code"])
        self.assertIn("below its declared floor", error["message"])

        allowed = self.run_cli(
            "model-route",
            "deep-review",
            "--provider",
            "claude",
            "--boundary",
            "review.pr-standard",
            "--lens",
            "skills/review/references/adversarial.md",
            "--json",
        )
        self.assertEqual(0, allowed.returncode, allowed.stderr)
        payload = json.loads(allowed.stdout)
        self.assertEqual("fable", payload["family"])
        self.assertEqual("xhigh", payload["effort"])
        self.assertEqual("code", payload["lens_domain"])
        # A code fan-out declares the code-review grading contract at the
        # boundary, so every lane there reports in severity tags — including the
        # four lenses this menu shares with plan review.
        self.assertIn("rules/code-review.md", payload["required_contracts"])

    def test_model_route_rejects_a_lens_without_a_boundary(self) -> None:
        """`--lens` alone used to resolve a route that silently ignored it."""
        rejected = self.run_cli(
            "model-route",
            "deep-review",
            "--provider",
            "claude",
            "--lens",
            "skills/review/references/adversarial.md",
            "--json",
        )
        self.assertEqual(2, rejected.returncode)
        error = json.loads(rejected.stdout)["error"]
        self.assertEqual("MODEL_ROUTE_INVALID", error["code"])
        self.assertIn("pass --boundary too", error["message"])


if __name__ == "__main__":
    unittest.main()
