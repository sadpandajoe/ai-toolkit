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


# The standing PII and secret scan over tracked files. Placeholders pass: a
# repeated-digit or 12345 story id, `<org>`/`<ws>` slots, made-up workspaces.
PLACEHOLDER_ID = re.compile(r"^(?:12345|(\d)\1+)$")
LEAK_PATTERNS = (
    ("Shortcut story URL", re.compile(r"app\.shortcut\.com/[\w-]+/story/(\d+)")),
    ("Shortcut story id", re.compile(r"\bsc-(\d{5,})\b", re.IGNORECASE)),
    (
        "internal workspace host",
        re.compile(
            r"\b(?=[0-9a-f]{0,7}\d)[0-9a-f]{8}\.(?:[a-z0-9-]+\.)*app(?:-stg|-dev)?\.preset\.io\b",
            re.IGNORECASE,
        ),
    ),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{22,})")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("API key", re.compile(r"\bsk-(?:ant-[\w-]{20,}|(?:proj-)?[A-Za-z0-9]{32,})")),
    ("Google API key", re.compile(r"\bAIza[\w-]{35}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
FIXTURE_DIRECTORIES = ("tests/fixtures/",)


def tracked_files() -> list[Path] | None:
    try:
        listing = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        return None
    return [
        ROOT / name
        for name in listing.split("\0")
        if name and not name.startswith(FIXTURE_DIRECTORIES) and (ROOT / name).is_file()
    ]


def leak_findings(paths: list[Path], root: Path = ROOT) -> list[str]:
    findings = []
    for path in paths:
        data = path.read_bytes()
        if b"\0" in data:
            continue
        for line_number, line in enumerate(data.decode(errors="replace").splitlines(), 1):
            for label, pattern in LEAK_PATTERNS:
                for match in pattern.finditer(line):
                    if match.groups() and PLACEHOLDER_ID.match(match.group(1) or ""):
                        continue
                    findings.append(f"{path.relative_to(root)}:{line_number}: {label}: {match.group(0)}")
    return findings


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

    def test_tracked_files_carry_no_pii_or_secrets(self) -> None:
        files = tracked_files()
        if files is None:
            self.skipTest("not a git checkout")
        self.assertEqual([], leak_findings(files))

    def test_the_leak_scan_catches_seeded_values(self) -> None:
        # Seeds are assembled at run time so this file holds no literal leak.
        story = "https://app.shortcut.com/" + "acme/story/" + "48213"
        seeded = {
            "Shortcut story URL": f"See {story}#activity-77",
            "Shortcut story id": "Fixes " + "sc-" + "48213.",
            "internal workspace host": "https://" + "9f3c2a1b" + ".us1a.app-stg.preset.io/",
            "GitHub token": "token=" + "ghp_" + "A1b2C3d4" * 5,
            "AWS access key": "AKIA" + "ABCDEFGH" + "12345678",
            "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
        }
        placeholders = (
            "Story: https://app.shortcut.com/<org>/story/<story-id>",
            "create-feature sc-12345 or sc-NNNNN",
            "https://<ws>.us1a.app-stg.preset.io and ws1.us1a.app-dev.preset.io",
            "`app.preset.io`, manage.app-stg.preset.io",
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for index, (label, text) in enumerate(seeded.items()):
                with self.subTest(seed=label):
                    path = base / f"seed-{index}.md"
                    path.write_text(f"intro\n{text}\n")
                    findings = leak_findings([path], base)
                    self.assertTrue(any(f"seed-{index}.md:2: {label}:" in item for item in findings), findings)
            clean = base / "placeholders.md"
            clean.write_text("\n".join(placeholders) + "\n")
            self.assertEqual([], leak_findings([clean], base))

    def test_rbac_seed_is_dry_run_and_never_targets_production(self) -> None:
        text = read("skills/preset-rbac-setup/SKILL.md")
        lowered = text.lower()
        self.assertIn("dry-run by default", lowered)
        self.assertIn("--apply", text)
        self.assertNotIn("default to pre-cleaning", lowered)
        self.assertNotIn("without explicit confirmation", lowered)
        self.assertIn("refuse", lowered)

    def test_all_local_workflow_state_is_hook_protected(self) -> None:
        # The wrapper hands every command to aitk.hooks.git_guard, which blocks
        # commits of the files in project_state.STATE_FILES.
        from aitk.project_state import STATE_FILES

        for stem in (
            "PROJECT",
            "PROJECT_ARCHIVE",
            "PLAN",
            "WATCH",
            "CHERRY_PICK",
            "CI_FIX",
        ):
            self.assertIn(f"{stem}.md", STATE_FILES)
        self.assertIn("python3 -m aitk.hooks.git_guard", read("hooks/prevent-project-commit.sh"))
        self.assertIn("from aitk.project_state import STATE_FILES", read("aitk/hooks/git_guard.py"))

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
        local = read("skills/review/references/local-review.md")
        pr_review = read("skills/review/references/pr-review.md")
        reviewer = read("agents/specialists/reviewer.md")
        self.assertIn("never review\ninline", local)
        self.assertIn("Launch one fresh reviewer worker", local)
        self.assertIn("Launch one fresh reviewer worker", pr_review)
        self.assertIn("you never edit, run tests, or dispatch anything", reviewer)
        self.assertNotIn("TRIVIAL + CORE -> full review team", pr_review)

    def test_resource_policy_is_capacity_based_not_container_count_based(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "rules/resource-management.md",
                "hooks/check-resources.sh",
                "skills/workflows/references/check-resources.md",
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

    def test_install_ignores_personal_legacy_command_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            conflict = home / ".claude/commands/start.md"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("# Personal start command\n")

            result = self.run_installer(home)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("# Personal start command\n", conflict.read_text())
            self.assertTrue((home / ".agents/skills/workflows").is_symlink())

    def test_installer_delegates_generation_to_aitk(self) -> None:
        installer = read("install.sh")
        implementation = read("aitk/installer.py")
        self.assertIn('exec "$ROOT/bin/aitk" install', installer)
        self.assertIn("write_build(paths.root", implementation)
        self.assertNotIn('rm -rf "$BUILD_DIR"', installer)

    def test_optional_pgm_skill_is_linked_during_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result = self.run_installer(home, "--with-pgm")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((home / ".claude/skills/pgm").is_symlink())
            self.assertTrue((home / ".agents/skills/pgm").is_symlink())

            regular = self.run_installer(home)
            self.assertEqual(0, regular.returncode, regular.stderr)
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
            self.assertFalse((claude / "commands").exists())
            self.assertTrue((claude / "skills").is_dir())
            self.assertFalse((claude / "skills").is_symlink())
            self.assertTrue((claude / "skills/workflows").is_symlink())
            self.assertFalse((claude / "skills/debug").exists())
            self.assertIn(
                "# >>> ai-toolkit managed guidance >>>",
                (claude / "CLAUDE.md").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
