from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import tomllib
import unittest

from aitk.build import (
    AGENTS,
    compare_build,
    expected_agents,
    expected_build,
    write_build,
)
from aitk.routing_manifest import validate_selector_ownership
from aitk.routing_resolver import resolve_route


ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        (root / "config").mkdir()
        (root / "config/CLAUDE.md").write_text(
            "@{{TOOLKIT_DIR}}/rules/universal.md\n"
        )

    def test_expected_build_resolves_portable_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)

            expected = expected_build(root)

            self.assertEqual(
                f"@{root}/rules/universal.md\n",
                expected[Path("build/config/CLAUDE.md")],
            )
            self.assertEqual({Path("build/config/CLAUDE.md")}, set(expected))

    def test_write_then_check_is_clean_and_source_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)

            result = write_build(root)

            self.assertEqual(1, result.written)
            self.assertEqual([], compare_build(root))
            (root / "config/CLAUDE.md").write_text("changed\n")
            self.assertEqual(
                ["different: build/config/CLAUDE.md"], compare_build(root)
            )

    def test_build_preserves_legacy_command_output_as_rollback_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)
            stale = root / "build/commands/stale.md"
            stale.parent.mkdir(parents=True)
            stale.write_text("old\n")

            result = write_build(root)

            self.assertEqual([], result.removed)
            self.assertEqual("old\n", stale.read_text())
            self.assertEqual([], compare_build(root))

    def test_manifest_validation_precedes_config_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)
            (root / "interfaces").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "skills/workflows/references/hello.md").write_text("# Hello\n")
            workflow = {
                "name": "hello",
                "summary": "Hello",
                "arguments": "",
                "rules": [],
                "triggers": ["hello"],
                "execution_class": "single_run",
            }
            (root / "interfaces/workflows.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skill": "workflows",
                        "reference_root": "skills/workflows/references",
                        "workflows": [workflow, dict(workflow)],
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "duplicate workflow name"):
                write_build(root)

            self.assertFalse((root / "build").exists())

    def test_optional_extension_is_validated_without_generating_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)
            (root / "interfaces").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "extensions/pgm/interfaces").mkdir(parents=True)
            (root / "extensions/pgm/skills/pgm/references").mkdir(parents=True)
            (root / "skills/workflows/references/hello.md").write_text("# Hello\n")
            (root / "extensions/pgm/skills/pgm/references/report.md").write_text(
                "# Report\n"
            )
            (root / "interfaces/workflows.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skill": "workflows",
                        "reference_root": "skills/workflows/references",
                        "workflows": [
                            {
                                "name": "hello",
                                "summary": "Hello",
                                "arguments": "",
                                "rules": [],
                                "triggers": ["hello"],
                                "execution_class": "single_run",
                            }
                        ],
                    }
                )
            )
            (root / "extensions/pgm/interfaces/workflows.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skill": "pgm",
                        "reference_root": "extensions/pgm/skills/pgm/references",
                        "workflows": [
                            {
                                "name": "report",
                                "summary": "Create report",
                                "arguments": "[team]",
                                "rules": [],
                                "triggers": ["create report"],
                                "execution_class": "single_run",
                            }
                        ],
                    }
                )
            )

            result = write_build(root, include_pgm=True)

            self.assertEqual(1, result.written)
            self.assertFalse((root / "commands").exists())
            self.assertFalse((root / "extensions/pgm/commands").exists())
            self.assertFalse((root / "build/commands").exists())
            self.assertEqual([], compare_build(root, include_pgm=True))

    def test_generated_output_rejects_symlink_ancestors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            self.make_repo(root)
            (root / "build").mkdir()
            (root / "build/config").symlink_to(outside, target_is_directory=True)
            sentinel = outside / "sentinel"
            sentinel.write_text("safe\n")

            with self.assertRaisesRegex(ValueError, "symlink ancestor"):
                write_build(root)

            self.assertEqual("safe\n", sentinel.read_text())
            self.assertFalse((outside / "CLAUDE.md").exists())


