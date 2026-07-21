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
            "PROJECT.md\nPROJECT_ARCHIVE.md\nPLAN.md\nWATCH.md\nCHERRY_PICK.md\nCI_FIX.md\nbuild/\n"
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
