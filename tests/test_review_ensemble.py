from __future__ import annotations

from pathlib import Path
import contextlib
import io
import json
import shutil
import tempfile
import unittest

from aitk.cli import main
from aitk.conformance import route_workflow
from aitk.model_routing import (
    ModelRouteError,
    resolve_ensemble,
    select_verifier,
    select_verifiers,
    validate_model_routing,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "interfaces/model-routing.json").read_text())
CATALOG = MANIFEST["providers"]
CLAUDE = {family: entry["selector"] for family, entry in CATALOG["claude"]["models"].items()}
CODEX = {family: entry["selector"] for family, entry in CATALOG["codex"]["models"].items()}
REVIEW_REFERENCES = ROOT / "skills/review/references"
REVIEW_SKILL = ROOT / "skills/review/SKILL.md"


def roster(resolved) -> set[tuple[str, str, str, str, str]]:
    return {
        (lane.role, lane.provider, lane.route, lane.family, lane.effort)
        for lane in resolved.lens + resolved.cross
    }


class ReviewEnsembleRosterTests(unittest.TestCase):
    def test_manifest_with_ensembles_is_valid(self) -> None:
        self.assertEqual([], validate_model_routing(ROOT))

    def test_deep_ensemble_from_claude_is_fable_plus_a_cold_sol_lane(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "claude")

        self.assertEqual(
            {
                ("lens", "claude", "deep-review", "fable", "xhigh"),
                ("cross", "codex", "deep-review", "sol", "xhigh"),
            },
            roster(resolved),
        )
        self.assertEqual("provider-diverse", resolved.coverage)
        self.assertEqual("full", resolved.status)
        self.assertEqual(
            CLAUDE["fable"], resolved.lens[0].selector
        )
        self.assertEqual(CODEX["sol"], resolved.cross[0].selector)

    def test_deep_ensemble_is_symmetric_when_started_from_codex(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "codex")

        self.assertEqual(
            {
                ("lens", "codex", "deep-review", "sol", "xhigh"),
                ("cross", "claude", "deep-review", "fable", "xhigh"),
            },
            roster(resolved),
        )
        self.assertEqual(("claude", "codex"), resolved.providers)

    def test_security_panel_is_three_votes_spanning_both_providers(self) -> None:
        resolved = resolve_ensemble(ROOT, "security", "claude")
        lanes = resolved.lens + resolved.cross

        self.assertEqual(3, len(lanes))
        self.assertEqual({"claude", "codex"}, {lane.provider for lane in lanes})
        self.assertEqual({"fable", "sol", "opus"}, {lane.family for lane in lanes})
        # The panel is three lanes; verification is two. Different counts by
        # design — a Codex-only cross provider can supply exactly two
        # provider-diverse verifiers for a Claude-raised finding.
        self.assertEqual(2, resolved.verification_lanes)
        self.assertEqual("provider", resolved.verifier_diversity)

    def test_standard_requires_a_cross_provider_lane_at_review_depth(self) -> None:
        resolved = resolve_ensemble(ROOT, "standard", "claude")

        self.assertEqual("required", resolved.cross_provider_policy)
        self.assertEqual(
            [("cross", "codex", "review", "sol", "high")],
            [
                (lane.role, lane.provider, lane.route, lane.family, lane.effort)
                for lane in resolved.cross
            ],
        )
        self.assertEqual(6, resolved.lens_lanes)

    def test_moderate_stays_provider_local_until_the_cross_lane_is_asked_for(self) -> None:
        resolved = resolve_ensemble(ROOT, "moderate", "claude")

        self.assertEqual("optional", resolved.cross_provider_policy)
        self.assertEqual((), resolved.cross)
        self.assertIsNone(resolved.cross_provider)
        self.assertEqual(("claude",), resolved.providers)
        self.assertEqual("family-diverse", resolved.coverage)
        self.assertEqual("full", resolved.status)

    def test_moderate_engages_the_cross_lane_on_explicit_opt_in(self) -> None:
        resolved = resolve_ensemble(ROOT, "moderate", "claude", engage_cross_provider=True)

        self.assertEqual(
            [("cross", "codex", "review", "sol", "high")],
            [
                (lane.role, lane.provider, lane.route, lane.family, lane.effort)
                for lane in resolved.cross
            ],
        )
        self.assertEqual("provider-diverse", resolved.coverage)

    def test_opting_in_cannot_add_a_cross_lane_to_a_forbidden_tier(self) -> None:
        resolved = resolve_ensemble(ROOT, "trivial", "claude", engage_cross_provider=True)

        self.assertEqual((), resolved.cross)
        self.assertEqual(("claude",), resolved.providers)

    def test_required_tiers_ignore_the_opt_in_flag(self) -> None:
        for name in ("standard", "deep", "security"):
            with self.subTest(ensemble=name):
                self.assertEqual(
                    roster(resolve_ensemble(ROOT, name, "claude")),
                    roster(resolve_ensemble(ROOT, name, "claude", engage_cross_provider=True)),
                )

    def test_trivial_is_one_local_lane_with_no_cross_provider(self) -> None:
        resolved = resolve_ensemble(ROOT, "trivial", "claude")

        self.assertEqual(1, resolved.lens_lanes)
        self.assertEqual("forbidden", resolved.cross_provider_policy)
        self.assertEqual((), resolved.cross)
        self.assertEqual("single-family", resolved.coverage)
        self.assertEqual("full", resolved.status)
        self.assertEqual(0, resolved.verification_lanes)

    def test_effort_is_xhigh_only_on_deep_routes(self) -> None:
        for name, expected in (
            ("trivial", {"high"}),
            ("standard", {"high", "xhigh"}),
            ("deep", {"xhigh"}),
            ("security", {"high", "xhigh"}),
        ):
            with self.subTest(ensemble=name):
                resolved = resolve_ensemble(ROOT, name, "claude")
                self.assertEqual(
                    expected,
                    {lane.effort for lane in resolved.lens + resolved.cross},
                )


