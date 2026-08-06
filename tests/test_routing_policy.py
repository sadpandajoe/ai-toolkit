"""The routing vocabulary and the invariants that hold it to the rules.

Route matrix, responsibility restrictions, selector ownership, and the guards that
stop a generic worker or a stale document from reintroducing a retired tier.
"""

from __future__ import annotations

import json
import tempfile
import unittest

from aitk.model_routing import (
    ModelRouteError,
    resolve_route,
    validate_model_routing,
)

from routing_fixtures import (
    ROOT,
    MODEL_CATALOG,
    RoutingTestCase,
)


class RoutingPolicyTests(RoutingTestCase):
    def test_route_matrix_enforces_family_effort_and_permissions(self) -> None:
        cases = {
            ("implementation", "codex"): ("sol", "high", "workspace-write"),
            ("review", "claude"): ("opus", "high", "plan"),
            ("deep-review", "claude"): ("fable", "xhigh", "plan"),
            ("rca", "claude"): ("opus", "high", "plan"),
            ("deep-rca", "codex"): ("sol", "xhigh", "read-only"),
            ("operations", "claude"): ("sonnet", "medium", "dontAsk"),
        }
        for (name, provider), expected in cases.items():
            with self.subTest(route=name, provider=provider):
                route = resolve_route(ROOT, name, provider)
                control = route.controls.get("sandbox") or route.controls.get(
                    "permission_mode"
                )
                self.assertEqual(expected, (route.family, route.effort, control))

    def test_fable_is_never_an_automatic_implementation_route(self) -> None:
        with self.assertRaisesRegex(ModelRouteError, "unknown or nonspawnable"):
            resolve_route(ROOT, "frontier-implementation", "claude")
        implementation = resolve_route(ROOT, "implementation", "claude")
        self.assertEqual(
            ("opus", "high"), (implementation.family, implementation.effort)
        )

    def test_responsibility_restrictions_cannot_be_weakened(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "interfaces/model-routing.json"
            payload = json.loads(path.read_text())
            operations = next(
                item for item in payload["routes"] if item["name"] == "operations"
            )
            operations["restrictions"] = ["Do anything requested."]
            path.write_text(json.dumps(payload))
            problems = validate_model_routing(root)
            self.assertTrue(
                any("responsibility restrictions" in item for item in problems),
                problems,
            )

    def test_generic_provider_worker_cannot_bypass_routing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "interfaces/providers.json"
            payload = json.loads(path.read_text())
            payload["providers"]["codex"]["bindings"]["fresh_subagent"] = {
                "mode": "native",
                "document": "config/providers/codex.md",
                "fallback": None,
            }
            path.write_text(json.dumps(payload))
            problems = validate_model_routing(root)
            self.assertTrue(
                any("must use source_linked_model_run" in item for item in problems),
                problems,
            )

    def test_selectors_are_owned_only_by_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            selector = MODEL_CATALOG["codex"]["models"]["sol"]["selector"]
            (root / "rules/leaked-selector.md").write_text(f"Use {selector} here.\n")
            problems = validate_model_routing(root)
            self.assertTrue(
                any("volatile model selector" in item for item in problems), problems
            )

    def test_future_selector_in_yaml_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "skills/review/agents/openai.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('model: "gpt-9.9-sol"\n')
            problems = validate_model_routing(root)
            self.assertTrue(
                any("volatile model selector" in item for item in problems), problems
            )

    def test_cherry_pick_authoritative_prose_cannot_restore_legacy_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            gate = root / "skills/cherry-pick/references/gate.md"
            gate.write_text(gate.read_text() + "\nUse Heavy-tier handling.\n")

            problems = validate_model_routing(root)

            self.assertTrue(
                any("legacy route vocabulary" in item for item in problems), problems
            )


if __name__ == "__main__":
    unittest.main()
