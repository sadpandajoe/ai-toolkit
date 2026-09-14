"""One request to one pinned dispatch.

The resolver is where a request is refused rather than downgraded: an unlisted
route, a fan-out without its lens, a lens below its route floor.
"""

from __future__ import annotations

import unittest

from aitk.model_routing import (
    ModelRouteError,
    resolve_route,
)

from routing_fixtures import (
    ROOT,
    RoutingTestCase,
)


class RoutingResolverTests(RoutingTestCase):
    def test_dispatch_boundary_rejects_an_unlisted_route(self) -> None:
        resolved = resolve_route(
            ROOT,
            "deep-review",
            "codex",
            boundary="review.independent",
        )
        self.assertEqual("review.independent", resolved.boundary)
        for contract in (
            "rules/model-assignment.md",
            "rules/specialist-handoff.md",
            "skills/review/SKILL.md",
            "skills/review/references/local-review.md",
            "agents/specialists/reviewer.md",
            "rules/code-review.md",
            "rules/severity.md",
        ):
            self.assertIn(contract, resolved.required_contracts)
        self.assertEqual("code", resolved.lens_domain)
        with self.assertRaisesRegex(ModelRouteError, "not allowed at boundary"):
            resolve_route(
                ROOT,
                "operations",
                "codex",
                boundary="review.independent",
            )
        # The planner lane is planning-only: it never resolves to an
        # implementation or review route, and the planning route is the only one
        # its boundary lists.
        with self.assertRaisesRegex(ModelRouteError, "not allowed at boundary"):
            resolve_route(
                ROOT, "implementation", "claude", boundary="workflows.create-feature-planning"
            )
        planner = resolve_route(
            ROOT, "planning", "claude", boundary="workflows.create-feature-planning"
        )
        self.assertEqual("fable", planner.family)
        self.assertIn("skills/planning/SKILL.md", planner.required_contracts)

    def test_deep_lens_route_boundaries_enforce_tier(self) -> None:
        # Code-judo is pinned to the deep tier: it accepts deep-review, rejects
        # the standard review route, and inlines its own narrow lens contract.
        judo = resolve_route(
            ROOT, "deep-review", "claude", boundary="review.code-judo"
        )
        self.assertEqual("review.code-judo", judo.boundary)
        self.assertEqual(
            (
                "rules/model-assignment.md",
                "rules/specialist-handoff.md",
                "skills/review/SKILL.md",
                "skills/review/references/code-judo.md",
            ),
            tuple(sorted(judo.required_contracts)),
        )
        self.assertTrue(judo.unscored)
        with self.assertRaisesRegex(ModelRouteError, "not allowed at boundary"):
            resolve_route(ROOT, "review", "claude", boundary="review.code-judo")
        # The conditional deep lenses are deep-review only, per lens.
        for lens in (
            "skills/review/references/adversarial.md",
            "skills/review/references/deep-quality.md",
            "skills/plan-review/references/architecture.md",
        ):
            with self.subTest(lens=lens):
                resolved = resolve_route(
                    ROOT, "deep-review", "claude", boundary="review.deep-lenses", lens=lens
                )
                self.assertEqual("fable", resolved.family)
                self.assertIn(lens, resolved.required_contracts)
                with self.assertRaisesRegex(ModelRouteError, "not allowed at boundary"):
                    resolve_route(
                        ROOT, "review", "claude", boundary="review.deep-lenses", lens=lens
                    )

    def test_fanout_boundary_requires_one_named_lens(self) -> None:
        with self.assertRaisesRegex(ModelRouteError, "fans out over reviewer lenses"):
            resolve_route(ROOT, "deep-review", "claude", "review.pr-deep-lenses")
        # A lens the marker never names is not a lane this boundary can launch.
        with self.assertRaisesRegex(ModelRouteError, "is not named at boundary"):
            resolve_route(
                ROOT,
                "deep-review",
                "claude",
                "review.pr-deep-lenses",
                lens="skills/review/references/code-judo.md",
            )
        # The guard runs both ways: a lane that does not fan out refuses --lens.
        with self.assertRaisesRegex(ModelRouteError, "does not fan out"):
            resolve_route(
                ROOT,
                "review",
                "claude",
                "review.pr-batch",
                lens="skills/review/references/pr-review.md",
            )

    def test_plan_validation_is_one_worker_with_the_validator_contract(self) -> None:
        for route in ("review", "deep-review"):
            with self.subTest(route=route):
                resolved = resolve_route(ROOT, route, "codex", boundary="planning.validate")
                self.assertEqual("plan", resolved.lens_domain)
                self.assertIn("agents/specialists/plan-validator.md", resolved.required_contracts)
                self.assertIn("rules/severity.md", resolved.required_contracts)
                # No sibling lens files: the validator carries its own focus.
                self.assertNotIn(
                    "skills/plan-review/references/architecture.md", resolved.required_contracts
                )
        with self.assertRaisesRegex(ModelRouteError, "does not fan out"):
            resolve_route(
                ROOT,
                "review",
                "codex",
                "planning.validate",
                lens="skills/plan-review/references/architecture.md",
            )


if __name__ == "__main__":
    unittest.main()
