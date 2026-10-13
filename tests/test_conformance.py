from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import tempfile
import unittest

from aitk.conformance import contracts_by_name, route_workflow, validate_contracts
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
        for surface in ("interfaces/model-routing.json", "agents", "aitk/installer.py"):
            self.assertIn(surface, covered)
        layers = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("aitk/routing_*.py")}
        self.assertEqual(set(), layers - covered)

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
        self.assertEqual("fable", routes["planning"]["providers"]["claude"]["model"])
        self.assertEqual("plan", routes["planning"]["providers"]["claude"]["permission_mode"])
        self.assertEqual("opus", routes["review"]["providers"]["claude"]["model"])
        self.assertEqual("fable", routes["deep-review"]["providers"]["claude"]["model"])
        # Both providers have a workhorse and a deep family; the deep routes
        # never run on the workhorse.
        for name in ("deep-review", "deep-rca"):
            self.assertEqual("astra", routes[name]["providers"]["codex"]["model"])
        for name in ("implementation", "planning", "review", "rca", "operations"):
            self.assertEqual("sol", routes[name]["providers"]["codex"]["model"])

    def test_specialist_contracts_are_inlined_for_their_lanes(self) -> None:
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        by_id = {b["id"]: b for b in payload["dispatch_boundaries"]}
        self.assertIn("agents/specialists/rca.md", by_id["debug.rca-specialist"]["contracts"])
        self.assertEqual(["rca", "deep-rca"], by_id["debug.rca-specialist"]["routes"])
        self.assertIn("agents/specialists/plan-validator.md", by_id["planning.validate"]["contracts"])
        self.assertEqual(["review", "deep-review"], by_id["planning.validate"]["routes"])
        self.assertEqual(["planning"], by_id["workflows.create-feature-planning"]["routes"])

    def test_review_lanes_run_through_model_run_with_their_own_contracts(self) -> None:
        """No native reviewer agent; each critic reads only what grades its lane.

        The second family and the same-provider fallback are `model-run`
        lanes (D7). Checklists for other lanes moved into the two contracts
        that use them, and the QA bug table has one home.
        """
        self.assertFalse((ROOT / "agents/claude/aitk-reviewer.md").exists())
        for content_root in ("config", "rules", "skills", "agents"):
            for path in sorted((ROOT / content_root).rglob("*.md")):
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertNotIn("aitk-reviewer", path.read_text())
        self.assertNotIn("aitk-reviewer", (ROOT / "README.md").read_text())
        binding = (ROOT / "config/providers/claude.md").read_text()
        self.assertIn("review.second-family", binding)
        reviewer = (ROOT / "agents/specialists/reviewer.md").read_text()
        validator = (ROOT / "agents/specialists/plan-validator.md").read_text()
        for retired in (
            "plan-review/references/backend.md",
            "plan-review/references/frontend.md",
            "testing/references/review-tests.md",
            "plan-review/references/implementation.md",
            "testing/references/review-testplan.md",
        ):
            self.assertNotIn(retired, reviewer)
            self.assertNotIn(retired, validator)
        rule = " ".join((ROOT / "rules/code-review.md").read_text().split())
        self.assertIn("Each new test fails when the behaviour it covers breaks", rule)
        self.assertIn("No mocks of internal code", rule)
        self.assertIn("Pre-verdict claim check", rule)
        flat_validator = " ".join(validator.split())
        self.assertIn("dependent code may already be deployed", flat_validator)
        self.assertIn("A first failing test is named per slice", flat_validator)
        severity = (ROOT / "rules/severity.md").read_text()
        self.assertNotIn("| high |", severity)
        self.assertIn("skills/qa/references/file-bug.md", severity)
        bug = (ROOT / "skills/qa/references/file-bug.md").read_text()
        self.assertIn("`[major]` =\n`[High]` = high", bug)
        gates = " ".join((ROOT / "rules/gates.md").read_text().split())
        self.assertIn("A refused security or adversarial lens may reroute once", gates)

    def test_the_rca_pass_list_and_record_have_one_home(self) -> None:
        """The parent gate and the specialist grade against the same list.

        The record's observables (reproduced, alternatives) replace a
        confidence number, so neither the gate nor the debugger can pass a
        story on a score.
        """
        rca = (ROOT / "agents/specialists/rca.md").read_text()
        flat = " ".join(rca.split())
        for item in (
            "evidenced, not asserted",
            "## RCA record",
            "Reproduced: yes",
            "Alternatives: ruled out",
            "Fix point:",
            "the regression test is the reproduction",
            "git show <sha>^:<file>",
            "Never invent a root cause",
        ):
            self.assertIn(item, flat)
        self.assertNotIn("/10", rca)
        for path in (
            "skills/debug/references/review-rca.md",
            "skills/debug/references/investigate-change.md",
        ):
            text = (ROOT / path).read_text()
            with self.subTest(path=path):
                self.assertIn("agents/specialists/rca.md", text)
                self.assertNotIn("evidenced, not asserted", text)
                self.assertNotIn("/10", text)
        gate = (ROOT / "skills/debug/references/review-rca.md").read_text()
        self.assertIn("aitk-model-route:debug.rca-specialist", gate)
        self.assertIn("rabbit-hole guardrail", gate)

    def test_planner_returns_the_plan_section_the_parent_writes(self) -> None:
        """One writer for PLAN.md: the planner returns text, the parent pastes it.

        The planner's contract and the two plan shapes it returns are its whole
        handoff, and a decomposition carries its phase table as a fenced block
        the parent records unchanged instead of re-typing it.
        """
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        by_id = {b["id"]: b for b in payload["dispatch_boundaries"]}
        self.assertEqual(
            [
                "agents/specialists/planner.md",
                "skills/planning/references/decompose-work.md",
                "skills/planning/references/plan-implementation.md",
            ],
            by_id["workflows.create-feature-planning"]["contracts"],
        )
        planner = (ROOT / "agents/specialists/planner.md").read_text()
        self.assertIn("read-only", planner)
        for line in ("Status: completed", "Status: blocked", "RECLASSIFY: <"):
            self.assertIn(line, planner)
        for heading in ("## Decomposition", "## Phase: <name>", "phases-json"):
            self.assertIn(heading, planner)
        decompose = (ROOT / "skills/planning/references/decompose-work.md").read_text()
        self.assertIn("```phases-json", decompose)
        self.assertIn("bin/aitk project-state phases --phases-json", decompose)
        plan = (ROOT / "skills/planning/references/plan-implementation.md").read_text()
        self.assertIn("Reclassify the phase first", plan)
        self.assertIn("project-state phase --name <phase> --status active", plan)
        self.assertIn("### Global invariants touched", plan)
        feature = (ROOT / "skills/workflows/references/create-feature.md").read_text()
        self.assertIn("writes the section\n   to `PLAN.md` verbatim", feature)

    def test_single_provider_verifier_changes_family_or_caps_the_finding(self) -> None:
        """A verifier on the family that raised the finding is not a verifier."""
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        verifier = next(b for b in payload["dispatch_boundaries"] if b["id"] == "review.verify-major")
        self.assertIn("deep-review", verifier["routes"], "the verifier has no other-family route to fall to")
        routes = {r["name"]: r for r in payload["routes"]}
        self.assertNotEqual(
            routes["review"]["providers"]["claude"]["model"],
            routes["deep-review"]["providers"]["claude"]["model"],
            "review and deep-review resolve to the same Claude family; the fallback changes nothing",
        )

    def test_delivery_follows_the_contract_graph(self) -> None:
        contracts = json.loads((ROOT / "interfaces/contracts.json").read_text())
        by_name = {c["name"]: c for c in contracts["contracts"]}
        feature_edges = {(e["from"], e["to"]) for e in by_name["create-feature"]["transitions"]}
        self.assertIn(("review", "plan"), feature_edges, "no edge back to plan for the next phase")
        self.assertIn(("review", "implement"), feature_edges, "no edge back to implement for the next wave")
        bug_edges = {(e["from"], e["to"]) for e in by_name["fix-bug"]["transitions"]}
        self.assertIn(("review", "implement"), bug_edges)
        # Verification can refute the diagnosis or the plan, not just the fix,
        # so the graph carries those edges; the review workflows carry the delta
        # pass after a fix; fix-ci can end after diagnosis when every failure is
        # pre-existing and can re-diagnose when the fix did not hold.
        self.assertIn(("verify", "diagnose"), bug_edges)
        self.assertIn(("verify", "plan"), feature_edges)
        for name in ("review-code", "review-code-adversarial"):
            edges = {(e["from"], e["to"]) for e in by_name[name]["transitions"]}
            self.assertIn(("verify", "review"), edges, name)
        ci_edges = {(e["from"], e["to"]) for e in by_name["fix-ci"]["transitions"]}
        self.assertIn(("verify", "diagnose"), ci_edges)
        self.assertIn(("diagnose", "$terminal"), ci_edges)
        # One compact line per contract keeps the file diffable at the contract level.
        contract_lines = [
            line for line in (ROOT / "interfaces/contracts.json").read_text().splitlines()
            if line.startswith("    {")
        ]
        self.assertEqual(len(contracts["contracts"]), len(contract_lines))
        for name in ("create-feature", "fix-bug"):
            self.assertIn("publish-explicit", by_name[name]["authorization"]["gates"])
            self.assertIn("published_pr", {k["key"] for k in by_name[name]["idempotency_keys"]})
        validate = (ROOT / "skills/planning/references/validate-plan.md").read_text()
        self.assertIn("aitk-model-route:planning.validate-second-family", validate)
        self.assertIn("size XL", validate)

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

    def test_test_workflows_never_publish_and_delivery_takes_no_pr(self) -> None:
        """Contract data only: the PR and push procedure is `deliver`'s to test."""
        contracts = contracts_by_name(ROOT)
        for name in ("create-tests", "update-tests"):
            with self.subTest(contract=name):
                serialized = json.dumps(contracts[name])
                self.assertNotIn("publish-explicit", serialized)
                self.assertNotIn("published_pr", serialized)
        workflows = {
            item["name"]: item
            for item in json.loads((ROOT / "interfaces/workflows.json").read_text())["workflows"]
        }
        for name in ("create-feature", "fix-bug", "fix-ci", "create-tests", "update-tests"):
            with self.subTest(arguments=name):
                self.assertIn("[--no-pr]", workflows[name]["arguments"])

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
