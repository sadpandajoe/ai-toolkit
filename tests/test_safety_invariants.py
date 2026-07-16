from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def authored_files() -> list[Path]:
    roots = [
        "commands",
        "config",
        "extensions",
        "hooks",
        "rules",
        "scripts",
        "skills",
        "statusline",
    ]
    files: list[Path] = [
        ROOT / "install.sh",
        ROOT / "install-hooks.sh",
        ROOT / "setup.sh",
    ]
    for relative in roots:
        files.extend(
            path
            for path in (ROOT / relative).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    return files


class SafetyInvariantTests(unittest.TestCase):
    def test_secret_values_are_never_echoed(self) -> None:
        pattern = re.compile(
            r"\becho\b[^\n]*\$(?:\{)?[A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET|API_KEY)",
            re.IGNORECASE,
        )
        offenders = []
        for path in authored_files():
            text = path.read_text(errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                    )
        self.assertEqual([], offenders, "secret-bearing variables must not be printed")

    def test_rbac_seed_is_dry_run_and_never_targets_production(self) -> None:
        text = read("skills/preset-rbac-setup/SKILL.md")
        lowered = text.lower()
        self.assertIn("dry-run by default", lowered)
        self.assertIn("--apply", text)
        self.assertNotIn("default to pre-cleaning", lowered)
        self.assertNotIn("without explicit confirmation", lowered)
        self.assertIn("refuse", lowered)

    def test_all_local_workflow_state_is_hook_protected(self) -> None:
        text = read("hooks/prevent-project-commit.sh")
        for stem in (
            "PROJECT",
            "PROJECT_ARCHIVE",
            "PLAN",
            "WATCH",
            "CHERRY_PICK",
            "CI_FIX",
        ):
            self.assertIn(stem, text)

    def test_personal_absolute_paths_do_not_leak_into_authored_source(self) -> None:
        personal_path = re.compile(r"/(?:Users|home)/[^<*`\s/]+/")
        offenders = []
        for path in authored_files():
            text = path.read_text(errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                if personal_path.search(line):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                    )
        self.assertEqual([], offenders)

    def test_qa_evidence_contract_has_one_location_and_format(self) -> None:
        qa_root = ROOT / "skills/qa"
        combined = "\n".join(
            path.read_text(errors="replace")
            for path in qa_root.rglob("*")
            if path.is_file()
        )
        self.assertNotIn("qa-evidence/", combined)
        self.assertNotIn("<file>.mov", combined)
        self.assertNotIn("not one giant recording", combined)
        self.assertIn("~/qa-recordings/", combined)
        self.assertIn(".webm", combined)

    def test_test_pr_scenario_selection_matches_command_contract(self) -> None:
        text = read("skills/qa/references/test-pr/scenarios.md")
        self.assertNotIn("## Confirmation", text)
        self.assertIn("proceed by default", text)
        self.assertIn("--step", text)

    def test_review_requires_fresh_reviewer_and_consistent_core_routing(self) -> None:
        code_quality = read("skills/review/references/code-quality.md")
        pr_review = read("skills/review/references/pr-review.md")
        self.assertNotIn("Review your own fix", code_quality)
        self.assertIn("fresh-context", code_quality)
        self.assertNotIn("TRIVIAL + CORE -> full review team", pr_review)

    def test_resource_policy_is_capacity_based_not_container_count_based(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "rules/resource-management.md",
                "hooks/check-resources.sh",
                "skills/preflight/rules.md",
                "skills/superset-local/references/start-stack.md",
            )
        )
        self.assertNotRegex(
            combined,
            r"(?i)(?:more than|>)\s*2(?!\d)[^\n]*(?:ask|confirm)",
        )
        self.assertNotIn("Current host: Apple", combined)
        self.assertNotIn('"$DOCKER_COUNT" -gt 2', combined)
        self.assertIn("Total Memory", combined)

    def test_stack_start_does_not_silently_modify_application_source(self) -> None:
        text = read("skills/superset-local/references/start-stack.md")
        self.assertIn("Do not modify application source code by default", text)
        self.assertIn("explicit", text.lower())

    def test_shortcut_retry_does_not_use_eval(self) -> None:
        self.assertNotIn('eval "$1"', read("skills/shortcut/references/fetch.md"))

    def test_read_only_work_does_not_require_project_state_mutation(self) -> None:
        text = read("rules/universal.md")
        self.assertNotIn("every command or ad-hoc work session", text)
        self.assertIn("Read-only", text)