class CrossProviderFailureTests(unittest.TestCase):
    def test_deep_blocks_when_the_cross_provider_is_unreachable(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "claude", ["claude"])

        self.assertEqual("blocked", resolved.status)
        self.assertEqual("block", resolved.on_degraded)
        self.assertEqual((), resolved.cross)
        self.assertEqual(("codex/deep-review",), resolved.dropped_lanes)
        self.assertIn("BLOCKED", resolved.disclosure)
        self.assertIn("No substitute model was used", resolved.disclosure)

    def test_security_blocks_when_the_cross_provider_is_unreachable(self) -> None:
        resolved = resolve_ensemble(ROOT, "security", "codex", ["codex"])

        self.assertEqual("blocked", resolved.status)
        self.assertNotIn("claude", {lane.provider for lane in resolved.cross})

    def test_standard_degrades_with_an_explicit_disclosure(self) -> None:
        resolved = resolve_ensemble(ROOT, "standard", "claude", ["claude"])

        self.assertEqual("degraded", resolved.status)
        self.assertEqual("family-diverse", resolved.coverage)
        self.assertIn("Model diversity was reduced", resolved.disclosure)
        self.assertIn("not ensemble coverage", resolved.disclosure)

    def test_a_missing_provider_never_yields_a_substitute_lane(self) -> None:
        for name in ("moderate", "standard", "deep", "security"):
            with self.subTest(ensemble=name):
                resolved = resolve_ensemble(ROOT, name, "claude", ["claude"])
                self.assertEqual(
                    {"claude"},
                    {lane.provider for lane in resolved.lens + resolved.cross},
                )
                self.assertIsNone(resolved.cross_provider)

    def test_a_dropped_opt_in_lane_is_disclosed_even_when_the_floor_holds(self) -> None:
        resolved = resolve_ensemble(
            ROOT, "moderate", "claude", ["claude"], engage_cross_provider=True
        )

        self.assertEqual(("codex/review",), resolved.dropped_lanes)
        self.assertEqual("family-diverse", resolved.coverage)
        self.assertEqual("family-diverse", resolved.coverage_floor)
        self.assertEqual("degraded", resolved.status)
        self.assertIn("Model diversity was reduced", resolved.disclosure)
        self.assertIn("codex/review", resolved.disclosure)

    def test_an_unavailable_origin_provider_fails_closed(self) -> None:
        with self.assertRaises(ModelRouteError) as error:
            resolve_ensemble(ROOT, "deep", "claude", ["codex"])

        self.assertEqual("MODEL_ROUTE_UNAVAILABLE", error.exception.code)

    def test_unknown_ensembles_and_providers_are_rejected(self) -> None:
        with self.assertRaises(ModelRouteError):
            resolve_ensemble(ROOT, "thermonuclear", "claude")
        with self.assertRaises(ModelRouteError):
            resolve_ensemble(ROOT, "deep", "gemini")


