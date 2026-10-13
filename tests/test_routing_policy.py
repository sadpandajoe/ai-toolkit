"""The routing vocabulary and the invariants that hold it to the rules.

The route table is read from the manifest; what stays pinned in policy is each
route's write controls and tool box, and the guard that stops a generic worker
from standing in for independent review.
"""

from __future__ import annotations

import json
import tempfile
import unittest

from aitk.routing_manifest import validate_model_routing
from aitk.routing_policy import ROUTE_CONTROLS, ModelRouteError
from aitk.routing_resolver import resolve_route

from routing_fixtures import (
    ROOT,
    MODEL_CATALOG,
    RoutingTestCase,
)


class RoutingPolicyTests(RoutingTestCase):
    def test_routes_resolve_to_the_manifest_family_effort_and_controls(self) -> None:
        """The route table is data: each route resolves exactly as the manifest says."""
        manifest = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        for item in manifest["routes"]:
            for provider in ("codex", "claude"):
                with self.subTest(route=item["name"], provider=provider):
                    route = resolve_route(ROOT, item["name"], provider)
                    mapping = item["providers"][provider]
                    self.assertEqual(
                        (mapping["model"], item["effort"]), (route.family, route.effort)
                    )
                    self.assertEqual(
                        MODEL_CATALOG[provider]["models"][mapping["model"]]["selector"],
                        route.selector,
                    )
                    control = "sandbox" if provider == "codex" else "permission_mode"
                    self.assertEqual(mapping[control], route.controls[control])

    def test_only_implementation_may_write(self) -> None:
        with self.assertRaisesRegex(ModelRouteError, "unknown or nonspawnable"):
            resolve_route(ROOT, "frontier-implementation", "claude")
        implementation = resolve_route(ROOT, "implementation", "claude")
        self.assertEqual(
            ("Read", "Grep", "Glob", "Edit", "Write"), implementation.tools
        )
        for name in ROUTE_CONTROLS:
            if name == "implementation":
                continue
            with self.subTest(route=name):
                claude = resolve_route(ROOT, name, "claude")
                codex = resolve_route(ROOT, name, "codex")
                self.assertEqual("read-only", codex.controls["sandbox"])
                self.assertIn(claude.controls["permission_mode"], {"plan", "dontAsk"})
                self.assertEqual(
                    ["Write", "Edit", "NotebookEdit"], claude.controls["disallowed_tools"]
                )
                self.assertFalse({"Edit", "Write"} & set(claude.tools))

    def test_a_manifest_edit_cannot_open_write_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "interfaces/model-routing.json"
            pristine = path.read_text()
            for control, value in (
                ("sandbox", "workspace-write"),
                ("permission_mode", "acceptEdits"),
                ("disallowed_tools", []),
            ):
                with self.subTest(control=control):
                    payload = json.loads(pristine)
                    review = next(item for item in payload["routes"] if item["name"] == "review")
                    provider = "codex" if control == "sandbox" else "claude"
                    review["providers"][provider][control] = value
                    path.write_text(json.dumps(payload))
                    self.assertIn(
                        "review: sandbox and permission controls do not match policy",
                        validate_model_routing(root),
                    )

    def test_the_orchestrator_names_a_catalog_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "interfaces/model-routing.json"
            payload = json.loads(path.read_text())
            payload["policy"]["orchestrator"]["claude"] = "haiku"
            path.write_text(json.dumps(payload))
            problems = validate_model_routing(root)
            self.assertTrue(
                any("orchestrator must name a catalog family" in item for item in problems),
                problems,
            )

    def test_generic_provider_worker_cannot_bypass_independent_review(self) -> None:
        # Same-provider workers may be native subagents, but independent review
        # and every routed specialist must cross the pinned transport.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "interfaces/providers.json"
            payload = json.loads(path.read_text())
            payload["providers"]["codex"]["bindings"]["independent_review"] = {
                "mode": "native",
                "fallback": None,
            }
            path.write_text(json.dumps(payload))
            problems = validate_model_routing(root)
            self.assertTrue(
                any("must use source_linked_model_run" in item for item in problems),
                problems,
            )
            payload["providers"]["codex"]["bindings"]["independent_review"] = {
                "mode": "fallback",
                "fallback": "source_linked_model_run",
            }
            payload["providers"]["codex"]["bindings"]["fresh_subagent"] = {
                "mode": "fallback",
                "fallback": "manual_fresh_session",
            }
            path.write_text(json.dumps(payload))
            problems = validate_model_routing(root)
            self.assertTrue(
                any("native or source_linked_model_run" in item for item in problems),
                problems,
            )


if __name__ == "__main__":
    unittest.main()
