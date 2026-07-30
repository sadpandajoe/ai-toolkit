"""What one dispatch actually receives.

The closure is the security-relevant half of routing: a lane that reads a contract
it was not granted, or is starved of the one it was, fails in ways no passing route
resolution shows. These tests pin both directions plus the marker-span scanning the
closure is derived from.
"""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from aitk.model_routing import (
    _marker_span_text,
    _safe_path,
    resolve_route,
    validate_model_routing,
)

from routing_fixtures import (
    ROOT,
    _declared_at,
    _lenses_named_at,
    _a_lens_named_at,
    _routes_for,
    RoutingTestCase,
)


class RoutingClosureTests(RoutingTestCase):
    def test_reviewer_lane_closures_do_not_cross_contaminate(self) -> None:
        # One boundary document declares several lanes, so the closure has to be
        # scoped to each marker: a findings reviewer that inlines the generative
        # judo contract (or a judo worker that inlines severity-graded findings
        # rules) receives two conflicting job descriptions in one prompt.
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        judo_lens = "skills/review/references/code-judo.md"
        checked_judo = False
        for boundary in payload["dispatch_boundaries"]:
            lens = _a_lens_named_at(boundary)
            for route in _routes_for(boundary, lens):
                with self.subTest(boundary=boundary["id"], route=route):
                    contracts = resolve_route(
                        ROOT,
                        route,
                        "claude",
                        boundary=boundary["id"],
                        lens=lens,
                    ).required_contracts
                    if boundary["id"] == "review.code-judo":
                        checked_judo = True
                        self.assertNotIn(
                            "skills/review/references/deep-quality.md", contracts
                        )
                        self.assertNotIn("rules/severity.md", contracts)
                    else:
                        self.assertNotIn(judo_lens, contracts)
        self.assertTrue(checked_judo, "review.code-judo left the boundary manifest")
        # Scoping narrows every lane on a multi-lane document, so pin all of
        # them exactly. Isolation that starves a lane is the same regression in
        # the other direction: the worker silently loses a lens it is told to
        # run, and a negative-membership assertion alone stays green.
        expected = {
            # A fan-out lane carries exactly one lens plus that lens's own
            # grading contracts — never the six siblings the marker also names.
            ("review.local-primary-lanes", "skills/review/references/deep-quality.md"): (
                "rules/code-review.md",
                "rules/model-assignment.md",
                "rules/severity.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/deep-quality.md",
                "skills/review/references/local-review.md",
            ),
            ("review.local-final-pass", "skills/review/references/code-quality.md"): (
                "rules/code-review.md",
                "rules/model-assignment.md",
                "rules/review-gate.md",
                "rules/severity.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/code-quality.md",
                "skills/review/references/local-review.md",
            ),
            # The independent lanes launch an external capability rather than a
            # lens, so their closure stays near the seeds — but both grade
            # findings onto the toolkit scale, so both keep the full grading
            # pair. With no lens in the closure, `local-review.md`'s own
            # Required Context is the only thing supplying it.
            ("review.local-independent-second-opinion", None): (
                "rules/code-review.md",
                "rules/model-assignment.md",
                "rules/severity.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/local-review.md",
            ),
            ("review.local-independent-capability", None): (
                "rules/code-review.md",
                "rules/model-assignment.md",
                "rules/review-gate.md",
                "rules/severity.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/local-review.md",
            ),
            ("review.code-quality-final", None): (
                "rules/code-review.md",
                "rules/model-assignment.md",
                "rules/review-gate.md",
                "rules/severity.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/code-quality.md",
            ),
            # The batch worker is a nested orchestrator, not a lens: it picks its
            # own team, so the classifier must reach it. It gets the classifier
            # and *not* the lenses the classifier can name -- `deep-quality.md`
            # used to arrive here only because the classifier links to it, which
            # handed the orchestrator a lens it never applies itself.
            ("review.pr-batch", None): (
                "rules/code-review.md",
                "rules/model-assignment.md",
                "rules/severity.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/classify-diff.md",
                "skills/review/references/pr-batch.md",
                "skills/review/references/pr-posting.md",
                "skills/review/references/pr-review.md",
            ),
        }
        allowed = {
            boundary["id"]: boundary for boundary in payload["dispatch_boundaries"]
        }
        for (identifier, lens), contracts in expected.items():
            for route in _routes_for(allowed[identifier], lens):
                with self.subTest(boundary=identifier, route=route):
                    resolved = resolve_route(
                        ROOT, route, "claude", boundary=identifier, lens=lens
                    )
                    self.assertEqual(
                        contracts, tuple(sorted(resolved.required_contracts))
                    )

    def test_no_marker_span_is_starved_of_a_contract_it_names(self) -> None:
        # Structural counterpart to the exact closures above: whatever a boundary
        # declares its worker must read has to reach that worker. This holds for
        # boundaries nobody thought to pin, including ones added later.
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        for boundary in payload["dispatch_boundaries"]:
            linked = set(_declared_at(boundary))
            if not linked:
                continue
            menu = set(_lenses_named_at(boundary))
            fanout = bool(boundary.get("lens_fanout", False))
            if not fanout:
                for route in _routes_for(boundary, None):
                    with self.subTest(boundary=boundary["id"], route=route):
                        contracts = set(
                            resolve_route(
                                ROOT, route, "claude", boundary=boundary["id"]
                            ).required_contracts
                        )
                        self.assertEqual(set(), linked - contracts)
                continue
            # A fan-out marker names a menu, and one dispatch takes one item off
            # it. The starvation invariant still has to hold per lens: every lens
            # the span offers must be selectable and must arrive when selected.
            # Asserting only the union would go green on a filter that silently
            # dropped the choice.
            #
            # The document-level and per-lane declarations are the other half.
            # They apply to every lane, so narrowing must leave them alone -- the
            # failure this catches is a filter that treats every seed as a sibling
            # to drop and starves all eight workers of the same contract at once.
            for lens in sorted(menu):
                routes = _routes_for(boundary, lens)
                # A floor that leaves a lens with no route at all is starvation
                # of a different kind: the lane is on the menu and nothing can
                # dispatch it.
                self.assertTrue(routes, f"{lens} has no route left at {boundary['id']}")
                for route in routes:
                    with self.subTest(boundary=boundary["id"], route=route, lens=lens):
                        contracts = set(
                            resolve_route(
                                ROOT,
                                route,
                                "claude",
                                boundary=boundary["id"],
                                lens=lens,
                            ).required_contracts
                        )
                        self.assertIn(lens, contracts)
                        self.assertEqual(set(), (menu - {lens}) & contracts)
                        self.assertEqual(set(), (linked - menu) - contracts)

    def test_marker_span_scopes_dependencies_to_one_dispatch(self) -> None:
        document = "\n".join(
            [
                "# Doc",
                "",
                "<!-- aitk-model-route:demo.first -->",
                "Dispatch reviewers with [alpha.md](alpha.md).",
                "",
                "<!-- aitk-model-route:demo.second -->",
                "Dispatch reviewers with [beta.md](beta.md).",
                "",
                "## Later",
                "",
                "Unscoped prose naming [gamma.md](gamma.md).",
            ]
        )
        first = _marker_span_text(document, "demo.first")
        self.assertIn("alpha.md", first)
        self.assertNotIn("beta.md", first)
        second = _marker_span_text(document, "demo.second")
        self.assertIn("beta.md", second)
        self.assertNotIn("gamma.md", second)
        self.assertNotIn("alpha.md", second)
        self.assertEqual("", _marker_span_text(document, "demo.missing").strip())
        exempted = "\n".join(
            [
                "<!-- aitk-model-route:demo.first -->",
                "Dispatch reviewers with [alpha.md](alpha.md).",
                "<!-- aitk-model-route-exempt:not-a-dispatch -->",
                "Prose naming [beta.md](beta.md).",
            ]
        )
        self.assertNotIn("beta.md", _marker_span_text(exempted, "demo.first"))

    def test_marker_span_ignores_headings_inside_fenced_examples(self) -> None:
        # A span that stops at a fenced heading silently truncates: every
        # contract the marker names after its own illustrative code block
        # vanishes from the closure without any error.
        document = "\n".join(
            [
                "<!-- aitk-model-route:demo.first -->",
                "Dispatch reviewers with [alpha.md](alpha.md). Emit:",
                "",
                "```markdown",
                "## Review Gate",
                "Status: clean",
                "```",
                "",
                "Then also read [beta.md](beta.md).",
                "",
                "## Real Heading",
                "",
                "Unscoped prose naming [gamma.md](gamma.md).",
            ]
        )
        span = _marker_span_text(document, "demo.first")
        self.assertIn("alpha.md", span)
        self.assertIn("beta.md", span)
        self.assertNotIn("gamma.md", span)

    def test_every_grading_lane_carries_the_code_review_contract(self) -> None:
        """A lane that emits severity-tagged findings must ship its calibration.

        The grading contracts were deliberately pulled out of the review
        umbrella so plan, PM, QA, and scope-leak lanes stop inheriting them.
        That trade is only safe while every lane that *does* grade shipped code
        reaches `rules/code-review.md` some other way — through a reviewer lens,
        the boundary's own span, or its document's Required Context. Nothing
        else in the suite checks that direction: the closure assertions above
        would happily record a lane that quietly lost its calibration.
        """
        grading_boundaries = {
            # Lens fan-outs: every lens the marker names, on every route.
            "review.local-primary-lanes",
            "review.local-final-pass",
            "review.pr-moderate",
            "review.pr-standard",
            "review.pr-lenses",
            # Single-lane code review with no fan-out.
            "review.code-quality-final",
            "review.pr-batch",
            # Capability lanes: no lens at all, so the orchestration reference
            # is the only supplier.
            "review.local-independent-second-opinion",
            "review.local-independent-capability",
            # Code-review lanes owned by another skill, which therefore do not
            # receive the review umbrella.
            "workflows.review-code-orchestration",
            "workflows.review-code-fresh",
            "workflows.review-pr-fresh",
            "workflows.adversarial-primary",
            "workflows.adversarial-second-opinion",
        }
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        boundaries = {
            boundary["id"]: boundary for boundary in payload["dispatch_boundaries"]
        }
        self.assertLessEqual(grading_boundaries, set(boundaries))
        for identifier in sorted(grading_boundaries):
            boundary = boundaries[identifier]
            lenses = _lenses_named_at(boundary) if boundary.get("lens_fanout") else [None]
            for lens in lenses:
                for route in _routes_for(boundary, lens):
                    with self.subTest(boundary=identifier, route=route, lens=lens):
                        contracts = resolve_route(
                            ROOT, route, "claude", boundary=identifier, lens=lens
                        ).required_contracts
                        self.assertIn("rules/code-review.md", contracts)
                        self.assertIn("rules/severity.md", contracts)

    def test_boundary_closure_includes_owner_and_responsibility_skills(self) -> None:
        resolved = resolve_route(
            ROOT,
            "implementation",
            "claude",
            boundary="workflows.create-feature-implementation",
        )
        for contract in (
            "rules/model-assignment.md",
            "skills/workflows/SKILL.md",
            "skills/implement-change/SKILL.md",
            "skills/workflows/references/create-feature.md",
            "rules/implementation.md",
            "rules/testing.md",
        ):
            self.assertIn(contract, resolved.required_contracts)

    def test_missing_derived_domain_contract_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            (root / "skills/review/SKILL.md").unlink()
            problems = validate_model_routing(root)
            self.assertTrue(
                any("missing required boundary contract" in item for item in problems),
                problems,
            )

    def test_missing_or_misspelled_transitive_contract_fails_validation(self) -> None:
        for mutation in ("missing", "misspelled"):
            with self.subTest(
                mutation=mutation
            ), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                if mutation == "missing":
                    (root / "rules/implementation.md").unlink()
                else:
                    path = root / "skills/implement-change/SKILL.md"
                    path.write_text(
                        path.read_text().replace(
                            "`rules/implementation.md`",
                            "`rules/implementation-typo.md`",
                        )
                    )
                problems = validate_model_routing(root)
                self.assertTrue(
                    any("missing contract dependency" in item for item in problems),
                    problems,
                )

    def test_contract_paths_reject_symlinked_parent_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rules").mkdir()
            (root / "rules/universal.md").write_text("# Universal\n")
            (root / "linked-rules").symlink_to(root / "rules", target_is_directory=True)

            self.assertIsNone(_safe_path(root, "linked-rules/universal.md"))


if __name__ == "__main__":
    unittest.main()