class InstallerOwnershipTests(unittest.TestCase):
    def run_installer(
        self, home: Path, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["CODEX_HOME"] = str(home / ".codex")
        return subprocess.run(
            ["/bin/sh", str(ROOT / "install.sh"), *arguments],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_install_is_non_destructive_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            claude = home / ".claude"
            custom_command = claude / "commands/custom.md"
            custom_skill = claude / "skills/custom/SKILL.md"
            custom_command.parent.mkdir(parents=True)
            custom_skill.parent.mkdir(parents=True)
            custom_command.write_text("# Custom command\n")
            custom_skill.write_text("---\nname: custom\ndescription: Custom\n---\n")
            claude_md = claude / "CLAUDE.md"
            claude_md.write_text("# Personal instructions\n")
            codex_md = home / ".codex/AGENTS.md"
            codex_md.parent.mkdir(parents=True)
            codex_md.write_text("# Personal Codex instructions\n")

            first = self.run_installer(home)
            self.assertEqual(0, first.returncode, first.stderr)
            self.assertEqual("# Custom command\n", custom_command.read_text())
            self.assertEqual(
                "---\nname: custom\ndescription: Custom\n---\n",
                custom_skill.read_text(),
            )
            self.assertIn("# Personal instructions", claude_md.read_text())
            self.assertIn("# Personal Codex instructions", codex_md.read_text())
            self.assertIn("# >>> ai-toolkit managed guidance >>>", codex_md.read_text())
            self.assertTrue((home / ".agents/skills/workflows").is_symlink())
            self.assertTrue((home / ".claude/skills/workflows").is_symlink())
            self.assertFalse((home / ".agents/skills/debug").exists())
            self.assertFalse((home / ".codex/skills/debug").exists())

            backups_after_first = sorted(claude.glob("backup-*"))
            ledger = home / ".ai-toolkit/install-state.json"
            first_ledger = ledger.read_bytes()
            first_ledger_mtime = ledger.stat().st_mtime_ns
            first_snapshot = sorted(
                str(path.relative_to(home))
                for path in home.rglob("*")
                if not path.is_dir()
            )

            second = self.run_installer(home)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(backups_after_first, sorted(claude.glob("backup-*")))
            self.assertEqual(first_ledger, ledger.read_bytes())
            self.assertEqual(first_ledger_mtime, ledger.stat().st_mtime_ns)
            second_snapshot = sorted(
                str(path.relative_to(home))
                for path in home.rglob("*")
                if not path.is_dir()
            )
            self.assertEqual(first_snapshot, second_snapshot)

    def test_install_preserves_conflicts_and_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            conflict = home / ".claude/commands/start.md"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("# Personal start command\n")

            result = self.run_installer(home)

            self.assertEqual(1, result.returncode)
            self.assertIn("conflict preserved", result.stderr)
            self.assertEqual("# Personal start command\n", conflict.read_text())
            self.assertTrue((home / ".agents/skills/workflows").is_symlink())

    def test_installer_delegates_generation_to_aitk(self) -> None:
        installer = read("install.sh")
        implementation = read("aitk/installer.py")
        self.assertIn('exec "$ROOT/bin/aitk" install', installer)
        self.assertIn("write_build(paths.root", implementation)
        self.assertNotIn('rm -rf "$BUILD_DIR"', installer)

    def test_optional_pgm_commands_are_linked_during_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result = self.run_installer(home, "--with-pgm")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(
                (home / ".claude/commands/create-status-report.md").is_symlink()
            )
            self.assertTrue(
                (home / ".claude/commands/create-velocity-report.md").is_symlink()
            )
            self.assertTrue((home / ".claude/skills/pgm").is_symlink())
            self.assertTrue((home / ".agents/skills/pgm").is_symlink())

            regular = self.run_installer(home)
            self.assertEqual(0, regular.returncode, regular.stderr)
            self.assertFalse(
                (home / ".claude/commands/create-status-report.md").exists()
            )
            self.assertFalse((home / ".agents/skills/pgm").exists())

    def test_install_migrates_legacy_whole_directory_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            claude = home / ".claude"
            claude.mkdir(parents=True)
            (claude / "commands").symlink_to(ROOT / "build/commands")
            (claude / "skills").symlink_to(ROOT / "skills")
            (claude / "CLAUDE.md").symlink_to(ROOT / "build/config/CLAUDE.md")

            result = self.run_installer(home)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((claude / "commands").is_dir())
            self.assertFalse((claude / "commands").is_symlink())
            self.assertTrue((claude / "skills").is_dir())
            self.assertFalse((claude / "skills").is_symlink())
            self.assertTrue((claude / "commands/fix-bug.md").is_symlink())
            self.assertTrue((claude / "skills/workflows").is_symlink())
            self.assertFalse((claude / "skills/debug").exists())
            self.assertIn(
                "# >>> ai-toolkit managed guidance >>>",
                (claude / "CLAUDE.md").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
