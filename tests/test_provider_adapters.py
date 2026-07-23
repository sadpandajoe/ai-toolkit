from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
import re
import tempfile
import unittest

from aitk.build import expected_build
from aitk.conformance import workflow_dependency_resources
from aitk.interfaces import load_skill_interfaces
from aitk.workflows import load_workflows, validate_workflows


ROOT = Path(__file__).resolve().parents[1]


class ProviderAdapterTests(unittest.TestCase):
    def test_shared_skill_frontmatter_is_agent_skills_portable(self) -> None:
        offenders: list[str] = []
        skills = list((ROOT / "skills").glob("*/SKILL.md"))
        skills.extend((ROOT / "extensions").glob("*/skills/*/SKILL.md"))
        for skill in sorted(skills):
            match = re.match(r"^---\n(.*?)\n---", skill.read_text(), re.DOTALL)
            self.assertIsNotNone(match, skill)
            keys = {
                line.split(":", 1)[0]
                for line in match.group(1).splitlines()
                if line and not line.startswith((" ", "\t")) and ":" in line
            }
            if keys != {"name", "description"}:
                offenders.append(f"{skill.relative_to(ROOT)}: {sorted(keys)}")
        self.assertEqual([], offenders)

    def test_codex_plugin_manifest_and_hooks_are_self_contained(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual("ai-toolkit", manifest["name"])
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("hooks", manifest)

        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
        commands = [
            hook["command"]
            for groups in hooks["hooks"].values()
            for group in groups
            for hook in group["hooks"]
        ]
        self.assertTrue(all("$PLUGIN_ROOT/" in command for command in commands))
        self.assertTrue(
            any("prevent-project-commit.sh" in command for command in commands)
        )

    def test_provider_hook_adapters_cover_every_productive_hook(self) -> None:
        productive = {
            "prevent-project-commit.sh",
            "pre-push-validate.sh",
            "check-resources.sh",
            "check-plan-drift.sh",
            "agent-setup-edit-reminder.sh",
        }
        codex = (ROOT / "hooks/hooks.json").read_text()
        claude = (ROOT / "install-hooks.sh").read_text()

        for script in productive:
            with self.subTest(script=script):
                self.assertIn(script, codex)
                self.assertIn(script, claude)

        hooks = json.loads(codex)["hooks"]
        posttool_matcher = hooks["PostToolUse"][0]["matcher"]
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"):
            self.assertIn(tool, posttool_matcher)

    def test_internal_codex_skills_disable_implicit_routing(self) -> None:
        internal = (
            "action-gate",
            "debug",
            "feedback",
            "implement-change",
            "metrics-emit",
            "plan-review",
            "planning",
            "pm",
            "pr-watch",
            "preflight",
            "preset-rbac-setup",
            "qa",
            "reflection",
            "reporting",
            "review",
            "shortcut",
            "superset-local",
            "testing",
            "workstreams",
        )
        for name in internal:
            metadata = (ROOT / f"skills/{name}/agents/openai.yaml").read_text()
            self.assertIn("interface:", metadata, name)
            self.assertIn("allow_implicit_invocation: false", metadata, name)

        public = (ROOT / "skills/workflows/agents/openai.yaml").read_text()
        self.assertIn("$workflows", public)

    def test_edit_reminder_accepts_codex_apply_patch_payloads(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "apply_patch",
                "tool_input": {
                    "patch": "*** Update File: /tmp/repo/skills/review/SKILL.md\n"
                },
            }
        )
        result = subprocess.run(
            ["bash", str(ROOT / "hooks/agent-setup-edit-reminder.sh")],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode)
        self.assertIn("systemMessage", result.stdout)
        self.assertIn("shared skills are canonical", result.stdout)

    def test_built_guidance_reaches_each_provider_binding(self) -> None:
        expected = expected_build(ROOT)
        claude = expected[Path("build/config/CLAUDE.md")]
        codex = expected[Path("build/config/AGENTS.md")]
        guidance = json.loads((ROOT / "interfaces/guidance.json").read_text())

        self.assertIn(str(ROOT / "config/providers/claude.md"), claude)
        self.assertIn(str(ROOT / "config/providers/codex.md"), codex)
        for rule in guidance["always_on_rules"]:
            with self.subTest(rule=rule):
                expected_rule = str(ROOT / rule)
                self.assertIn(expected_rule, claude)
                self.assertIn(expected_rule, codex)
        for provider in ("claude", "codex"):
            document = ROOT / f"config/providers/{provider}.md"
            self.assertTrue(document.is_file())
            self.assertIn("capability bindings", document.read_text().lower())

    def test_dependencies_resolve_from_source_link_and_isolated_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / ".agents/skills/workflows"
            installed.parent.mkdir(parents=True)
            installed.symlink_to(ROOT / "skills/workflows", target_is_directory=True)
            source_root = installed.resolve().parents[1]
            self.assertEqual(ROOT, source_root)

            plugin = Path(temporary) / "plugin"
            for relative in (
                ".codex-plugin",
                "aitk",
                "bin",
                "config",
                "docs",
                "interfaces",
                "rules",
                "skills",
            ):
                shutil.copytree(ROOT / relative, plugin / relative, symlinks=True)
            shutil.copy2(ROOT / "PROJECT_TEMPLATE.md", plugin / "PROJECT_TEMPLATE.md")
            routed = subprocess.run(
                [
                    str(plugin / "bin/aitk"),
                    "--root",
                    str(plugin),
                    "model-route",
                    "deep-review",
                    "--provider",
                    "codex",
                    "--boundary",
                    "review.code-quality-final",
                    "--json",
                ],
                cwd=Path(temporary),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, routed.returncode, routed.stderr)
            self.assertEqual("deep-review", json.loads(routed.stdout)["route"])
            declared = {
                entry["name"]: Path(entry["path"])
                for entry in load_skill_interfaces(plugin)
                if str(entry["path"]).startswith("skills/")
            }

            resolved: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {}
            for repository in (source_root, plugin):
                self.assertEqual([], validate_workflows(repository))
                workflows = load_workflows(repository)
                repository_map: dict[str, tuple[tuple[str, str], ...]] = {}
                for workflow in workflows:
                    with self.subTest(
                        repository=repository.name, workflow=workflow.name
                    ):
                        dependencies = workflow_dependency_resources(
                            repository, workflow
                        )
                        repository_map[workflow.name] = tuple(
                            (dependency.name, dependency.resource.as_posix())
                            for dependency in dependencies
                        )
                        for dependency in dependencies:
                            resource = repository / dependency.resource
                            skill_root = repository / declared[dependency.name]
                            self.assertTrue(resource.is_file(), resource)
                            self.assertTrue(
                                resource.is_relative_to(skill_root), resource
                            )
                            self.assertTrue(resource.read_bytes(), resource)
                resolved[repository.name] = repository_map

            self.assertEqual(resolved[source_root.name], resolved[plugin.name])
            expected_review_plan = {
                (
                    "plan-review",
                    "skills/plan-review/references/architecture.md",
                ),
                ("plan-review", "skills/plan-review/references/backend.md"),
                ("plan-review", "skills/plan-review/references/frontend.md"),
                (
                    "plan-review",
                    "skills/plan-review/references/implementation.md",
                ),
                ("planning", "skills/planning/references/finalize.md"),
                ("pm", "skills/pm/references/review-feature-brief.md"),
                ("testing", "skills/testing/references/review-testplan.md"),
            }
            self.assertEqual(
                expected_review_plan,
                set(resolved[source_root.name]["review-plan"]),
            )
            self.assertEqual(
                {
                    (
                        "archive-project-file",
                        "skills/archive-project-file/SKILL.md",
                    ),
                    ("metrics-emit", "skills/metrics-emit/SKILL.md"),
                    ("reporting", "skills/reporting/SKILL.md"),
                    (
                        "reporting",
                        "skills/reporting/templates/complete-project-final.md",
                    ),
                    (
                        "reporting",
                        "skills/reporting/templates/complete-project-metrics.md",
                    ),
                    (
                        "reporting",
                        "skills/reporting/templates/complete-project-summary.md",
                    ),
                },
                set(resolved[source_root.name]["complete-project"]),
            )
            self.assertGreater(
                sum(len(items) for items in resolved[source_root.name].values()),
                0,
            )

    def test_plugin_distribution_matches_public_skill_support_scope(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        support = json.loads((ROOT / "interfaces/support.json").read_text())
        plugin_root = ROOT / str(manifest["skills"])
        public = [
            entry
            for entry in load_skill_interfaces(ROOT)
            if entry["classification"] in {"public_router", "public_direct"}
        ]

        self.assertIn("codex-plugin", support["distributions"])
        for entry in public:
            path = Path(str(entry["path"]))
            if path.parts[0] == "skills":
                self.assertTrue(
                    (plugin_root / path.relative_to("skills") / "SKILL.md").is_file()
                )
        pgm = next(entry for entry in public if entry["name"] == "pgm")
        self.assertEqual("extensions", Path(str(pgm["path"])).parts[0])
        self.assertEqual(["source-linked"], support["extension_distributions"]["pgm"])

    def test_ci_matrix_exactly_covers_the_declared_support_window(self) -> None:
        support = json.loads((ROOT / "interfaces/support.json").read_text())
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        os_match = re.search(r"(?m)^\s*os:\s*\[([^]]+)\]", workflow)
        python_match = re.search(r"(?m)^\s*python-version:\s*\[([^]]+)\]", workflow)
        self.assertIsNotNone(os_match)
        self.assertIsNotNone(python_match)
        matrix_os = {item.strip().strip("\"'") for item in os_match.group(1).split(",")}
        matrix_python = {
            item.strip().strip("\"'") for item in python_match.group(1).split(",")
        }
        minimum = int(str(support["python"]["minimum"]).split(".")[1])
        maximum = int(str(support["python"]["maximum"]).split(".")[1])

        self.assertEqual(set(support["operating_systems"]), matrix_os)
        self.assertEqual(
            {f"3.{minor}" for minor in range(minimum, maximum + 1)},
            matrix_python,
        )


if __name__ == "__main__":
    unittest.main()
