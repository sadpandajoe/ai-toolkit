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

JUDO_SUBJECT = re.compile(r"code-judo|judo (?:pass|lane)", re.IGNORECASE)
DISPATCH_VERB = re.compile(
    r"\b(?:dispatch|dispatches|dispatched|run|runs|launch|launches|spawn|spawns)\b",
    re.IGNORECASE,
)


def _judo_dispatch_sentences(content: str) -> list[str]:
    """Sentences that both name the judo lane and tell a caller to run it."""
    flat = re.sub(r"\s+", " ", content)
    return [
        sentence
        for sentence in re.split(r"(?<=[.!?]) ", flat)
        if JUDO_SUBJECT.search(sentence) and DISPATCH_VERB.search(sentence)
    ]


def _markdown_table_rows(block: str) -> list[list[str]]:
    """Split a Markdown table into cell lists, dropping the alignment row."""
    rows = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue
        rows.append(cells)
    return rows


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

    def test_deep_tier_phrase_list_stays_canonical_and_single_owner(self) -> None:
        # The one-word gap between "deep quality" (one cheap lens) and "deep
        # quality review" (whole review at deep tier) is load-bearing, and the
        # phrase list must live in exactly one file so the predicate cannot drift
        # between the classifier and the orchestrators that read it.
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        section = re.search(
            r"^### Deep-tier phrases.*?(?=^#{2,3} )",
            classifier,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section, "classify-diff.md lost its Deep-tier phrases section")
        quoted = re.findall(
            r'"([^"]+)"',
            "\n".join(
                line for line in section.group(0).splitlines() if line.startswith(">")
            ),
        )
        self.assertEqual(
            {"deep review", "deep quality review", "thermonuclear"}, set(quoted)
        )
        # Scan the toolkit's own content roots only — build output and local
        # worktrees under .claude/ are copies, not second owners.
        candidates = [path for path in ROOT.glob("*.md") if path.is_file()]
        for content_root in ("skills", "rules", "config", "docs", "extensions"):
            candidates.extend(
                path
                for path in (ROOT / content_root).glob("**/*.md")
                if path.is_file() and not path.is_symlink()
            )
        owners = [
            str(path.relative_to(ROOT))
            for path in sorted(candidates)
            if "thermonuclear" in path.read_text()
        ]
        self.assertEqual(["skills/review/references/classify-diff.md"], owners)

    def test_classifier_emits_two_independent_deep_lens_fields(self) -> None:
        # Deep-tier escalation picks the route; Code-judo lane decides whether the
        # generative pass runs at all. Orchestrators must key judo dispatch on the
        # lane field, since a `^refactor` title sets it with escalation NO.
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        # The Output section embeds a fenced sample whose own `##` headings must
        # not terminate the match, so anchor the end on the next real section.
        output = re.search(
            r"^## Output\b(.*?)(?=^## Notes\b|\Z)",
            classifier,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(output, "classify-diff.md lost its Output section")
        for field in ("Deep-tier escalation:", "Code-judo lane:"):
            self.assertIn(field, output.group(0))
        # Substring presence proves nothing about the predicate a consumer gates
        # on, so check the sentences that actually dispatch judo: each consumer
        # must gate at least one of them on the lane field, and none may gate on
        # deep-tier escalation, which is a route choice rather than a lane.
        for consumer in (
            "skills/review/SKILL.md",
            "skills/review/references/local-review.md",
            "skills/review/references/pr-review.md",
            "skills/review/references/workflow-review.md",
        ):
            with self.subTest(consumer=consumer):
                dispatches = _judo_dispatch_sentences((ROOT / consumer).read_text())
                self.assertTrue(
                    dispatches, f"{consumer} no longer dispatches the judo lane"
                )
                self.assertTrue(
                    any("Code-judo lane" in sentence for sentence in dispatches),
                    f"{consumer} dispatches judo without gating on the lane field",
                )
                escalation_gated = [
                    sentence
                    for sentence in dispatches
                    if "Deep-tier escalation: YES" in sentence
                    and "Code-judo lane" not in sentence
                ]
                self.assertEqual([], escalation_gated)

    def test_batch_code_judo_suppression_travels_with_the_dispatch(self) -> None:
        # Batch review is the sole exception to "dispatch judo on Code-judo lane:
        # YES". A per-PR worker sees only its payload, so the suppression has to
        # be an explicit dispatch field and the receiving contracts must gate on
        # it — otherwise the umbrella rule and the batch rule contradict.
        suppression = "Batch mode: Code-judo suppressed"
        for contract in (
            "skills/review/references/pr-batch.md",
            "skills/review/references/pr-review.md",
            "skills/review/references/workflow-review.md",
            "skills/review/SKILL.md",
        ):
            with self.subTest(contract=contract):
                self.assertIn(suppression, (ROOT / contract).read_text())
        batch = (ROOT / "skills/review/references/pr-batch.md").read_text()
        dispatch = re.search(r"^## Dispatch.*?(?=^## )", batch, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(dispatch, "pr-batch.md lost its Dispatch section")
        self.assertIn(suppression, dispatch.group(0))
        self.assertIn("suppressed (batch)", dispatch.group(0))
        self.assertIn(
            "suppressed (batch)",
            (ROOT / "skills/workflows/references/review-pr.md").read_text(),
        )
        # The wave block is where a batch survives context_reset, so the state
        # has to be representable there: a proposals column whose sample rows
        # carry the suppressed value, not a prose mention elsewhere in the file.
        wave = re.search(
            r"^## Review-PR Batch Wave N$.*?^Next wave:", batch, re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(wave, "pr-batch.md lost its wave block template")
        rows = _markdown_table_rows(wave.group(0))
        self.assertTrue(rows, "the wave block template lost its table")
        header = [cell.lower() for cell in rows[0]]
        self.assertIn("proposals", header)
        column = header.index("proposals")
        self.assertTrue(len(rows) > 1, "the wave block template lost its sample rows")
        for row in rows[1:]:
            self.assertEqual("suppressed (batch)", row[column])

    def test_code_judo_pins_its_proposals_to_a_worker_result_slot(self) -> None:
        # A routed judo worker returns the same four fields as every other lane,
        # so the lens itself has to say which slot proposals land in. Without the
        # mapping a worker is free to emit them as findings, scoring the one
        # output this lens exists to keep unscored.
        judo = (ROOT / "skills/review/references/code-judo.md").read_text()
        mapping = re.search(
            r"^### Routed result mapping$.*?(?=^## |\Z)",
            judo,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(mapping, "code-judo.md lost its routed result mapping")
        slots = dict(
            re.findall(
                r"^- `(\w+)` — (.*?)(?=^- `|\Z)",
                mapping.group(0),
                re.MULTILINE | re.DOTALL,
            )
        )
        self.assertEqual({"summary", "findings", "verification"}, set(slots))
        self.assertIn("proposal", slots["summary"].lower())
        # A bare "empty", not the "non-empty ... is a contract violation" prose
        # further down the bullet: the slot has to state the required value, so
        # rewording the directive away can't be masked by the rationale.
        self.assertRegex(slots["findings"].lower(), r"(?<!non-)\bempty\b")

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