class GeneratedAgentTests(unittest.TestCase):
    """The native agent roster is build output of its contracts (N12, D16, D17)."""

    def copy_repo(self, temporary: str) -> Path:
        root = Path(temporary) / "repo"
        shutil.copytree(
            ROOT, root, ignore=shutil.ignore_patterns(".git", "build", "__pycache__")
        )
        return root

    def test_tracked_agents_equal_the_build(self) -> None:
        expected = expected_agents(ROOT)
        names = {spec.name for spec in AGENTS} | {"aitk-tester"}
        self.assertEqual(
            {Path(f"agents/claude/{name}.md") for name in names}
            | {Path(f"agents/codex/{name}.toml") for name in names},
            set(expected),
        )
        for relative, content in expected.items():
            with self.subTest(path=relative.as_posix()):
                self.assertEqual(content, (ROOT / relative).read_text())

    def test_each_agent_pins_its_route_model_and_effort(self) -> None:
        routes = {spec.name: spec.route for spec in AGENTS} | {"aitk-tester": "implementation"}
        for name, route in routes.items():
            claude = resolve_route(ROOT, route, "claude")
            codex = resolve_route(ROOT, route, "codex")
            with self.subTest(agent=name):
                text = (ROOT / f"agents/claude/{name}.md").read_text()
                frontmatter = text.split("---\n")[1]
                self.assertIn(f"\nmodel: {claude.family}\n", frontmatter)
                self.assertIn(f"\neffort: {claude.effort}\n", frontmatter)
                tools = re.search(r"^tools: (.*)$", frontmatter, re.MULTILINE)
                self.assertIsNotNone(tools)
                for tool in tools.group(1).split(", "):
                    self.assertRegex(tool, r"^[A-Z][A-Za-z]+$", "agent tools take bare names")
                agent = tomllib.loads((ROOT / f"agents/codex/{name}.toml").read_text())
                self.assertEqual(codex.selector, agent["model"])
                self.assertEqual(codex.effort, agent["model_reasoning_effort"])
                self.assertIn(agent["sandbox_mode"], {"read-only", "workspace-write"})

    def test_generated_bodies_carry_the_routed_contract_list(self) -> None:
        for spec in AGENTS:
            route = resolve_route(ROOT, spec.route, "claude", boundary=spec.boundary)
            claude = (ROOT / f"agents/claude/{spec.name}.md").read_text()
            codex = tomllib.loads((ROOT / f"agents/codex/{spec.name}.toml").read_text())
            self.assertIn("Generated by `bin/aitk build`", claude)
            for contract in route.required_contracts:
                body = (ROOT / contract).read_text()
                if body.startswith("---\n"):
                    body = body.split("---\n", 2)[2]
                with self.subTest(agent=spec.name, contract=contract):
                    self.assertIn(f"Contract: `{contract}`", claude)
                    self.assertIn(body.strip(), claude)
                    self.assertIn(body.strip(), codex["developer_instructions"])
        planner = (ROOT / "agents/claude/aitk-planner.md").read_text()
        self.assertNotIn("maxTurns", planner)
        self.assertNotIn("Summary: <", planner)
        debugger = (ROOT / "agents/claude/aitk-debugger.md").read_text()
        self.assertNotIn("permissionMode", debugger)
        self.assertNotIn("/10", debugger)
        self.assertIn("unmerged branches hold unshipped code", debugger)
        self.assertIn("git show <sha>^:<file>", debugger)
        codex = tomllib.loads((ROOT / "agents/codex/aitk-debugger.toml").read_text())
        self.assertIn("restriction is prose", codex["developer_instructions"])

    def test_source_edits_are_build_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_repo(temporary)
            write_build(root)
            self.assertEqual([], compare_build(root))
            rca = root / "agents/specialists/rca.md"
            rca.write_text(rca.read_text() + "\nOne more rule.\n")
            tester = root / "agents/claude/aitk-tester.md"
            tester.write_text(tester.read_text().replace("\nmodel: sonnet\n", "\nmodel: opus\n"))
            self.assertEqual(
                [
                    "different: agents/claude/aitk-debugger.md",
                    "different: agents/claude/aitk-tester.md",
                    "different: agents/codex/aitk-debugger.toml",
                ],
                compare_build(root),
            )
            write_build(root)
            self.assertEqual([], compare_build(root))
            self.assertIn("\nmodel: sonnet\n", tester.read_text())

    def test_a_codex_pin_is_allowed_only_as_the_build_renders_it(self) -> None:
        """A generated TOML may carry the current selector; nothing else may.

        A hand edit is build drift, which `doctor` and `check` report; a stale or
        foreign selector, or a pin in a file the build did not write, is a
        selector leak.
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_repo(temporary)
            write_build(root)
            payload = json.loads((root / "interfaces/model-routing.json").read_text())
            self.assertEqual([], validate_selector_ownership(root, payload))
            planner = root / "agents/codex/aitk-planner.toml"
            generated = planner.read_text()
            planner.write_text(generated + "# hand edit\n")
            self.assertEqual(
                ["different: agents/codex/aitk-planner.toml"], compare_build(root)
            )
            leak = (
                "volatile model selector copied outside manifest: "
                "agents/codex/aitk-planner.toml"
            )
            selector = tomllib.loads(generated)["model"]
            planner.write_text(generated.replace(selector, "gpt-5.9-sol"))
            self.assertEqual([leak], validate_selector_ownership(root, payload))
            planner.write_text(generated + f"# also try {selector}\n")
            self.assertEqual([leak], validate_selector_ownership(root, payload))
            planner.write_text(generated.split("\n\n", 1)[1])
            self.assertEqual([leak], validate_selector_ownership(root, payload))

if __name__ == "__main__":
    unittest.main()