class VerifierDiversityTests(unittest.TestCase):
    def test_a_deep_finding_is_verified_by_the_other_provider(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "claude")

        verifier = select_verifier(resolved, "claude", "fable")

        self.assertIsNotNone(verifier)
        self.assertEqual("codex", verifier.provider)
        self.assertNotEqual("fable", verifier.family)

    def test_verification_is_symmetric_for_a_cross_lane_finding(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "claude")

        verifier = select_verifier(resolved, "codex", "sol")

        self.assertEqual("claude", verifier.provider)

    def test_standard_verification_only_requires_a_different_family(self) -> None:
        resolved = resolve_ensemble(ROOT, "standard", "claude")

        verifier = select_verifier(resolved, "claude", "opus")

        self.assertNotEqual("opus", verifier.family)

    def test_a_provider_local_tier_verifies_on_its_own_provider(self) -> None:
        resolved = resolve_ensemble(ROOT, "moderate", "claude")

        verifier = select_verifier(resolved, "claude", "opus")

        self.assertEqual(
            {"claude"}, {lane.provider for lane in resolved.verification_pool}
        )
        self.assertEqual("claude", verifier.provider)
        self.assertNotEqual("opus", verifier.family)

    def test_opting_in_widens_the_verification_pool_to_both_providers(self) -> None:
        resolved = resolve_ensemble(ROOT, "moderate", "claude", engage_cross_provider=True)

        self.assertEqual(
            {"claude", "codex"}, {lane.provider for lane in resolved.verification_pool}
        )

    def test_no_verifier_exists_when_diversity_cannot_be_met(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "claude", ["claude"])

        self.assertIsNone(select_verifier(resolved, "claude", "fable"))

    def test_a_roster_that_cannot_verify_itself_is_disclosed(self) -> None:
        resolved = resolve_ensemble(ROOT, "moderate", "codex")

        self.assertEqual(("codex/sol",), resolved.unverifiable_lanes)
        self.assertEqual("degraded", resolved.status)
        self.assertIn("no verifier meets family diversity", resolved.disclosure)
        self.assertIsNone(select_verifier(resolved, "codex", "sol"))

    def test_crossing_providers_makes_a_codex_moderate_verifiable(self) -> None:
        resolved = resolve_ensemble(ROOT, "moderate", "codex", engage_cross_provider=True)

        self.assertEqual((), resolved.unverifiable_lanes)
        self.assertEqual("full", resolved.status)
        self.assertEqual("claude", select_verifier(resolved, "codex", "sol").provider)

    def test_the_security_panel_draws_multiple_distinct_verifiers(self) -> None:
        resolved = resolve_ensemble(ROOT, "security", "claude")

        verifiers = select_verifiers(resolved, "claude", "fable")

        # The tier contracts for exactly what the catalog can supply, so a full
        # security run reaches its verifier count rather than living with a
        # permanent shortfall. Both halves are pinned: raising one without the
        # other reintroduces the gap.
        self.assertEqual(2, len(verifiers))
        self.assertEqual(2, resolved.verification_lanes)
        self.assertEqual({"codex"}, {lane.provider for lane in verifiers})
        self.assertEqual(
            len(verifiers), len({(lane.provider, lane.route) for lane in verifiers})
        )

    def test_one_lane_tiers_never_return_more_than_their_contract(self) -> None:
        for name in ("moderate", "standard", "deep"):
            with self.subTest(ensemble=name):
                resolved = resolve_ensemble(ROOT, name, "claude")
                self.assertLessEqual(
                    len(select_verifiers(resolved, "claude", "opus")),
                    resolved.verification_lanes,
                )

    def test_an_unknown_origin_lane_fails_closed_instead_of_verifying(self) -> None:
        resolved = resolve_ensemble(ROOT, "deep", "claude")

        with self.assertRaises(ModelRouteError):
            select_verifier(resolved, "Claude", "fable")
        with self.assertRaises(ModelRouteError):
            select_verifier(resolved, "claude", "Opus")
        # Both halves are real names, but codex/fable is not a lane any roster
        # can produce — the pair has to be validated, not the two fields.
        with self.assertRaises(ModelRouteError):
            select_verifier(resolved, "codex", "fable")

    def test_trivial_has_no_verification_lane(self) -> None:
        resolved = resolve_ensemble(ROOT, "trivial", "claude")

        self.assertIsNone(select_verifier(resolved, "claude", "opus"))


