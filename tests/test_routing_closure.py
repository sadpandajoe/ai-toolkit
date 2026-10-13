"""What one dispatch actually receives.

The closure is the security-relevant half of routing: a lane that reads a contract
it was not granted, or lacks the one it grades by, fails in ways no passing route
resolution shows. The closure is the lane's declared `contracts` plus the selected
lens, so these tests check the lists themselves: no cross-contamination, the
grading contracts on every grading lane, no parent file in a worker, and files
that exist.
"""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from aitk.routing_manifest import validate_model_routing
from aitk.routing_policy import _safe_path
from aitk.routing_resolver import resolve_route

from routing_fixtures import (
    ROOT,
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

    def test_every_grading_lane_carries_the_code_review_contract(self) -> None:
        """A lane that emits severity-tagged findings must ship its calibration.

        The grading contracts were deliberately pulled out of the review
        umbrella so plan, PM, QA, and scope-leak lanes stop inheriting them.
        That trade is only safe while every lane that *does* grade shipped code
        lists `rules/code-review.md` and `rules/severity.md` in its own
        `contracts`. Nothing else in the suite checks that direction.
        """
        grading_boundaries = {
            # Deep-lens fan-outs: every lens the marker names.
            "review.deep-lenses",
            "review.pr-deep-lenses",
            # Single-lane code review with no fan-out.
            "review.independent",
            "review.second-family",
            "review.delta",
            "review.verify-major",
            "review.pr-independent",
            "review.pr-second-family",
            "review.pr-batch",
            # Code-review lanes owned by another skill, which therefore do not
            # receive the review umbrella.
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
            lenses = _lenses_named_at(boundary) or [None]
            for lens in lenses:
                for route in _routes_for(boundary, lens):
                    with self.subTest(boundary=identifier, route=route, lens=lens):
                        contracts = resolve_route(
                            ROOT, route, "claude", boundary=identifier, lens=lens
                        ).required_contracts
                        self.assertIn("rules/code-review.md", contracts)
                        self.assertIn("rules/severity.md", contracts)

    def test_implementation_closure_is_its_declared_contract_list(self) -> None:
        """An implementer receives its contract, not the parent's procedure.

        The closure used to start from structural seeds -- the routing policy,
        the owning workflow skill and the boundary document -- so every worker
        was handed the orchestration it must never perform. It is now exactly the
        boundary's `contracts`.
        """
        resolved = resolve_route(
            ROOT,
            "implementation",
            "claude",
            boundary="workflows.create-feature-implementation",
        )
        self.assertEqual(
            ("skills/implement-change/SKILL.md", "rules/implementation.md"),
            resolved.required_contracts,
        )
        for contract in (
            "rules/model-assignment.md",
            "rules/specialist-handoff.md",
            "skills/workflows/SKILL.md",
            "skills/workflows/references/create-feature.md",
        ):
            self.assertNotIn(contract, resolved.required_contracts)

    def test_the_independent_reviewer_contract_stays_under_its_word_budget(self) -> None:
        """A cold lane reads its whole contract every run; keep it short.

        The reviewer's handoff is its contract, the code-review rule and the
        severity tags. Checklists for other lanes and the parent's procedure
        are what pushed it past this budget before, so the cap is the check.
        """
        resolved = resolve_route(ROOT, "review", "codex", boundary="review.independent")
        words = sum(
            len((ROOT / contract).read_text().split())
            for contract in resolved.required_contracts
        )
        self.assertLess(words, 2500, resolved.required_contracts)

    def test_every_listed_contract_exists_and_no_worker_gets_parent_files(self) -> None:
        """Each lane's list names real files; parent-only files reach no worker.

        The routing policy and the handoff rules are the parent's. A critic --
        any review-route lane -- is also kept away from the parent's review
        procedure, the gate rules, and any file that sends it to PROJECT.md,
        because each carries the parent's view into a lane whose worth is that
        it has none.
        """
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        routes = {route["name"]: route for route in payload["routes"]}
        parent_only = {"rules/model-assignment.md", "rules/specialist-handoff.md"}
        critic_excluded = parent_only | {
            "skills/review/references/local-review.md",
            "rules/gates.md",
        }
        for boundary in payload["dispatch_boundaries"]:
            with self.subTest(boundary=boundary["id"]):
                self.assertTrue(boundary.get("contracts"), "no contract list")
                for contract in boundary["contracts"]:
                    self.assertTrue((ROOT / contract).is_file(), contract)
            lens = _a_lens_named_at(boundary)
            for route in _routes_for(boundary, lens):
                critic = routes[route]["responsibility"] == "review"
                excluded = critic_excluded if critic else parent_only
                with self.subTest(boundary=boundary["id"], route=route):
                    contracts = resolve_route(
                        ROOT, route, "claude", boundary=boundary["id"], lens=lens
                    ).required_contracts
                    self.assertEqual(set(), excluded & set(contracts))
                    if critic:
                        for contract in contracts:
                            self.assertNotIn(
                                "If PROJECT.md exists", (ROOT / contract).read_text()
                            )

    def test_missing_listed_contract_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            (root / "agents/specialists/finding-verifier.md").unlink()
            problems = validate_model_routing(root)
            self.assertTrue(
                any(
                    "missing required boundary contract: review.verify-major" in item
                    and "agents/specialists/finding-verifier.md" in item
                    for item in problems
                ),
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
