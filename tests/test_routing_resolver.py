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
            boundary="review.code-quality-final",
        )
        self.assertEqual("review.code-quality-final", resolved.boundary)
        for contract in (
            "rules/model-assignment.md",
            "skills/review/SKILL.md",
            "skills/review/references/code-quality.md",
            "rules/code-review.md",
            "rules/review-gate.md",
            "rules/stop-rules.md",
            "rules/severity.md",
        ):
            self.assertIn(contract, resolved.required_contracts)
        with self.assertRaisesRegex(ModelRouteError, "not allowed at boundary"):
            resolve_route(
                ROOT,
                "operations",
                "codex",
                boundary="review.code-quality-final",
            )

    def test_deep_lens_route_boundaries_enforce_tier(self) -> None:
        # Code-judo is pinned to the deep tier: it accepts deep-review, rejects
        # the standard review route, and inlines its own narrow lens contract.
        # The closure is asserted exactly — an extra file here is how the
        # generative lane silently reacquires the findings lens's severity rules.
        judo = resolve_route(
            ROOT, "deep-review", "claude", boundary="review.code-judo"
        )
        self.assertEqual("review.code-judo", judo.boundary)
        self.assertEqual(
            (
                "rules/model-assignment.md",
                "rules/stop-rules.md",
                "skills/review/SKILL.md",
                "skills/review/references/code-judo.md",
            ),
            tuple(sorted(judo.required_contracts)),
        )
        # The generative lane is declared unscored, which the runner enforces on
        # the returned result rather than trusting the contract prose.
        self.assertTrue(judo.unscored)
        with self.assertRaisesRegex(ModelRouteError, "not allowed at boundary"):
            resolve_route(ROOT, "review", "claude", boundary="review.code-judo")
        # A moderate PR lane must accept both the standard and the deep route so
        # deep-tier escalation can reroute it without introducing a new binding.
        for responsibility in ("review", "deep-review"):
            with self.subTest(responsibility=responsibility):
                resolved = resolve_route(
                    ROOT,
                    responsibility,
                    "claude",
                    boundary="review.pr-moderate",
                    lens="skills/review/references/code-quality.md",
                )
                self.assertEqual("review.pr-moderate", resolved.boundary)

    def test_fanout_boundary_requires_one_named_lens(self) -> None:
        with self.assertRaisesRegex(ModelRouteError, "fans out over reviewer lenses"):
            resolve_route(ROOT, "review", "claude", "review.pr-standard")
        # A lens the marker never names is not a lane this boundary can launch.
        with self.assertRaisesRegex(ModelRouteError, "is not named at boundary"):
            resolve_route(
                ROOT,
                "review",
                "claude",
                "review.pr-standard",
                lens="skills/review/references/code-judo.md",
            )
        # The guard runs both ways. A boundary that does not fan out has no menu
        # to narrow, so accepting the flag there would silently drop every span
        # dependency it fails to match — the batch lane's classifier, say.
        with self.assertRaisesRegex(ModelRouteError, "does not fan out"):
            resolve_route(
                ROOT,
                "review",
                "claude",
                "review.pr-batch",
                lens="skills/review/references/pr-review.md",
            )


if __name__ == "__main__":
    unittest.main()
