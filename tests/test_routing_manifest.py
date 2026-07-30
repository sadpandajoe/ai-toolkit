"""Loading and validating the manifest, fail-closed.

Every case here is a malformed or drifted declaration that must become a problem
string rather than a traceback or a quiet default: boundary shape, lens menus, the
per-domain lens floor, the dispatch marker inventory, and the exemption list.
"""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import unittest

from aitk.model_routing import (
    ModelRouteError,
    load_model_routing,
    resolve_route,
    validate_dispatch_boundaries,
    validate_model_routing,
)

from routing_fixtures import (
    ROOT,
    RoutingTestCase,
)


class RoutingManifestTests(RoutingTestCase):
    def test_manifest_and_dispatch_inventory_are_valid(self) -> None:
        self.assertEqual([], validate_model_routing(ROOT))

    def test_missing_marker_fails_closed_on_the_dispatch_path(self) -> None:
        # `validate_dispatch_boundaries` catches a missing marker at check time,
        # but `resolve_route` is the dispatch path. Without its own guard the
        # closure silently shrinks to the seeds and still hands back a
        # launchable route, so a worker runs without the contracts it needs.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "rules", root / "rules")
            shutil.copytree(ROOT / "skills", root / "skills")
            shutil.copytree(ROOT / "interfaces", root / "interfaces")
            document = root / "skills/review/references/code-judo.md"
            document.write_text(
                document.read_text().replace(
                    "<!-- aitk-model-route:review.code-judo -->", ""
                )
            )
            with self.assertRaisesRegex(ModelRouteError, "missing route marker"):
                resolve_route(root, "deep-review", "claude", "review.code-judo")

    def test_declared_lens_menu_and_dispatch_prose_must_agree(self) -> None:
        # The menu used to be implicit: whatever the span linked was a lens.
        # Declaring it in the manifest only helps if the two are held together,
        # and each direction of drift fails differently — a manifest-only lens
        # cannot be dispatched, a prose-only lens is silently demoted to a
        # shared dependency and reaches every worker at once. Neither shows up
        # in a passing route resolution.
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            payload = json.loads(manifest.read_text())
            boundary = next(
                item
                for item in payload["dispatch_boundaries"]
                if item["id"] == "review.pr-standard"
            )
            self.assertEqual([], validate_dispatch_boundaries(root, payload))
            lens = "skills/review/references/adversarial.md"

            declared_only = json.loads(manifest.read_text())
            document = root / "skills/review/references/pr-review.md"
            original = document.read_text()
            document.write_text(
                original.replace("  [adversarial.md](adversarial.md),\n", "", 1)
            )
            problems = validate_dispatch_boundaries(root, declared_only)
            self.assertIn(
                f"declared lens is not linked in the dispatch span: "
                f"review.pr-moderate/{lens}",
                problems,
            )
            document.write_text(original)

            prose_only = json.loads(manifest.read_text())
            for item in prose_only["dispatch_boundaries"]:
                if item["id"] == "review.pr-standard":
                    item["lenses"] = [
                        value for value in item["lenses"] if value != lens
                    ]
            problems = validate_dispatch_boundaries(root, prose_only)
            self.assertIn(
                f"reviewer lens linked in the dispatch span but not declared: "
                f"review.pr-standard/{lens}",
                problems,
            )
            # And the menu is what `--lens` resolves against: a lens missing from
            # it is unroutable rather than mis-scoped. The lens floor has to come
            # out too, or the manifest fails to load first and this proves nothing
            # about the resolver -- which is itself the point of the floor.
            prose_only["lens_floors"]["code"] = [
                value for value in prose_only["lens_floors"]["code"] if value != lens
            ]
            manifest.write_text(json.dumps(prose_only))
            with self.assertRaisesRegex(ModelRouteError, "is not named at boundary"):
                resolve_route(root, "deep-review", "claude", boundary["id"], lens=lens)

    def test_a_menu_may_not_quietly_drop_a_floor_lens(self) -> None:
        """Per-boundary, not union-wide.

        The menus are checked for containment against the classifier and for
        completeness across their union. Both stay green when one boundary loses
        a lens its siblings still list: the union is whole, the narrowed menu is
        still a subset, and the lane is simply unreachable in that one workflow.
        The floor is declared once per domain so a single boundary cannot shrink
        below it.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            self.assertEqual([], validate_model_routing(root))
            for identifier, dropped in (
                ("review.pr-standard", "skills/review/references/adversarial.md"),
                ("review.local-primary-lanes", "skills/review/references/deep-quality.md"),
                (
                    "workflows.review-plan-fresh",
                    "skills/plan-review/references/implementation.md",
                ),
            ):
                with self.subTest(boundary=identifier, dropped=dropped):
                    payload = json.loads(pristine)
                    for item in payload["dispatch_boundaries"]:
                        if item["id"] == identifier:
                            item["lenses"] = [
                                lens for lens in item["lenses"] if lens != dropped
                            ]
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(
                        ModelRouteError, f"{identifier} omits .* lens floor entries"
                    ):
                        load_model_routing(root)
            # And a malformed floor is a reported problem rather than a crash or a
            # silently skipped check.
            for floors in (
                {"code": []},
                {"code": ["skills/review/references/nonexistent.md"]},
                {"nonsense": ["skills/review/references/adversarial.md"]},
                {"code": [{"lens": "skills/review/references/adversarial.md"}]},
            ):
                with self.subTest(floors=floors):
                    payload = json.loads(pristine)
                    payload["lens_floors"] = floors
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(ModelRouteError, "invalid lens floor"):
                        load_model_routing(root)
            manifest.write_text(pristine)
            self.assertEqual([], validate_model_routing(root))

    def test_lens_menu_shape_is_tied_to_the_fanout_flag(self) -> None:
        # A menu on a boundary that refuses `--lens` describes a selection
        # nothing can make, and a one-entry menu is a fan-out with nothing to
        # choose between — both are half-finished edits rather than designs.
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            # Each subtest starts from the pristine manifest. Reading back the
            # file the previous subtest corrupted meant subtest N validated N
            # stacked mutations, and any one of them raising satisfied the regex
            # -- so every case after the first proved nothing about its own
            # mutation, and a rule that stopped rejecting it would stay green.
            pristine = manifest.read_text()
            self.assertEqual([], validate_model_routing(root))
            for identifier, mutation in (
                ("review.pr-batch", {"lenses": ["skills/review/SKILL.md"]}),
                ("review.pr-standard", {"lenses": ["skills/review/SKILL.md"]}),
                # One rule per fixture. A single menu of two identical
                # nonexistent paths broke the duplicate rule *and* the existence
                # rule at once, so either one going missing left the case green
                # and neither was independently covered.
                (
                    "review.pr-standard",
                    {
                        "lenses": [
                            "skills/review/nonexistent.md",
                            "skills/review/code-quality.md",
                        ]
                    },
                ),
                (
                    "review.pr-standard",
                    {"lenses": ["skills/review/code-quality.md"] * 2},
                ),
                ("review.pr-standard", {"lenses": []}),
            ):
                with self.subTest(boundary=identifier, mutation=mutation):
                    payload = json.loads(pristine)
                    for item in payload["dispatch_boundaries"]:
                        if item["id"] == identifier:
                            item.update(mutation)
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(
                        ModelRouteError, "invalid dispatch boundary lens menu"
                    ):
                        load_model_routing(root)
            manifest.write_text(pristine)

    def test_malformed_manifest_is_a_stable_route_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            (root / "interfaces/model-routing.json").write_text("{")
            with self.assertRaisesRegex(ModelRouteError, "unavailable or invalid"):
                resolve_route(root, "review", "codex")

    def test_hostile_nested_manifest_values_fail_without_crashing(self) -> None:
        mutations = (
            lambda payload: payload.update({"version": True}),
            lambda payload: payload.update({"dispatch_boundaries": None}),
            lambda payload: next(
                item for item in payload["routes"] if item["name"] == "review"
            )["providers"]["claude"].update({"disallowed_tools": [{}]}),
            lambda payload: payload["dispatch_boundaries"][0].update({"routes": [{}]}),
            lambda payload: payload["dispatch_boundaries"][0].update({"count": True}),
        )
        for mutate in mutations:
            with self.subTest(
                mutation=mutate
            ), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                path = root / "interfaces/model-routing.json"
                payload = json.loads(path.read_text())
                mutate(payload)
                path.write_text(json.dumps(payload))
                self.assertTrue(validate_model_routing(root))

    def test_new_dispatch_requires_an_inventoried_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "skills/review/references/new-dispatch.md"
            path.write_text("# New\n\nSpawn reviewer agents now.\n")
            problems = validate_model_routing(root)
            self.assertTrue(
                any("unmarked model dispatch boundary" in item for item in problems),
                problems,
            )

    def test_mid_sentence_and_extension_dispatches_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            core = root / "skills/review/references/new-mid-sentence.md"
            core.write_text("# New\n\nThe orchestrator spawns reviewer agents now.\n")
            extension = root / "extensions/pgm/skills/pgm/references/new-dispatch.md"
            extension.write_text(
                "# New\n\nSend this work to implementation subagents.\n"
            )
            problems = validate_model_routing(root)
            unmarked = [
                item for item in problems if "unmarked model dispatch boundary" in item
            ]
            self.assertEqual(2, len(unmarked), problems)


if __name__ == "__main__":
    unittest.main()