class EnsembleInvariantTests(unittest.TestCase):
    def fixture(self, temporary: str) -> Path:
        root = Path(temporary) / "repo"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__"),
        )
        return root

    def mutate(self, root: Path, name: str, **changes: object) -> None:
        manifest = root / "interfaces/model-routing.json"
        payload = json.loads(manifest.read_text())
        for entry in payload["ensembles"]:
            if entry["name"] == name:
                entry.update(changes)
        manifest.write_text(json.dumps(payload))

    def test_weakening_a_required_cross_provider_lane_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            self.mutate(root, "deep", cross_provider="optional")

            self.assertNotEqual([], validate_model_routing(root))

    def test_dropping_a_cross_lane_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            self.mutate(root, "deep", cross_lanes=[])

            self.assertNotEqual([], validate_model_routing(root))

    def test_lowering_verifier_diversity_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            self.mutate(root, "deep", verification={"lanes": 1, "diversity": "family"})

            self.assertNotEqual([], validate_model_routing(root))

    def test_a_lens_budget_above_the_fanout_cap_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            self.mutate(root, "standard", lens_lanes=12)

            self.assertNotEqual([], validate_model_routing(root))

    def test_a_lens_budget_too_small_for_its_routes_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            self.mutate(root, "moderate", lens_lanes=1)

            self.assertNotEqual([], validate_model_routing(root))

    def test_widening_a_boundary_route_allowlist_fails_validation(self) -> None:
        for boundary in (
            "review.code-judo",
            "review.adversarial-cross-provider-panel",
            "workflows.adversarial-primary",
            "review.local-independent-capability",
        ):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                manifest = root / "interfaces/model-routing.json"
                payload = json.loads(manifest.read_text())
                for entry in payload["dispatch_boundaries"]:
                    if entry["id"] == boundary and "review" not in entry["routes"]:
                        entry["routes"] = [*entry["routes"], "review"]
                    elif entry["id"] == boundary:
                        entry["routes"] = [*entry["routes"], "operations"]
                manifest.write_text(json.dumps(payload))

                self.assertNotEqual([], validate_model_routing(root))

    def test_removing_an_ensemble_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            manifest = root / "interfaces/model-routing.json"
            payload = json.loads(manifest.read_text())
            payload["ensembles"] = [
                entry for entry in payload["ensembles"] if entry["name"] != "security"
            ]
            manifest.write_text(json.dumps(payload))

            self.assertNotEqual([], validate_model_routing(root))


class EnsembleCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(["--root", str(ROOT), "review-ensemble", *arguments])
        return code, stream.getvalue()

    def test_cli_reports_the_resolved_roster(self) -> None:
        code, output = self.run_cli("deep", "--provider", "claude")

        self.assertEqual(0, code)
        self.assertIn("claude/deep-review", output)
        self.assertIn("codex/deep-review", output)

    def test_cli_emits_machine_readable_provenance(self) -> None:
        code, output = self.run_cli("deep", "--provider", "claude", "--json")
        payload = json.loads(output)

        self.assertEqual(0, code)
        self.assertEqual("full", payload["status"])
        self.assertEqual(
            [("claude", "fable"), ("codex", "sol")],
            [
                (lane["provider"], lane["family"])
                for lane in payload["lens"] + payload["cross"]
            ],
        )

    def test_cli_json_carries_the_unverifiable_roster(self) -> None:
        code, output = self.run_cli("moderate", "--provider", "codex", "--json")
        payload = json.loads(output)

        self.assertEqual(["codex/sol"], payload["unverifiable_lanes"])
        self.assertEqual("degraded", payload["status"])
        # A `continue` tier still exits 0 — the honesty lives in the payload and
        # the disclosure sentence, not in a non-zero status the caller would
        # have to treat as failure.
        self.assertEqual(0, code)
        self.assertIn("no verifier meets family diversity", payload["disclosure"])

    def test_cli_exits_blocked_when_the_cross_provider_is_missing(self) -> None:
        code, output = self.run_cli(
            "deep", "--provider", "claude", "--available", "claude"
        )

        self.assertEqual(4, code)
        self.assertIn("No substitute model was used", output)


