"""Loading and validating the manifest, fail-closed.

Every case here is a malformed or drifted declaration that must become a problem
string rather than a traceback or a quiet default: boundary shape, lens menus, the
per-domain lens floor, and the route marker inventory.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import unittest

from aitk.routing_manifest import (
    load_model_routing,
    validate_model_routing,
)
from aitk.routing_policy import ModelRouteError
from aitk.routing_resolver import resolve_route

from routing_fixtures import (
    ROOT,
    RoutingTestCase,
)


class RoutingManifestTests(RoutingTestCase):
    def test_manifest_and_dispatch_inventory_are_valid(self) -> None:
        self.assertEqual([], validate_model_routing(ROOT))

    def test_missing_marker_fails_closed_on_the_dispatch_path(self) -> None:
        # `validate_dispatch_boundaries` catches a missing marker at check time,
        # but `resolve_route` is the dispatch path. Without its own guard it
        # would hand back a launchable route for a lane the prose no longer
        # dispatches.
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

    def test_route_markers_and_boundaries_stay_a_bijection(self) -> None:
        """Each boundary's marker appears once at its path; fenced examples do not count."""
        marker = "<!-- aitk-model-route:review.code-judo -->"
        relative = "skills/review/references/code-judo.md"
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            document = root / relative
            original = document.read_text()
            self.assertEqual(1, original.count(marker))
            cases = {
                "duplicate": (
                    original + f"\n{marker}\n",
                    f"unknown, misplaced, or duplicate route marker: {relative}/review.code-judo",
                ),
                "unknown": (
                    original + "\n<!-- aitk-model-route:review.not-declared -->\n",
                    f"unknown, misplaced, or duplicate route marker: {relative}/review.not-declared",
                ),
                "fenced only": (
                    original.replace(marker, f"```markdown\n{marker}\n```"),
                    f"missing route marker: {relative}/review.code-judo",
                ),
            }
            for name, (text, expected) in cases.items():
                with self.subTest(case=name):
                    document.write_text(text)
                    self.assertIn(expected, validate_model_routing(root))
            document.write_text(original + f"\n```markdown\n{marker}\n```\n")
            self.assertEqual([], validate_model_routing(root))

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
                ("review.pr-deep-lenses", "skills/review/references/adversarial.md"),
                ("review.deep-lenses", "skills/review/references/deep-quality.md"),
                ("review.deep-lenses", "skills/review/references/architecture.md"),
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

    def test_lens_menu_shape_is_checked_and_requires_a_domain(self) -> None:
        # A one-entry menu is a fan-out with nothing to choose between, and a
        # menu without a declared domain leaves a dual-use lens — architecture
        # review, test review — with no signal for which vocabulary to answer in.
        # Both are half-finished edits rather than designs. The menu is now what
        # *makes* a boundary fan out, so a menu-less boundary is simply a lane
        # that applies its own lenses; it is `lens_domain` that it may carry
        # alone, not `lenses`.
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
                ("review.pr-deep-lenses", {"lenses": ["skills/review/SKILL.md"]}),
                # One rule per fixture. A single menu of two identical
                # nonexistent paths broke the duplicate rule *and* the existence
                # rule at once, so either one going missing left the case green
                # and neither was independently covered.
                (
                    "review.pr-deep-lenses",
                    {
                        "lenses": [
                            "skills/review/nonexistent.md",
                            "skills/review/references/deep-quality.md",
                        ]
                    },
                ),
                (
                    "review.pr-deep-lenses",
                    {"lenses": ["skills/review/references/deep-quality.md"] * 2},
                ),
                ("review.pr-deep-lenses", {"lenses": []}),
                # A well-formed menu on a lane that declares no domain.
                (
                    "cherry-pick.validate-scope-leak",
                    {
                        "lenses": [
                            "skills/review/references/adversarial.md",
                            "skills/review/references/deep-quality.md",
                        ]
                    },
                ),
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

    def test_both_lens_floors_are_required_and_pinned_in_policy(self) -> None:
        """Optional floors are floors that delete themselves.

        Both maps returned "no problems" for `null` and for `{}`, and neither
        compared against anything, so every guarantee they encode could be
        removed by deleting the line that states it — an empty map, a dropped
        domain, a deleted lens entry. None of those reads as a behaviour change
        in a diff, and all three validated. The pins in `routing_policy.py` make
        the manifest answerable to a second copy, the way the route table already
        is, and the two comparisons run in opposite directions because the two
        floors fail in opposite directions: a route floor is breached by
        *widening* (the expensive lens becomes cheap), a menu floor by
        *narrowing* (the lane becomes unreachable).
        """
        adversarial = "skills/review/references/adversarial.md"
        cases = (
            (lambda p: p.update(lens_routes={}), "lens_routes must not be empty"),
            (lambda p: p.update(lens_routes=None), "lens_routes must be an object"),
            (
                lambda p: p["lens_routes"].pop(adversarial),
                f"lens route floor for {adversarial} must stay within",
            ),
            (
                lambda p: p["lens_routes"].__setitem__(
                    adversarial, ["review", "deep-review"]
                ),
                f"lens route floor for {adversarial} must stay within",
            ),
            (lambda p: p.update(lens_floors={}), "lens_floors must not be empty"),
            (lambda p: p.update(lens_floors=None), "lens_floors must be an object"),
            (
                lambda p: p["lens_floors"]["code"].remove(adversarial),
                "lens floor for code drops pinned lenses",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            self.assertEqual([], validate_model_routing(root))
            for mutate, expected in cases:
                with self.subTest(expected=expected):
                    payload = json.loads(pristine)
                    mutate(payload)
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(ModelRouteError, re.escape(expected)):
                        load_model_routing(root)
            manifest.write_text(pristine)
            self.assertEqual([], validate_model_routing(root))

    def test_every_route_pins_an_explicit_effort(self) -> None:
        """D16: a route names its effort; a missing, unknown or `max` effort fails."""
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        for route in payload["routes"]:
            with self.subTest(route=route["name"]):
                self.assertIn(route.get("effort"), ("low", "medium", "high", "xhigh"))
        resolved = resolve_route(ROOT, "review", provider="codex", boundary="review.independent")
        self.assertEqual("high", resolved.effort)
        cases = (
            (lambda p: p["routes"][0].pop("effort"), "invalid model route entry"),
            (lambda p: p["routes"][0].update(effort="max"), "effort must be one of"),
            (lambda p: p["routes"][0].update(effort="extreme"), "effort must be one of"),
            (lambda p: p["routes"][0].update(effort="medium"), "invariant mapping mismatch"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            for mutate, expected in cases:
                with self.subTest(expected=expected):
                    mutated = json.loads(pristine)
                    mutate(mutated)
                    manifest.write_text(json.dumps(mutated))
                    with self.assertRaisesRegex(ModelRouteError, re.escape(expected)):
                        load_model_routing(root)
            manifest.write_text(pristine)
            self.assertEqual([], validate_model_routing(root))

    def test_a_menuless_lane_may_not_inline_a_lens_below_its_route_floor(self) -> None:
        """The floor has to cover the lane that applies the lens itself.

        `resolve_route` checks `lens_routes` against the lens named by `--lens`,
        and only a boundary with a menu ever passes one. A lane like
        `review.pr-batch` applies its lenses in its own context and declares them
        as boundary contracts, so it reached the adversarial lens on the cheap
        `review` route without the floor ever being consulted — bypassed not by
        overriding the rule but by taking a path it was never wired into.

        A fan-out boundary must stay exempt: its check-time closure is resolved
        with `lens=None` and deliberately contains the whole menu, so the same
        rule applied there would demand every fan-out satisfy the strictest floor
        on its menu and reject all of them. `workflows.adversarial-primary` is
        the control in the other direction — a menu-less lane that declares the
        adversarial lens on `deep-review`, which is exactly what the floor asks
        for and must keep validating untouched.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            self.assertEqual([], validate_model_routing(root))
            for identifier, lens in (
                ("review.pr-batch", "skills/review/references/adversarial.md"),
                ("review.pr-batch", "skills/review/references/architecture.md"),
            ):
                with self.subTest(boundary=identifier, lens=lens):
                    payload = json.loads(pristine)
                    for item in payload["dispatch_boundaries"]:
                        if item["id"] == identifier:
                            item["contracts"] = [*item["contracts"], lens]
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(
                        ModelRouteError,
                        f"{identifier} inlines {re.escape(lens)} on review",
                    ):
                        load_model_routing(root)
            # Restricting the same lane to `deep-review` makes the identical
            # declaration legal, which is the floor being a floor rather than a
            # ban on the lens.
            payload = json.loads(pristine)
            for item in payload["dispatch_boundaries"]:
                if item["id"] == "review.pr-batch":
                    item["contracts"] = [
                        *item["contracts"],
                        "skills/review/references/adversarial.md",
                    ]
                    item["routes"] = ["deep-review"]
            manifest.write_text(json.dumps(payload))
            self.assertEqual([], validate_model_routing(root))
            manifest.write_text(pristine)

    def test_every_lane_declares_a_well_formed_contract_list(self) -> None:
        """The list is the worker's whole contract, so it must exist and be sane.

        Nothing is inherited from the boundary document any more: a lane with no
        list would dispatch a worker with no instructions, and a list that names
        a parent-only file hands the worker the orchestration it must never do.
        """
        cases = (
            (lambda b: b.pop("contracts"), "invalid dispatch boundary contracts: review.independent"),
            (lambda b: b.update(contracts=[]), "invalid dispatch boundary contracts: review.independent"),
            (
                lambda b: b.update(contracts=["rules/severity.md", "rules/severity.md"]),
                "invalid dispatch boundary contracts: review.independent",
            ),
            (lambda b: b.update(contracts=["rules/severity.txt"]), "invalid dispatch boundary contracts: review.independent"),
            (lambda b: b.update(contracts=["../rules/severity.md"]), "invalid dispatch boundary contracts: review.independent"),
            (lambda b: b.update(contracts=["README.md"]), "invalid dispatch boundary contracts: review.independent"),
            (
                lambda b: b.update(contracts=["rules/no-such-contract.md"]),
                "missing required boundary contract: review.independent: rules/no-such-contract.md",
            ),
            (
                lambda b: b["contracts"].append("rules/model-assignment.md"),
                "review.independent hands its worker a parent-only contract: rules/model-assignment.md",
            ),
            (
                lambda b: b["contracts"].append("rules/gates.md"),
                "review.independent hands its worker a parent-only contract: rules/gates.md",
            ),
            (
                lambda b: b["contracts"].append("skills/review/references/local-review.md"),
                "review.independent hands its worker a parent-only contract: skills/review/references/local-review.md",
            ),
            (
                lambda b: b["contracts"].append("skills/pm/references/project-first.md"),
                "review.independent hands a critic a contract that sends it to PROJECT.md",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            # No shipped contract tells its reader to open PROJECT.md first any
            # more, so the fixture carries one.
            (root / "skills/pm/references/project-first.md").write_text(
                "# Brief review\n\nIf PROJECT.md exists, read it first.\n"
            )
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            self.assertEqual([], validate_model_routing(root))
            for mutate, expected in cases:
                with self.subTest(expected=expected):
                    payload = json.loads(pristine)
                    mutate(
                        next(
                            item
                            for item in payload["dispatch_boundaries"]
                            if item["id"] == "review.independent"
                        )
                    )
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(ModelRouteError, re.escape(expected)):
                        load_model_routing(root)
            # The routing policy is parent-only on an implementation lane too;
            # the gate rules are refused only to critics.
            payload = json.loads(pristine)
            implementation = next(
                item
                for item in payload["dispatch_boundaries"]
                if item["id"] == "workflows.fix-bug-implementation"
            )
            implementation["contracts"].append("rules/specialist-handoff.md")
            manifest.write_text(json.dumps(payload))
            with self.assertRaisesRegex(
                ModelRouteError,
                "fix-bug-implementation hands its worker a parent-only contract",
            ):
                load_model_routing(root)
            implementation["contracts"][-1] = "rules/gates.md"
            manifest.write_text(json.dumps(payload))
            self.assertEqual([], validate_model_routing(root))
            manifest.write_text(pristine)

    def test_route_tool_boxes_are_pinned(self) -> None:
        """A tool box is widened by an edit to the policy, never by the manifest alone."""
        def route(payload: dict[str, object], name: str) -> dict[str, object]:
            return next(item for item in payload["routes"] if item["name"] == name)

        cases = (
            (lambda p: route(p, "review").pop("tools"), "invalid model route entry"),
            (lambda p: route(p, "review")["tools"].append("Edit"), "review: tools do not match policy"),
            (lambda p: route(p, "planning")["tools"].append("Bash(git push *)"), "planning: tools must be"),
            (lambda p: route(p, "rca")["tools"].append("Bash"), "rca: tools do not match policy"),
            (lambda p: route(p, "implementation").update(tools=[]), "implementation: tools must be"),
            (lambda p: route(p, "operations")["tools"].append("Read"), "operations: tools must be"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            for mutate, expected in cases:
                with self.subTest(expected=expected):
                    payload = json.loads(pristine)
                    mutate(payload)
                    manifest.write_text(json.dumps(payload))
                    with self.assertRaisesRegex(ModelRouteError, re.escape(expected)):
                        load_model_routing(root)
            manifest.write_text(pristine)
            self.assertEqual([], validate_model_routing(root))

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
            # A pinned floor is read from the raw payload, so its members are
            # whatever the file says. Comparing it as a set before checking the
            # members are strings crashed on the nested form instead of
            # reporting it.
            lambda payload: payload["lens_routes"].update(
                {"skills/review/references/adversarial.md": [{"route": "deep-review"}]}
            ),
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

    def test_a_route_family_must_exist_in_the_provider_catalog(self) -> None:
        """A route names a model family; one the catalog lacks fails closed."""
        cases = (("codex", "nova"), ("claude", "haiku"), ("codex", "opus"))
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = root / "interfaces/model-routing.json"
            pristine = manifest.read_text()
            for provider, family in cases:
                with self.subTest(provider=provider, family=family):
                    mutated = json.loads(pristine)
                    route = mutated["routes"][0]
                    route["providers"][provider]["model"] = family
                    manifest.write_text(json.dumps(mutated))
                    expected = f"{route['name']}/{provider}: invalid route controls"
                    self.assertIn(expected, validate_model_routing(root))
            manifest.write_text(pristine)
            self.assertEqual([], validate_model_routing(root))

    def test_model_selectors_live_only_in_their_owned_homes(self) -> None:
        """Standing rule 6: a volatile selector is written down in few places.

        The catalog's selectors may appear in the manifest, the pricing table,
        tests, the changelog, the migration notes and the generated Codex agent
        files; anywhere else is a copy that drifts on the next model change.
        """
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        selectors = sorted(
            model["selector"]
            for provider in payload["providers"].values()
            for model in provider["models"].values()
        )
        allowed = re.compile(
            r"(interfaces/model-routing\.json|aitk/pricing\.py|tests/.*|CHANGELOG\.md"
            r"|docs/MIGRATION\.md|agents/codex/[^/]+\.toml)"
        )
        try:
            listing = subprocess.run(
                ["git", "-C", str(ROOT), "ls-files", "-z"],
                capture_output=True,
                check=True,
            ).stdout.decode()
            names = [name for name in listing.split("\0") if name]
        except (OSError, subprocess.CalledProcessError):
            skipped = {".git", "build", "__pycache__"}
            names = [
                path.relative_to(ROOT).as_posix()
                for path in ROOT.rglob("*")
                if path.is_file() and not skipped & set(path.relative_to(ROOT).parts)
            ]
        copies = []
        for name in sorted(names):
            path = ROOT / name
            if allowed.fullmatch(name) or not path.is_file():
                continue
            text = path.read_bytes().decode(errors="replace")
            copies.extend(f"{name}: {item}" for item in selectors if item in text)
        self.assertEqual([], copies)


if __name__ == "__main__":
    unittest.main()
