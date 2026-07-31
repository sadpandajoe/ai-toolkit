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
        # The section is a top-level `##` deliberately. As a `###` it fell inside
        # `## Required Context`, whose extent runs to the next `##`, so the route
        # runner read its navigation links as declared contract dependencies and
        # shipped `deep-quality.md` into every closure that contained the
        # classifier. Match `##` only — a `###` here is the defect, not a variant.
        section = re.search(
            r"^## Deep-tier phrases.*?(?=^## )",
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

    def test_every_classified_reviewer_can_actually_be_dispatched(self) -> None:
        """Each lens the classifier can trigger must resolve at every fan-out.

        The classifier's Review Domain table is the contract between "which
        reviewers apply" and "which reviewers can run". Nothing previously tied
        the two together, and they drifted: the adversarial lens was named by
        `--adversarial` and by security-sensitive detection in the PR and local
        procedures, appeared in neither the classifier table nor any fan-out
        menu, and so was unroutable at every review boundary. A test pinning one
        lens to one boundary would not have caught that and will not catch the
        next omission, so assert the whole mapping instead.
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
            self.assertTrue(
                (ROOT / path).is_file(), f"classifier names a missing lens: {path}"
            )
        # Code-judo is the one classified domain that is deliberately not a
        # fan-out lens: it returns unscored proposals and dispatches at its own
        # boundary, which the orchestration references state explicitly.
        own_boundary = {"skills/review/references/code-judo.md"}
        self.assertLessEqual(own_boundary, triggerable)
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        # The classifier grades *diffs*, so it is the universe for `code`
        # fan-outs only. `plan` fan-outs select from the plan-review lens set and
        # are checked against their own universe below; folding the two together
        # would make every plan menu look like it named untriggerable lanes.
        code_fanouts = [
            boundary
            for boundary in payload["dispatch_boundaries"]
            if boundary.get("lenses") and boundary.get("lens_domain") == "code"
        ]
        plan_fanouts = [
            boundary
            for boundary in payload["dispatch_boundaries"]
            if boundary.get("lenses") and boundary.get("lens_domain") == "plan"
        ]
        self.assertTrue(code_fanouts, "no code lens fan-out boundaries left to check")
        self.assertTrue(plan_fanouts, "no plan lens fan-out boundaries left to check")
        fannable = triggerable - own_boundary
        # The floor is declared once per domain and enforced on every boundary of
        # that domain, which is the part per-boundary containment plus a
        # union-wide completeness check could not do: a lens dropped from one
        # menu left the union whole, so the lane was unreachable in exactly one
        # workflow and both assertions stayed green.
        code_floor = set(payload["lens_floors"]["code"])
        plan_floor = set(payload["lens_floors"]["plan"])
        for boundary in code_fanouts:
            with self.subTest(boundary=boundary["id"]):
                menu = set(boundary.get("lenses", []))
                # Containment upward, floor downward. A menu entry the classifier
                # cannot name is a lane no classification can reach; a floor
                # entry the menu omits is a lane a classification reaches and
                # cannot dispatch.
                self.assertLessEqual(menu, fannable)
                self.assertLessEqual(code_floor, menu)
        for boundary in plan_fanouts:
            with self.subTest(boundary=boundary["id"]):
                self.assertLessEqual(plan_floor, set(boundary.get("lenses", [])))
        # Adversarial is pinned in the floor itself, because breadth is not the
        # property that failed. It was named by `--adversarial` and by
        # security-sensitive detection in every review procedure while being
        # absent from every menu, so it has to be dispatchable wherever findings
        # lenses fan out, at any tier — and narrowing that now means editing one
        # declaration whose effect is visible for every boundary at once.
        self.assertIn("skills/review/references/adversarial.md", code_floor)
        # The other direction, and the one the containment check cannot see: a
        # lens the classifier can trigger but no menu offers is a lane that gets
        # selected and then cannot be dispatched. Asserting only containment made
        # this test satisfiable by deleting lenses from every menu at once.
        self.assertEqual(
            set(),
            fannable - code_floor,
            "classifier can trigger code lenses that the lens floor does not require",
        )
        # Plan lenses come from the plan-review skill plus two declared
        # cross-skill lanes. The point of checking is the reverse leak: a
        # code-only lens (deep-quality, code-judo, adversarial) in a plan menu
        # would grade a written plan with a diff lens.
        plan_universe = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "skills/plan-review/references").glob("*.md")
        } | {
            "skills/testing/references/review-testplan.md",
            "skills/pm/references/review-feature-brief.md",
        }
        for boundary in plan_fanouts:
            with self.subTest(boundary=boundary["id"]):
                self.assertLessEqual(set(boundary["lenses"]), plan_universe)
        # Floor completeness for plan, which the per-boundary check above cannot
        # give: without it, dropping a lens from one menu *and* from the floor
        # passes, which is the masking shape one level up. The plan-review skill's
        # own references are the universe that must stay dispatchable everywhere;
        # the two cross-skill lanes are not, since `review-feature-brief` is
        # deliberately offered by the workflow menus and not the planning one.
        own_plan_lenses = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "skills/plan-review/references").glob("*.md")
        }
        self.assertTrue(own_plan_lenses, "the plan-review lens references moved")
        self.assertEqual(
            set(),
            own_plan_lenses - plan_floor,
            "a plan-review lens is not required by the plan lens floor",
        )

    def test_deep_review_lenses_carry_the_route_floor_the_rule_promises(self) -> None:
        """The routing rule's `deep-review` row must be enforced as data.

        `rules/model-assignment.md` states which kinds of review run on
        `deep-review`, and every fan-out boundary lists both routes, so nothing
        stopped an architecture or adversarial dispatch from resolving to
        Opus/high. The manifest's `lens_routes` is where that row becomes
        enforceable, and this test is the join: a lens whose subject matter the
        rule reserves for `deep-review` must carry the floor, and a floor must not
        exist for a lens the rule does not reserve.
        """
        rule = (ROOT / "rules/model-assignment.md").read_text()
        row = re.search(r"^\| `deep-review` \|([^|]+)\|", rule, re.MULTILINE)
        self.assertIsNotNone(row, "model-assignment.md lost its `deep-review` row")
        # "Architecture, security, adversarial, or final cold review" — the words
        # come out of the rule rather than being restated here, so rewording the
        # row to drop a category fails this test instead of quietly widening what
        # may run cheap.
        reserved = {
            word for word in re.findall(r"[a-z]+", row.group(1).lower()) if len(word) > 3
        } - {"final", "review", "or"}
        self.assertIn("architecture", reserved)
        self.assertIn("adversarial", reserved)
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        floors = payload.get("lens_routes", {})
        menus = {
            lens
            for boundary in payload["dispatch_boundaries"]
            for lens in boundary.get("lenses", [])
        }
        self.assertTrue(menus, "no fan-out menus left to check")
        for lens in sorted(menus):
            stem = Path(lens).stem.replace("-", " ").split()
            with self.subTest(lens=lens):
                if reserved & set(stem):
                    self.assertEqual(
                        ["deep-review"],
                        floors.get(lens),
                        f"{lens} is reserved for deep-review by the rule but has "
                        "no matching floor in the manifest",
                    )
                else:
                    # A floor on an unreserved lens is drift the other way: the
                    # manifest would be denying a route the rule allows, with no
                    # written justification anyone can find.
                    self.assertNotIn(lens, floors)
        # No floor may name a path that is not a dispatchable lens, which is how a
        # renamed lens would silently lose its floor while the entry lingered.
        self.assertLessEqual(set(floors), menus)

    def test_security_predicate_covers_agent_capability_surfaces(self) -> None:
        """The classifier must call a change to its own routing security-sensitive.

        The predicate shipped with the standard web-application list, so a diff
        that lets a worker resolve a cheaper model, receive a contract it was not
        granted, or skip a fail-closed check answered `Security-sensitive: NO` on
        every row. The adversarial lens fires on that answer, which means the one
        lens that would have read those changes adversarially was the lens they
        could not trigger. The categories are written as file signals rather than
        prose so this test can self-apply them.
        """
        classifier = (ROOT / "skills/review/references/classify-diff.md").read_text()
        step = re.search(
            r"^4\. \*\*Assess security sensitivity\*\*.*?(?=^## )",
            classifier,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(step, "classify-diff.md lost its security-sensitivity step")
        body = step.group(0)
        for category in (
            "Agent capability configuration",
            "Worker context assembly",
            "Trust boundary changes",
        ):
            with self.subTest(category=category):
                self.assertIn(category, body)
        # Self-application, which is the part a keyword check cannot do: the paths
        # the predicate names must exist, and this toolkit's own dispatch surfaces
        # must be among them. A predicate that named `auth/` and nothing else would
        # pass the category check above while still missing the diff that produced
        # this test.
        # Only the backticked tokens that are *shaped* like paths -- the section
        # also quotes field values like `NO`, and demanding those exist on disk
        # would make the check fail for the wrong reason.
        # Signals come from the predicate's own rows, not from the paragraphs that
        # explain them. The prose below the rows quotes `aitk/routing_*.py` while
        # arguing that the rows must name it -- counting that mention as coverage
        # would let every row signal be deleted while the argument for having them
        # kept the test green.
        rows = "\n".join(re.findall(r"^\s+- .*$", body, re.MULTILINE))
        named = {
            token
            for token in re.findall(r"`([^`]+)`", rows)
            if "/" in token or re.search(r"\.[a-z]+$", token)
        }
        self.assertTrue(named, "the predicate names no concrete file signal")
        for signal in sorted(named):
            with self.subTest(signal=signal):
                # A signal may be a glob -- `aitk/routing_*.py` names a family
                # whose membership changes as the subsystem is split, and pinning
                # six literal paths would rot at the next extraction. It still
                # has to resolve to something that exists, or it is a predicate
                # naming a surface this repo does not have.
                matches = (
                    sorted(ROOT.glob(signal))
                    if any(char in signal for char in "*?[")
                    else [ROOT / signal]
                )
                self.assertTrue(
                    matches and all(path.exists() for path in matches),
                    f"{signal} matches no real path",
                )
        # Expanded, because the facade is not the implementation. `model_routing.py`
        # became a re-export shim and every fail-closed check moved into the
        # `routing_*` layers behind it, so a predicate that named only the shim
        # would have read `NO` on the diff that moved them -- and did.
        covered = {
            path.relative_to(ROOT).as_posix()
            for signal in named
            for path in (
                ROOT.glob(signal) if any(c in signal for c in "*?[") else [ROOT / signal]
            )
        }
        for surface in ("interfaces/model-routing.json", "aitk/model_routing.py"):
            self.assertIn(surface, covered)
        layers = {
            path.relative_to(ROOT).as_posix() for path in ROOT.glob("aitk/routing_*.py")
        }
        self.assertTrue(layers, "the routing layers moved without this test noticing")
        self.assertEqual(
            set(),
            layers - covered,
            "the security predicate misses routing layers that hold the trust boundary",
        )

    def test_review_rounds_measure_scope_against_the_recorded_base(self) -> None:
        """Round 2 must review the same span as round 1, not the fix delta.

        `rules/code-review.md` tells reviewers to drop a finding whose `file:line`
        is unchanged by the change set. Measured against the last fix instead of
        the review's own base, that rule inverts: a defect this review introduced
        and committed in round 1 is "unchanged code" from round 2 onward, so the
        rule meant to keep reviewers honest becomes the reason the review cannot
        report what it created. The base is therefore recorded state, and the
        record template is where that becomes checkable.
        """
        rule = (ROOT / "rules/code-review.md").read_text()
        scope = [
            paragraph
            for paragraph in rule.split("\n- ")
            if paragraph.startswith("**Scope is upstream of correctness.**")
        ]
        self.assertEqual(1, len(scope), "the scope rule is missing or duplicated")
        # The rule must not stop at "in the diff" -- it has to say which diff, or a
        # reviewer applying it literally per round is following it correctly and
        # still going blind to earlier rounds.
        recorded = [
            paragraph
            for paragraph in rule.split("\n- ")
            if "recorded review base" in paragraph or "recorded span" in paragraph
        ]
        self.assertTrue(
            recorded, "code-review.md defines diff scope without pinning the base"
        )
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        # Recorded, not merely mentioned: the base has to survive a context reset,
        # which means a field in the PROJECT.md record and in the emitted gate.
        record = re.search(
            r"^## Current Code Review$.*?^### Resume Notes",
            local,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(record, "local-review.md lost its Review Record template")
        self.assertRegex(record.group(0), re.compile(r"^\*\*Base:\*\*", re.MULTILINE))
        gate = re.search(r"^## Review Gate$.*?^Status:", local, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(gate, "local-review.md lost its Review Gate block")
        self.assertRegex(gate.group(0), re.compile(r"^Base:", re.MULTILINE))
        # And every later round has to say it reuses that base. The iterate section
        # is the one that ran on the fix delta.
        # Stop at the first `###`. The subsections below it (final pass,
        # resolved-state audit) also say "recorded base", so matching to the next
        # `##` would let the re-run itself keep measuring the fix delta while a
        # sibling section satisfied the assertion.
        iterate = re.search(
            r"^## Re-Verify \+ Iterate$.*?(?=^###? )", local, re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(iterate, "local-review.md lost its Re-Verify + Iterate section")
        self.assertIn("recorded base", iterate.group(0))

    def test_the_independent_lane_is_not_narrowed_by_the_primary_scope_filter(
        self,
    ) -> None:
        """A second opinion confined to the primary scope is a second pass.

        The scope mapping handed this lane `working-tree` on `--uncommitted` and
        the primary path filter otherwise, so the one reviewer with an independent
        model and context was pointed at exactly the files the user was already
        iterating on -- and structurally could not report that the problem was in
        a file the filter excluded.
        """
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        section = re.search(
            r"^## Independent Second Opinion.*?(?=^## )",
            local,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section, "local-review.md lost its second-opinion section")
        body = section.group(0)
        # The old mapping is the specific thing that must not come back: a line
        # that sends this lane a narrowed scope because the caller passed a filter.
        narrowing = [
            line
            for line in body.splitlines()
            if re.search(r"`--(?:uncommitted|committed)`.*(?:→|->)", line)
            or re.search(r"(?:→|->)\s*`working-tree`", line)
        ]
        self.assertEqual(
            [], narrowing, "the independent lane still follows the primary scope filter"
        )
        self.assertIn("does not follow the primary filter", body)
        # `working-tree` stays reachable, but only where there is no base to use --
        # otherwise "always branch" is a rule with no defined behavior on a
        # repository that cannot produce one.
        self.assertIn("working-tree", body)
        self.assertIn("no base", body)
        # Divergent scopes have to be visible, or a finding outside the primary
        # scope looks like the reviewer ignored the filter.
        record = re.search(
            r"^## Current Code Review$.*?^### Findings",
            local,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(record, "local-review.md lost its Review Record template")
        self.assertRegex(
            record.group(0),
            re.compile(r"^\*\*Independent scope:\*\*", re.MULTILINE),
        )

    def test_the_resolved_state_audit_is_dispatchable_with_a_wide_closure(self) -> None:
        """The lane that re-reads the findings ledger needs more than one lens.

        Every other lane reads a slice: one lens, one diff. Nothing re-read the
        record to ask whether a finding marked `fixed` was fixed, or whether the
        class it described recurs elsewhere in the branch -- which is how nine
        findings of one shape survived several review rounds. This lane is not a
        lens, so its closure is declared wide on purpose, and that width is the
        property worth pinning: narrowed to a single lens it becomes another
        findings pass.
        """
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        audit = next(
            (
                boundary
                for boundary in payload["dispatch_boundaries"]
                if boundary["id"] == "review.local-resolved-audit"
            ),
            None,
        )
        self.assertIsNotNone(audit, "the resolved-state audit boundary is gone")
        self.assertEqual("skills/review/references/local-review.md", audit["path"])
        # Deep route only. Auditing whether a defect class recurs across a branch
        # is the reasoning `rules/model-assignment.md` reserves for `deep-review`,
        # and a boundary listing both routes is how the cheap one gets picked.
        self.assertEqual(["deep-review"], audit["routes"])
        # Not a fan-out: one worker holding the whole ledger. Fanning this out by
        # lens would give each worker a slice of the ledger, which is the shape it
        # exists to correct.
        self.assertNotIn("lenses", audit)
        for contract in (
            "rules/code-review.md",
            "rules/severity.md",
            "skills/review/references/classify-diff.md",
        ):
            self.assertIn(contract, audit["contracts"])
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        section = re.search(
            r"^### Resolved-State Audit$.*?(?=^## )", local, re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(section, "local-review.md lost its resolved-state audit")
        body = section.group(0)
        self.assertIn("<!-- aitk-model-route:review.local-resolved-audit -->", body)
        # Branch-wide, from the recorded base -- an audit of the fix commits alone
        # cannot answer the recurrence question.
        self.assertIn("recorded base", body)
        # The symmetry cap normally holds a "same problem in file X" finding to
        # `[minor]`. This lane is the documented exception, and saying so here is
        # what stops the cap from silently demoting every recurrence it finds.
        self.assertIn("symmetry", body)
        # Its result must be recordable, or "the audit ran and was clean" is
        # indistinguishable from "the audit never ran".
        self.assertIn("Resolved-state audit:", local)
        # STANDARD tier hands the fan-out off-thread and gets back a list of the
        # steps the main thread still owns. The audit is mandatory on that tier,
        # so a hand-back list without it is the same unreachable-lane shape the
        # lens menus already had: named by the procedure that requires it, absent
        # from the enumeration the caller actually follows.
        handback = re.search(
            r"^5\. Return confirmed.*?(?=^## )",
            (ROOT / "skills/review/references/workflow-review.md").read_text(),
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(handback, "workflow-review.md lost its hand-back step")
        step = handback.group(0)
        self.assertIn("review.local-resolved-audit", step)
        # And conditional on the caller, which is the half a plain `assertIn`
        # cannot see. `workflow-review.md` serves `review-code` *and*
        # `review-pr`, while the audit's contract reads the local Review Record
        # and fix queue that only the local path writes. An unconditional
        # requirement here is not a stricter rule, it is a step whose inputs do
        # not exist on half the callers -- so the qualifier has to precede the
        # boundary id, and the PR path has to say what it does instead.
        qualifier = step.split("review.local-resolved-audit")[0]
        self.assertIn(
            "`review-code`",
            qualifier,
            "the audit is required without naming the path that can satisfy it",
        )
        self.assertIn(
            "`review-pr`", step, "the hand-back never says what the PR path does"
        )

    def test_boundary_return_contracts_are_the_generic_worker_envelope(self) -> None:
        """A dispatch document may not invent its own result shape.

        `run_model` validates every worker result against `WORKER_SCHEMA` with
        `additionalProperties: false`. A boundary document that specifies a
        Markdown hand-back instead is not merely inconsistent — it describes a
        dispatch that fails at the runner on both providers, which is how batch
        PR review shipped non-executable while reading as complete. The same
        document class is also where "the worker launches reviewer lanes" hides,
        and a read-only review route has no subagent capability to launch with.
        """
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        envelope = tuple(WORKER_SCHEMA["required"])
        checked = 0
        for path in sorted({boundary["path"] for boundary in payload["dispatch_boundaries"]}):
            text = (ROOT / path).read_text()
            for section in re.findall(
                r"^\*{0,2}Return contract.*?(?=^#{1,3} )", text, re.MULTILINE | re.DOTALL
            ):
                checked += 1
                with self.subTest(path=path):
                    for field in envelope:
                        self.assertIn(
                            f"`{field}`",
                            section,
                            f"{path} declares a return contract that is not the "
                            "generic worker envelope",
                        )
        self.assertTrue(checked, "no boundary document declares a return contract")
        # The other half of the same finding: the batch worker's payload must say
        # it applies its lenses rather than dispatching them, because the
        # procedure it inlines (`pr-review.md`) says "launch ... in parallel" to
        # whoever reads it, and the worker reads it.
        batch = (ROOT / "skills/review/references/pr-batch.md").read_text()
        span = re.search(
            r"<!-- aitk-model-route:review\.pr-batch -->.*?(?=^## )",
            batch,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(span, "pr-batch.md lost its dispatch span")
        self.assertIn("no subagent capability", span.group(0))

    def test_lens_finding_templates_lead_with_the_domain_severity(self) -> None:
        """A lens may not teach its worker a vocabulary the runner rejects.

        `_domain_problem` rejects a `code` result whose findings carry no
        `[major]`/`[minor]`/`[nitpick]` tag, so a lens whose finding template
        leads with a failure *kind* instead — `### [vulnerability] ...`, which is
        how the adversarial lens shipped — describes a worker that fails at the
        runner while reading as complete. It also cannot dedupe or escalate
        against the other lanes it fans out beside. Written as a sweep over the
        declared menus so a lens added later is covered without editing this
        test.
        """
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
                # Only headings that already lead with a bracketed tag are finding
                # templates. A lens that formats findings some other way is not in
                # scope here; a lens that leads with the *wrong* bracket is.
                for tag in re.findall(r"^#{2,4} \[([^\]]+)\]", text, re.MULTILINE):
                    checked.add(lens)
                    with self.subTest(lens=lens, tag=tag):
                        self.assertEqual(
                            expected,
                            {option.strip() for option in tag.split("|")},
                            f"{lens} templates findings as [{tag}], which is not the "
                            f"{domain} severity vocabulary the runner enforces",
                        )
        # Pin the lens the drift was found in, so the sweep cannot pass by finding
        # nothing to sweep.
        self.assertIn("skills/review/references/adversarial.md", checked)

    def test_missing_test_findings_name_the_assertion_that_locks_them(self) -> None:
        """A coverage finding has to say what would fail.

        "Add tests for X" is graded by whether a test file grew, which any
        always-green test satisfies -- and `rules/code-review.md` already calls
        always-green tests noise. Naming the assertion makes the finding checkable
        by someone other than the reviewer who raised it.
        """
        rule = (ROOT / "rules/code-review.md").read_text()
        calibration = re.search(
            r"^### Test Coverage Severity Calibration$.*?(?=^## )",
            rule,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(rule, "code-review.md lost its coverage calibration")
        body = calibration.group(0)
        self.assertIn("Name the locking assertion", body)
        # An unnameable assertion needs a defined outcome. Without one the
        # requirement is unenforceable in the only case that matters -- the
        # reviewer who cannot name one just omits the column.
        self.assertIn("cannot be named", body)
        local = (ROOT / "skills/review/references/local-review.md").read_text()
        findings = re.search(
            r"^### Findings$.*?(?=^###)", local, re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(findings, "local-review.md lost its Findings table")
        rows = _markdown_table_rows(findings.group(0))
        self.assertTrue(rows, "the Findings table template lost its header")
        header = [cell.lower() for cell in rows[0]]
        self.assertIn("locking assertion", header)
        # Status must stay the last column: the template is read positionally by
        # anyone updating a row, and appending the new column after Status would
        # put the assertion where readers look for open/fixed.
        self.assertEqual("status", header[-1])

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
        # The suppression flag is a dispatch field; recording it as
        # `suppressed (batch)` is the main thread's job after the worker returns,
        # so it lives with the posting step rather than inside Dispatch. Both must
        # still exist — a suppression nobody records reads as "judo ran, found
        # nothing" in the wave table.
        post = re.search(r"^## Post.*?(?=^## )", batch, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(post, "pr-batch.md lost its Post section")
        self.assertIn("suppressed (batch)", batch)
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