class DeepReviewRoutingTests(unittest.TestCase):
    def test_deep_review_pr_routes_to_review_pr_with_the_deep_trigger(self) -> None:
        match = route_workflow(ROOT, "deep review PR 48")

        self.assertIsNotNone(match)
        self.assertEqual("review-pr", match.workflow.name)
        self.assertEqual("deep review pr", match.trigger)

    def test_a_named_pr_wins_over_the_local_deep_code_review_trigger(self) -> None:
        for request in (
            "deep code review of PR 48",
            "deep code review of pull request 48",
        ):
            with self.subTest(request=request):
                self.assertEqual("review-pr", route_workflow(ROOT, request).workflow.name)

    def test_deep_code_review_without_a_pr_stays_local(self) -> None:
        match = route_workflow(ROOT, "deep code review")

        self.assertEqual("review-code", match.workflow.name)

    def test_plain_pr_review_still_routes_without_the_deep_trigger(self) -> None:
        match = route_workflow(ROOT, "review pr 48")

        self.assertEqual("review-pr", match.workflow.name)
        self.assertNotIn("deep", match.trigger)

    def test_review_pr_declares_the_deep_flag(self) -> None:
        manifest = json.loads((ROOT / "interfaces/workflows.json").read_text())
        entry = next(
            item for item in manifest["workflows"] if item["name"] == "review-pr"
        )

        self.assertIn("--deep", entry["arguments"])


