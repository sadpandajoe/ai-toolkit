from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import tempfile
import unittest

from aitk.conformance import route_workflow, validate_contracts
from aitk.routing_policy import DOMAIN_SEVERITIES, WORKER_SCHEMA
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

    def test_deep_tier_phrases_stay_canonical_and_single_owner(self) -> None:
        # "deep quality" (one lens) versus "deep quality review" (whole review at
        # deep tier) is a one-word gap the classifier alone owns.
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        for phrase in ('**"deep review"**', '**"deep quality review"**', '**"thermonuclear"**'):
            self.assertIn(phrase, classifier)
        candidates = [path for path in ROOT.glob("*.md") if path.is_file()]
        for content_root in ("skills", "rules", "config", "docs", "extensions", "agents"):
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

    def test_classifier_reports_risk_flags_that_select_deep_lenses(self) -> None:
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        output = re.search(
            r"^## Output\b(.*?)(?=^## Notes\b|\Z)", classifier, re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(output, "classify-diff.md lost its Output section")
        for field in (
            "Security-sensitive:",
            "Architecture change:",
            "Refactor-shaped:",
            "Deep-tier escalation:",
            "Code-judo lane:",
            "Deep lenses:",
        ):
            self.assertIn(field, output.group(0))

    def test_every_classified_deep_lens_is_dispatchable_at_every_fan_out(self) -> None:
        """The classifier's deep-lens table, the code floor, and every code menu agree.

        v2 runs one independent reviewer by default and fans out only over the
        conditional deep lenses. A lens the classifier can name but no menu
        offers is a lane that gets selected and cannot run; a menu entry the
        classifier never names is dead weight in a worker's closure.
        """
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        table = re.search(
            r"^\| Review Domain \| Trigger \| Skill \|.*?(?=\n\n)",
            classifier,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(table, "classify-diff.md lost its Review Domain table")
        triggerable = {
            f"skills/{cells[2].strip('`')}"
            for cells in _markdown_table_rows(table.group(0))
            if cells[0] != "Review Domain"
        }
        for path in sorted(triggerable):
            self.assertTrue((ROOT / path).is_file(), f"classifier names a missing lens: {path}")
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        code_floor = set(payload["lens_floors"]["code"])
        self.assertEqual(triggerable, code_floor)
        fanouts = [b for b in payload["dispatch_boundaries"] if b.get("lenses")]
        self.assertTrue(fanouts, "no deep-lens fan-out boundaries left")
        for boundary in fanouts:
            with self.subTest(boundary=boundary["id"]):
                self.assertEqual("code", boundary["lens_domain"])
                self.assertEqual(["deep-review"], boundary["routes"])
                self.assertEqual(code_floor, set(boundary["lenses"]))
        # Plan validation is one worker with the validator contract inline; it
        # never fans out over plan lenses, so no boundary may declare a plan menu.
        self.assertEqual(
            [],
            [b["id"] for b in fanouts if b.get("lens_domain") == "plan"],
        )
        validate = next(b for b in payload["dispatch_boundaries"] if b["id"] == "planning.validate")
        self.assertEqual("plan", validate["lens_domain"])
        self.assertIn("agents/specialists/plan-validator.md", validate["contracts"])

    def test_deep_review_lenses_carry_the_route_floor_the_rule_promises(self) -> None:
        rule = (ROOT / "rules/model-assignment.md").read_text()
        row = next(
            (line for line in rule.splitlines() if line.startswith("| `deep-review` |")),
            None,
        )
        self.assertIsNotNone(row, "model-assignment.md lost its `deep-review` row")
        when = row.strip().strip("|").split("|")[-1].lower()
        reserved = {word for word in re.findall(r"[a-z]+", when) if len(word) > 3} - {
            "review", "lens", "flagged", "risk", "exceptional", "escalation"
        }
        self.assertIn("architecture", reserved)
        self.assertIn("adversarial", reserved)
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        floors = payload["lens_routes"]
        menus = {lens for b in payload["dispatch_boundaries"] for lens in b.get("lenses", [])}
        for lens in sorted(menus):
            stem = set(Path(lens).stem.replace("-", " ").split())
            with self.subTest(lens=lens):
                if reserved & stem:
                    self.assertEqual(["deep-review"], floors.get(lens))
                else:
                    self.assertNotIn(lens, floors)
        self.assertLessEqual(set(floors), menus)

    def test_security_predicate_covers_agent_capability_surfaces(self) -> None:
        """A change to the toolkit's own routing must classify as security-sensitive."""
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        bullet = re.search(
            r"^   - \*\*Security-sensitive\*\*.*?(?=^   - \*\*)",
            classifier,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(bullet, "classify-diff.md lost its security-sensitive flag")
        body = bullet.group(0)
        for category in ("agent capability configuration", "worker context assembly", "trust-boundary changes"):
            self.assertIn(category, body.lower())
        named = {
            token
            for token in re.findall(r"`([^`]+)`", body)
            if "/" in token or re.search(r"\.[a-z]+$", token)
        }
        self.assertTrue(named)
        covered: set[str] = set()
        for signal in sorted(named):
            matches = (
                sorted(ROOT.glob(signal)) if any(c in signal for c in "*?[") else [ROOT / signal]
            )
            with self.subTest(signal=signal):
                self.assertTrue(matches and all(m.exists() for m in matches), f"{signal} matches no real path")
            covered |= {m.relative_to(ROOT).as_posix().rstrip("/") for m in matches}
        for surface in ("interfaces/model-routing.json", "aitk/model_routing.py", "agents", "aitk/installer.py"):
            self.assertIn(surface, covered)
        layers = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("aitk/routing_*.py")}
        self.assertEqual(set(), layers - covered)

    def test_review_rounds_measure_scope_against_the_recorded_base(self) -> None:
        rule = (ROOT / "rules/code-review.md").read_text()
        self.assertIn("**Scope is upstream of correctness.**", rule)
        self.assertIn("recorded base", rule)
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        record = re.search(r"^## Current Code Review$.*?^### Resume Notes", local, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(record, "local-review.md lost its Review Record template")
        self.assertRegex(record.group(0), re.compile(r"^\*\*Base:\*\*", re.MULTILINE))
        delta = re.search(r"^## Delta Review$.*?(?=^## )", local, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(delta, "local-review.md lost its Delta Review section")
        self.assertIn("recorded base", delta.group(0))

    def test_review_is_one_independent_lane_with_a_bounded_delta(self) -> None:
        """The 10-round review loop is gone: one full review, one delta, then escalate."""
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        local_ids = {
            b["id"] for b in payload["dispatch_boundaries"]
            if b["path"] == "skills/review/references/local-review.md"
        }
        self.assertEqual(
            {
                "review.independent",
                "review.second-family",
                "review.deep-lenses",
                "review.delta",
                "review.verify-major",
            },
            local_ids,
        )
        pr_ids = {
            b["id"] for b in payload["dispatch_boundaries"]
            if b["path"] == "skills/review/references/pr-review.md"
        }
        self.assertEqual(
            {"review.pr-independent", "review.pr-second-family", "review.pr-deep-lenses"}, pr_ids
        )
        for identifier in (
            "review.independent",
            "review.second-family",
            "review.delta",
            "review.pr-independent",
            "review.pr-second-family",
            "review.pr-batch",
        ):
            boundary = next(b for b in payload["dispatch_boundaries"] if b["id"] == identifier)
            with self.subTest(boundary=identifier):
                self.assertIn("agents/specialists/reviewer.md", boundary["contracts"])
                self.assertIn("rules/code-review.md", boundary["contracts"])
                self.assertEqual("code", boundary["lens_domain"])
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        self.assertIn("not a third round", local)
        self.assertIn("never review\ninline", local)
        rule = (ROOT / "rules/code-review.md").read_text()
        for clause in ("One independent review by default", "Validate before fixing", "Delta review, not a second full review", "Bounded rounds"):
            self.assertIn(clause, rule)

    def test_findings_are_validated_before_any_fix(self) -> None:
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        section = re.search(r"^## Validate, Then Fix$.*?(?=^## )", local, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(section, "local-review.md lost its Validate, Then Fix section")
        body = section.group(0)
        self.assertIn("before changing anything", body)
        self.assertIn("rejected with a one-line evidence-based", body)
        handoff = (ROOT / "rules/specialist-handoff.md").read_text()
        self.assertIn("critics, not authorities", handoff)
        reviewer = (ROOT / "agents/specialists/reviewer.md").read_text().replace("\n", " ")
        self.assertIn("parent validates every finding", reviewer)

    def test_batch_worker_is_a_single_reviewer_that_reports_deferred_lenses(self) -> None:
        batch = (ROOT / "skills/review/references/pr-batch.md").read_text()
        span = re.search(
            r"<!-- aitk-model-route:review\.pr-batch -->.*?(?=^## )", batch, re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(span, "pr-batch.md lost its dispatch span")
        self.assertIn("no subagent capability", span.group(0))
        self.assertIn("Batch mode: Code-judo suppressed", span.group(0))
        self.assertIn("Deferred lenses:", batch)
        wave = re.search(r"^## Review-PR Batch Wave N$.*?^Next wave:", batch, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(wave, "pr-batch.md lost its wave block template")
        rows = _markdown_table_rows(wave.group(0))
        header = [cell.lower() for cell in rows[0]]
        self.assertIn("proposals", header)
        self.assertIn("deferred", header)
        for row in rows[1:]:
            self.assertEqual("suppressed (batch)", row[header.index("proposals")])

    def test_lens_finding_templates_lead_with_the_domain_severity(self) -> None:
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        menus: dict[str, set[str]] = {}
        for boundary in payload["dispatch_boundaries"]:
            domain = boundary.get("lens_domain")
            if domain is not None and boundary.get("lenses"):
                menus.setdefault(domain, set()).update(boundary["lenses"])
        self.assertTrue(menus, "no fan-out boundary declares a lens menu")
        checked: set[str] = set()
        for domain, lenses in sorted(menus.items()):
            expected = {tag.strip("[]") for tag in DOMAIN_SEVERITIES[domain]}
            for lens in sorted(lenses):
                text = (ROOT / lens).read_text()
                for tag in re.findall(r"^#{2,4} \[([^\]]+)\]", text, re.MULTILINE):
                    checked.add(lens)
                    with self.subTest(lens=lens, tag=tag):
                        self.assertEqual(expected, {option.strip() for option in tag.split("|")})
        self.assertIn("skills/review/references/adversarial.md", checked)

    def test_missing_test_findings_name_the_assertion_that_locks_them(self) -> None:
        rule = (ROOT / "rules/code-review.md").read_text()
        section = re.search(r"^## Severity$.*?(?=^## )", rule, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(section, "code-review.md lost its Severity section")
        self.assertIn("Name the locking assertion", section.group(0))
        self.assertIn("cannot be named", section.group(0))
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        findings = re.search(r"^### Findings$.*?(?=^###)", local, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(findings)
        rows = _markdown_table_rows(findings.group(0))
        header = [cell.lower() for cell in rows[0]]
        self.assertIn("locking assertion", header)
        self.assertIn("verdict", header)
        self.assertEqual("status", header[-1])

    def test_code_judo_pins_its_proposals_to_a_worker_result_slot(self) -> None:
        judo = (ROOT / "skills/review/references/code-judo.md").read_text()
        mapping = re.search(r"^### Routed result mapping$.*?(?=^## |\Z)", judo, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(mapping, "code-judo.md lost its routed result mapping")
        slots = dict(re.findall(r"^- `(\w+)` — (.*?)(?=^- `|\Z)", mapping.group(0), re.MULTILINE | re.DOTALL))
        self.assertEqual({"summary", "findings", "verification"}, set(slots))
        self.assertIn("proposal", slots["summary"].lower())
        self.assertRegex(slots["findings"].lower(), r"(?<!non-)\bempty\b")

    def test_routes_reflect_the_sonnet_control_plane(self) -> None:
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        self.assertEqual({"codex": "sol", "claude": "sonnet"}, payload["policy"]["orchestrator"])
        routes = {route["name"]: route for route in payload["routes"]}
        self.assertEqual("sonnet", routes["implementation"]["providers"]["claude"]["model"])
        self.assertEqual("opus", routes["planning"]["providers"]["claude"]["model"])
        self.assertEqual("plan", routes["planning"]["providers"]["claude"]["permission_mode"])
        self.assertEqual("opus", routes["review"]["providers"]["claude"]["model"])
        self.assertEqual("fable", routes["deep-review"]["providers"]["claude"]["model"])
        self.assertNotIn("ensembles", payload)
        rule = (ROOT / "rules/model-assignment.md").read_text()
        self.assertIn("Opus plans only COMPLEX work", rule)
        self.assertIn("Prefer the other provider for independent review", rule)

    def test_specialist_contracts_are_inlined_for_their_lanes(self) -> None:
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        by_id = {b["id"]: b for b in payload["dispatch_boundaries"]}
        self.assertIn("agents/specialists/rca.md", by_id["debug.rca-specialist"]["contracts"])
        self.assertEqual(["rca", "deep-rca"], by_id["debug.rca-specialist"]["routes"])
        self.assertIn("agents/specialists/plan-validator.md", by_id["planning.validate"]["contracts"])
        self.assertEqual(["review", "deep-review"], by_id["planning.validate"]["routes"])
        self.assertEqual(["planning"], by_id["workflows.create-feature-planning"]["routes"])
        for contract in ("agents/specialists/reviewer.md", "agents/specialists/rca.md", "agents/specialists/plan-validator.md"):
            text = (ROOT / contract).read_text()
            self.assertIn("read-only", text.lower())
        validator = (ROOT / "agents/specialists/plan-validator.md").read_text()
        self.assertIn("Verdict: APPROVE | CHANGES_REQUIRED | REPLAN", validator)
        rca = (ROOT / "agents/specialists/rca.md").read_text()
        self.assertIn("Verdict: PASS | REVISE | ESCALATE", rca)

    def test_gates_rule_defines_outcomes_and_the_retry_budget(self) -> None:
        gates = (ROOT / "rules/gates.md").read_text()
        for outcome in ("`PASS`", "`RETRY`", "`ESCALATE`", "`RECLASSIFY`", "`USER_DECISION`", "`BLOCKED`"):
            self.assertIn(outcome, gates)
        self.assertIn("one initial attempt plus one informed retry", gates)
        self.assertIn("never becomes `PASS` from code inspection alone", gates)
        loop = (ROOT / "skills/verification-loop/SKILL.md").read_text()
        self.assertIn("Never a third quiet attempt", loop)
        self.assertIn("rules/gates.md", loop)

    def test_retired_v1_vocabulary_does_not_return(self) -> None:
        retired = re.compile(
            r"\bMODERATE\b|rules/(?:review-gate|stop-rules|scoring)\.md|review-ensemble|"
            r"skills/action-gate|iterate-review\.md|8/10 or better|"
            r"checkpoint \+ context_reset|Run context_reset"
        )
        offenders = []
        for content_root in ("rules", "skills", "config", "agents"):
            for path in sorted((ROOT / content_root).rglob("*.md")):
                if path.is_symlink():
                    continue
                for number, line in enumerate(path.read_text().splitlines(), 1):
                    if retired.search(line):
                        offenders.append(f"{path.relative_to(ROOT)}:{number}")
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
