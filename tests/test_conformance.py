from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import tempfile
import unittest

from aitk.conformance import route_workflow, validate_contracts
from aitk.workflows import load_workflows


ROOT = Path(__file__).resolve().parents[1]


class ConformanceTests(unittest.TestCase):
    def test_behavior_and_resume_contracts_are_satisfied(self) -> None:
        self.assertEqual([], validate_contracts(ROOT))

    def test_daily_requests_route_deterministically(self) -> None:
        cases = {
            "Please build a feature for bulk editing dashboards": "create-feature",
            "Diagnose and fix this broken behavior": "fix-bug",
            "GitHub Actions failing on my PR": "fix-ci",
            "Address the review comments on PR 42": "address-feedback",
            "Run an adversarial code review": "review-code-adversarial",
            "Review my code before I push": "review-code",
            "Review the technical plan": "review-plan",
            "Review pull request 42": "review-pr",
            "Manually test PR 42 in the browser": "test-pr",
            "Execute the test plan for SQL Lab": "run-test-plan",
            "Babysit PR 42 until CI is green": "watch-pr",
            "Save a checkpoint before I clear context": "checkpoint",
            "Show me the workflow metrics": "metrics",
            "Validate toolkit health": "toolkit-doctor",
            "Improve the existing test suite": "update-tests",
            "Create the first tests for this package": "create-tests",
            "Open a pull request for these changes": "create-pr",
            "Show the current session cost": "show-cost",
            "Check local capacity before the test run": "check-resources",
            "Resume session from saved state": "start",
        }
        for request, expected in cases.items():
            with self.subTest(request=request):
                match = route_workflow(ROOT, request)
                self.assertIsNotNone(match)
                self.assertEqual(expected, match.workflow.name)

    def test_unrelated_small_request_does_not_force_a_workflow(self) -> None:
        self.assertIsNone(route_workflow(ROOT, "What does this function return?"))

    def test_pr_review_comment_requests_use_specific_triggers(self) -> None:
        cases = {
            "Add review comments to pull request 42": (
                "add review comments to pull request"
            ),
            "Post PR review comments on pull request 42": "post pr review comments",
        }
        for request, trigger in cases.items():
            with self.subTest(request=request):
                match = route_workflow(ROOT, request)
                self.assertIsNotNone(match)
                self.assertEqual("review-pr", match.workflow.name)
                self.assertEqual(trigger, match.trigger)

    def test_generic_pr_comment_requests_remain_unrouted(self) -> None:
        for request in (
            "Add comments to pull request 42",
            "Post comments on PR 42",
        ):
            with self.subTest(request=request):
                self.assertIsNone(route_workflow(ROOT, request))

    def test_pr_posting_keeps_severity_labels_internal(self) -> None:
        posting = (
            ROOT / "skills/review/references/pr-posting.md"
        ).read_text()
        normalized_posting = " ".join(posting.split())
        self.assertIn("Severity labels are internal metadata", posting)
        for label in (
            "`[major]`",
            "`[minor]`",
            "`[nitpick]`",
            "`[critical]`",
            "`[nit]`",
        ):
            with self.subTest(label=label):
                self.assertIn(label, posting)
        self.assertIn(
            "Never include scores or confidence anywhere in posted GitHub "
            "review prose",
            normalized_posting,
        )
        self.assertIn(
            "Never include severity labels in inline comments, top-level comments, "
            "or review bodies unless the user explicitly requests labeled comments",
            normalized_posting,
        )
        for review_surface in (
            "inline comments",
            "top-level comments",
            "review bodies",
        ):
            with self.subTest(review_surface=review_surface):
                self.assertIn(review_surface, normalized_posting)
        self.assertIn("explicitly requests labeled comments", posting)

    def test_optional_pgm_requests_route_only_when_enabled(self) -> None:
        request = "Create a current program health report"
        self.assertIsNone(route_workflow(ROOT, request))
        match = route_workflow(ROOT, request, include_pgm=True)
        self.assertIsNotNone(match)
        self.assertEqual("create-status-report", match.workflow.name)
        explicit = route_workflow(ROOT, "$pgm create-velocity-report", include_pgm=True)
        self.assertIsNotNone(explicit)
        self.assertEqual("create-velocity-report", explicit.workflow.name)
        self.assertIsNone(route_workflow(ROOT, "$pgm create-velocity-report"))

    def test_core_workflow_explicit_invocation_uses_manifest_owner(self) -> None:
        match = route_workflow(ROOT, "$workflows fix-bug")
        self.assertIsNotNone(match)
        self.assertEqual("workflows", match.workflow.owner_skill)
        self.assertEqual("fix-bug", match.workflow.name)

    def test_every_declared_trigger_and_explicit_invocation_routes_exactly(
        self,
    ) -> None:
        for workflow in load_workflows(ROOT, include_pgm=True):
            enabled = workflow.owner_skill == "pgm"
            for trigger in workflow.triggers:
                with self.subTest(workflow=workflow.name, trigger=trigger):
                    match = route_workflow(ROOT, trigger, include_pgm=enabled)
                    self.assertIsNotNone(match)
                    self.assertEqual(workflow.name, match.workflow.name)
            explicit = route_workflow(
                ROOT,
                f"${workflow.owner_skill} {workflow.name}",
                include_pgm=enabled,
            )
            self.assertIsNotNone(explicit)
            self.assertEqual(workflow.name, explicit.workflow.name)

    def test_equal_specificity_between_workflows_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(ROOT / "interfaces", root / "interfaces")
            shutil.copytree(ROOT / "extensions", root / "extensions")
            manifest = root / "interfaces/workflows.json"
            payload = json.loads(manifest.read_text())
            payload["workflows"][0]["triggers"] = ["same trigger"]
            payload["workflows"][1]["triggers"] = ["same trigger"]
            manifest.write_text(json.dumps(payload))

            self.assertIsNone(route_workflow(root, "same trigger"))

    def test_canonical_workflows_do_not_embed_provider_primitives(self) -> None:
        forbidden = re.compile(
            r"\b(?:Claude|Codex|Anthropic|OpenAI)\b|"
            r"\b(?:EnterPlanMode|ExitPlanMode|TaskCreate|TaskList|TaskUpdate)\b|"
            r"@\{\{TOOLKIT_DIR\}\}"
        )
        offenders: list[str] = []
        for reference in sorted((ROOT / "skills/workflows/references").glob("*.md")):
            if forbidden.search(reference.read_text()):
                offenders.append(str(reference.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_optional_pgm_workflows_do_not_embed_provider_primitives(self) -> None:
        forbidden = re.compile(
            r"\b(?:Claude|Codex|Anthropic|OpenAI)\b|"
            r"\b(?:EnterPlanMode|ExitPlanMode|TaskCreate|TaskList|TaskUpdate)\b|"
            r"@\{\{TOOLKIT_DIR\}\}"
        )
        offenders = [
            str(reference.relative_to(ROOT))
            for reference in sorted(
                (ROOT / "extensions/pgm/skills/pgm/references").glob("*.md")
            )
            if forbidden.search(reference.read_text())
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