class ReviewContractProseTests(unittest.TestCase):
    def test_every_review_gate_reports_model_coverage(self) -> None:
        for name in ("local-review.md", "adversarial-orchestration.md"):
            with self.subTest(reference=name):
                self.assertIn(
                    "Model coverage:", (REVIEW_REFERENCES / name).read_text()
                )

    def test_deep_review_mode_pins_the_tier_and_requires_cross_provider(self) -> None:
        text = (ROOT / "skills/workflows/references/review-pr.md").read_text()

        self.assertIn("--deep", text)
        self.assertIn("pinned to at least STANDARD", text)
        self.assertIn("Cross-provider review is mandatory", text)

    def test_the_cross_provider_lane_is_documented_as_cold_everywhere(self) -> None:
        for reference in (
            REVIEW_REFERENCES / "ensemble.md",
            REVIEW_REFERENCES / "local-review.md",
            REVIEW_REFERENCES / "pr-review.md",
            REVIEW_REFERENCES / "adversarial-orchestration.md",
            ROOT / "skills/workflows/references/review-pr.md",
        ):
            with self.subTest(reference=reference.name):
                text = reference.read_text()
                self.assertIn("never the origin lane", text)

    def test_findings_carry_model_provenance_through_synthesis(self) -> None:
        record = (REVIEW_REFERENCES / "local-review.md").read_text()

        self.assertIn("Raised by", record)
        self.assertIn("Verified by", record)
        self.assertIn("merging", record)

    def test_pr_reviews_keep_model_provenance_off_the_public_surface(self) -> None:
        text = (REVIEW_REFERENCES / "pr-review.md").read_text()

        self.assertIn("raiser and verifier `provider/family`", text)
        self.assertIn("Findings posted to GitHub carry severity and evidence only", text)
        self.assertIn("stays in the local report and PROJECT.md record", text)

    def test_moderate_cross_provider_dispatch_is_documented_as_opt_in(self) -> None:
        self.assertIn(
            "--cross-provider", (REVIEW_REFERENCES / "local-review.md").read_text()
        )
        self.assertIn(
            "opt-in, not automatic", (REVIEW_REFERENCES / "ensemble.md").read_text()
        )

    def test_lens_routes_are_documented_as_mandatory(self) -> None:
        ensemble = (REVIEW_REFERENCES / "ensemble.md").read_text()

        self.assertIn("Lens routes are mandatory, not a menu", ensemble)
        self.assertIn("Mandatory lens routes", ensemble)

    def test_the_lens_table_routes_deep_quality_to_the_deep_route(self) -> None:
        # SKILL.md is the file an orchestrator reads first. If its Route cell
        # still said `review`, the mandatory `deep-review` route would sit empty
        # on a MODERATE run while the resolver reported family-diverse coverage.
        row = next(
            line
            for line in (REVIEW_SKILL).read_text().splitlines()
            if line.startswith("| Deep quality |")
        )

        self.assertTrue(row.rstrip().endswith("| deep-review |"), row)
        self.assertIn("deep-review", row.split("|")[2])

    def test_classify_diff_keeps_every_mandatory_route_covered(self) -> None:
        text = (REVIEW_REFERENCES / "classify-diff.md").read_text()

        self.assertIn("Cover every mandatory lens route", text)
        self.assertIn("never to the point of emptying one", text)

    def test_the_disclosure_is_not_scoped_to_below_floor_runs(self) -> None:
        for reference in (
            REVIEW_REFERENCES / "local-review.md",
            REVIEW_REFERENCES / "pr-review.md",
        ):
            with self.subTest(reference=reference.name):
                self.assertNotIn("disclosure when below floor", reference.read_text())
        self.assertIn(
            "Whenever the resolver\nreturns a disclosure sentence",
            (REVIEW_REFERENCES / "local-review.md").read_text(),
        )

    def test_the_pr_trivial_lane_has_a_declared_dispatch_boundary(self) -> None:
        text = (REVIEW_REFERENCES / "pr-review.md").read_text()
        declared = {entry["id"] for entry in MANIFEST["dispatch_boundaries"]}

        self.assertIn("<!-- aitk-model-route:review.pr-trivial -->", text)
        self.assertIn("review.pr-trivial", declared)

    def test_the_security_verifier_count_is_distinguished_from_the_panel(self) -> None:
        ensemble = (REVIEW_REFERENCES / "ensemble.md").read_text()
        adversarial = (REVIEW_REFERENCES / "adversarial-orchestration.md").read_text()

        self.assertIn("select_verifiers()", ensemble)
        self.assertIn("exactly two provider-diverse verifiers", ensemble)
        self.assertIn("different count from the verifiers", ensemble)
        self.assertIn("record the vote count\nactually achieved", adversarial)

    def test_second_opinion_and_cross_provider_are_named_as_distinct_lanes(self) -> None:
        ensemble = (REVIEW_REFERENCES / "ensemble.md").read_text()
        skill = (ROOT / "skills/review/SKILL.md").read_text()

        self.assertIn("**not** the independent second-opinion capability", ensemble)
        self.assertIn("The two names are not interchangeable", ensemble)
        self.assertIn("They are not the ensemble's cross-provider lane", skill)

    def test_trivial_review_keeps_exactly_one_fresh_reviewer(self) -> None:
        gate = (ROOT / "rules/complexity-gate.md").read_text()

        self.assertIn("implementation path only", gate)
        self.assertIn("still runs exactly one fresh reviewer at TRIVIAL", gate)

    def test_code_quality_separates_read_only_lens_mode_from_the_fix_loop(self) -> None:
        text = (REVIEW_REFERENCES / "code-quality.md").read_text()

        self.assertIn("Lens mode", text)
        self.assertIn("Orchestrator mode", text)
        self.assertIn("read-only review workers", text)

    def test_classify_diff_owns_a_lens_priority_order(self) -> None:
        text = (REVIEW_REFERENCES / "classify-diff.md").read_text()

        self.assertIn("Lens priority order", text)
        self.assertIn("Shed Lanes", text)

    def test_ensemble_reference_is_linked_from_the_review_skill(self) -> None:
        self.assertTrue((REVIEW_REFERENCES / "ensemble.md").exists())
        self.assertIn(
            "references/ensemble.md", (ROOT / "skills/review/SKILL.md").read_text()
        )


if __name__ == "__main__":
    unittest.main()
