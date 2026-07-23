from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from aitk.build import write_build
from aitk.doctor import _secret_output, run_doctor


class DoctorTests(unittest.TestCase):
    def make_clean_repo(self, root: Path) -> None:
        for directory in (
            "config",
            "hooks",
            "rules",
            "skills/example/references",
        ):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("rules/universal.md skills/example/\n")
        (root / ".gitignore").write_text(
            "/PROJECT.md\n/PROJECT_ARCHIVE.md\n/PLAN.md\n/WATCH.md\n/CHERRY_PICK.md\n/CI_FIX.md\nbuild/\n"
        )
        (root / "config/CLAUDE.md").write_text("@{{TOOLKIT_DIR}}/rules/universal.md\n")
        (root / "rules/universal.md").write_text("# Universal\n")
        (root / "skills/example/SKILL.md").write_text(
            "---\n"
            "name: example\n"
            "description: Use when an example is needed. Do NOT use for real work.\n"
            "---\n\n"
            "Read [details](references/details.md).\n"
        )
        (root / "skills/example/references/details.md").write_text("# Details\n")
        (root / "hooks/prevent-project-commit.sh").write_text(
            "#!/bin/bash\n# PROJECT.md PROJECT_ARCHIVE.md PLAN.md WATCH.md CHERRY_PICK.md CI_FIX.md\n"
        )
        write_build(root)

    def test_clean_fixture_has_no_failures_or_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            findings = run_doctor(root)
            problems = [finding for finding in findings if finding.status != "PASS"]
            self.assertEqual([], problems)

    def test_retired_command_sources_and_slash_aliases_fail_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "commands").mkdir()
            (root / "commands/fix-bug.md").write_text("# Retired\n")
            (root / "extensions/pgm/commands").mkdir(parents=True)
            (root / "extensions/pgm/commands/report.md").write_text("# Retired\n")
            extension_skill = root / "extensions/pgm/skills/pgm/SKILL.md"
            extension_skill.parent.mkdir(parents=True)
            extension_skill.write_text("Route this work to `/create-status-report`.\n")

            finding = next(
                item
                for item in run_doctor(root)
                if item.check == "canonical-ownership"
            )

            self.assertEqual("FAIL", finding.status)
            combined = " ".join(finding.details)
            self.assertIn("commands/fix-bug.md: retired command source", combined)
            self.assertIn(
                "extensions/pgm/commands/report.md: retired command source",
                combined,
            )
            self.assertIn(
                "extensions/pgm/skills/pgm/SKILL.md: retired slash alias",
                combined,
            )

    def test_broken_link_and_bad_description_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "skills/example/SKILL.md").write_text(
                "---\nname: example\ndescription: Example helper.\n---\n"
                "[missing](references/missing.md)\n"
            )
            findings = run_doctor(root)
            messages = "\n".join(
                f"{finding.status} {finding.message} {' '.join(finding.details)}"
                for finding in findings
            )
            self.assertIn("DRIFT Skill descriptions", messages)
            self.assertIn("FAIL Markdown links", messages)

    def test_rule_inventory_requires_a_real_non_readme_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "rules/orphan.md").write_text("# Orphan\n")
            (root / "README.md").write_text(
                "rules/universal.md rules/orphan.md skills/example/\n"
            )

            finding = next(
                item for item in run_doctor(root) if item.check == "rule-loaders"
            )

            self.assertEqual("FAIL", finding.status)
            self.assertEqual(("rules/orphan.md",), finding.details)

    def test_rule_inventory_rejects_rule_only_reference_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "rules/first.md").write_text(
                "# First\n\nRead `rules/second.md`.\n"
            )
            (root / "rules/second.md").write_text(
                "# Second\n\nRead `rules/first.md`.\n"
            )
            (root / "README.md").write_text(
                "rules/universal.md rules/first.md rules/second.md "
                "skills/example/\n"
            )

            finding = next(
                item for item in run_doctor(root) if item.check == "rule-loaders"
            )

            self.assertEqual("FAIL", finding.status)
            self.assertEqual(
                ("rules/first.md", "rules/second.md"), finding.details
            )

    def test_rule_inventory_reports_non_utf8_sources_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "config/binary.yaml").write_bytes(b"\xff\xfe\x00")

            finding = next(
                item for item in run_doctor(root) if item.check == "rule-loaders"
            )

            self.assertEqual("FAIL", finding.status)
            self.assertIn(
                "config/binary.yaml: not valid UTF-8 text", finding.details
            )

    def test_readme_direct_workflow_rule_claims_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "interfaces").mkdir()
            (root / "interfaces/workflows.json").write_text(
                '{"version":1,"skill":"workflows",'
                '"reference_root":"skills/workflows/references",'
                '"workflows":[{"name":"example","summary":"Example",'
                '"arguments":"","rules":["rules/universal.md"],'
                '"triggers":["run example"],"execution_class":"single_run"}]}\n'
            )
            (root / "README.md").write_text(
                "skills/example/\n\n"
                "## Workflow Rules\n\n"
                "| File | Owner / direct workflow loaders |\n"
                "|---|---|\n"
                "| `rules/universal.md` | Always-on guidance; `wrong` |\n"
            )

            finding = next(
                item
                for item in run_doctor(root)
                if item.check == "readme-workflow-rules"
            )

            self.assertEqual("FAIL", finding.status)
            self.assertIn(
                "rules/universal.md: expected example; README claims none",
                finding.details,
            )

    def test_readme_workflow_rule_rows_cannot_be_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "interfaces").mkdir()
            (root / "interfaces/workflows.json").write_text(
                '{"version":1,"skill":"workflows",'
                '"reference_root":"skills/workflows/references",'
                '"workflows":[{"name":"example","summary":"Example",'
                '"arguments":"","rules":[],"triggers":["run example"],'
                '"execution_class":"single_run"}]}\n'
            )
            (root / "README.md").write_text(
                "skills/example/\n\n## Workflow Rules\n\n"
                "| File | Owner / direct workflow loaders |\n|---|---|\n"
                "| `rules/universal.md` | Always-on |\n"
                "| `rules/universal.md` | Still always-on |\n"
            )

            finding = next(
                item
                for item in run_doctor(root)
                if item.check == "readme-workflow-rules"
            )

            self.assertIn(
                "rules/universal.md: duplicate README workflow rule row",
                finding.details,
            )

    def test_state_files_must_be_ignored_only_at_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / ".gitignore").write_text(
                "PROJECT.md\nPROJECT_ARCHIVE.md\nPLAN.md\nWATCH.md\n"
                "CHERRY_PICK.md\nCI_FIX.md\nbuild/\n"
            )

            finding = next(
                item for item in run_doctor(root) if item.check == "state-protection"
            )

            self.assertEqual("FAIL", finding.status)
            self.assertIn("/PLAN.md", finding.details)

    def test_provider_specific_primitives_in_shared_skills_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            details = root / "skills/example/references/details.md"
            details.write_text("Run EnterPlanMode then use model: haiku.\n")
            findings = run_doctor(root)
            portability = next(
                finding
                for finding in findings
                if finding.check == "provider-portability"
            )
            self.assertEqual("FAIL", portability.status)
            self.assertEqual(2, len(portability.details))

    def test_every_forbidden_provider_primitive_category_has_a_negative_fixture(
        self,
    ) -> None:
        cases = {
            "provider template import": "@{{TOOLKIT_DIR}}/rules/provider.md\n",
            "EnterPlanMode": "EnterPlanMode\n",
            "ExitPlanMode": "ExitPlanMode\n",
            "Claude task primitive": "TaskCreate\n",
            "provider worktree primitive": "EnterWorktree\n",
            "provider agent call": "Agent(task='review')\n",
            "provider workflow runtime": "phase('review')\n",
            "provider workflow tool": "Workflow tool\n",
            "provider lifecycle command": "/compact\n",
            "Claude model tier": "model: haiku\n",
            "Claude skill directory": "CLAUDE_SKILL_DIR\n",
            "Claude plugin cache": ".claude/plugins/cache/example\n",
        }
        for label, content in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_clean_repo(root)
                details = root / "skills/example/references/details.md"
                details.write_text(content)

                finding = next(
                    item
                    for item in run_doctor(root)
                    if item.check == "provider-portability"
                )

                self.assertEqual("FAIL", finding.status)
                self.assertTrue(any(label in item for item in finding.details))

    def test_non_object_plugin_manifest_fails_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / ".codex-plugin").mkdir()
            (root / ".codex-plugin/plugin.json").write_text("[]\n")

            finding = next(
                item for item in run_doctor(root) if item.check == "provider-package"
            )

            self.assertEqual("FAIL", finding.status)
            self.assertIn("JSON object", " ".join(finding.details))

    def test_secret_output_scanner_covers_shell_and_python_sinks(self) -> None:
        cases = {
            "echo.sh": 'echo "$GH_TOKEN"\n',
            "printf.sh": "printf '%s\\n' \"${API_KEY}\"\n",
            "trace.sh": "set -x\nrun_command\n",
            "print.py": 'import os\nprint(os.environ["GH_TOKEN"])\n',
            "logging.py": "import logging\napi_key = 'value'\nlogging.info('%s', api_key)\n",
            "raise.py": "secret = 'value'\nraise RuntimeError(secret)\n",
        }
        for filename, content in cases.items():
            with self.subTest(
                filename=filename
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / filename).write_text(content)

                finding = _secret_output(root)

                self.assertEqual("FAIL", finding.status)
                self.assertIn(filename, finding.details)

    def test_secret_output_scanner_ignores_environment_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dependency = root / ".venv/lib/python/site-packages/dependency.py"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("print(API_TOKEN)\n")

            finding = _secret_output(root)

            self.assertEqual("PASS", finding.status)
            self.assertEqual((), finding.details)

    def test_syntax_checks_ignore_environments_but_reject_authored_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            dependency = root / ".venv/lib/python/site-packages"
            dependency.mkdir(parents=True)
            (dependency / "invalid.py").write_text("def broken(\n")
            (dependency / "invalid.sh").write_text("if then\n")

            findings = {item.check: item for item in run_doctor(root)}

            self.assertEqual("PASS", findings["python-syntax"].status)
            self.assertEqual("PASS", findings["shell-syntax"].status)

            authored = root / "scripts"
            authored.mkdir()
            (authored / "invalid.py").write_text("def broken(\n")
            (authored / "invalid.sh").write_text("if then\n")

            findings = {item.check: item for item in run_doctor(root)}

            self.assertEqual("FAIL", findings["python-syntax"].status)
            self.assertEqual("FAIL", findings["shell-syntax"].status)


if __name__ == "__main__":
    unittest.main()
