"""require-review-gate.sh blocks `gh pr create` until the review gate is PASS.

The hook reads the routing snapshot in the repository's PROJECT.md through the
same `gate_blockers` check `checkpoint reserve` uses, so each case builds the
snapshot with the real `project-state` CLI rather than hand-writing the block.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AITK = str(ROOT / "bin" / "aitk")
PR_CREATE = 'gh pr create --title "t" --body "b"'


def run_hook(command: str, cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != "SKIP_PR_GATE"}
    environment.update(env)
    return subprocess.run(
        ["bash", str(ROOT / "hooks" / "require-review-gate.sh")],
        input=json.dumps(
            {"cwd": str(cwd), "tool_input": {"command": command}, "hook_event_name": "PreToolUse"}
        ),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )


def project_state(repo: Path, *args: str) -> None:
    subprocess.run(
        [AITK, "project-state", *args, "--file", str(repo / "PROJECT.md")],
        check=True,
        capture_output=True,
        text=True,
    )


def checkpoint(repo: Path, action: str, *args: str) -> None:
    subprocess.run(
        [AITK, "checkpoint", action, "--workflow", "create-feature", "--file", str(repo / "PROJECT.md"), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class ReviewGateHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        # macOS temp dirs sit under the /var -> /private/var symlink, which
        # `aitk checkpoint` refuses; resolve like tests/test_checkpoint.py.
        self.repo = Path(self._temporary.name).resolve()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q", "-b", "main"], check=True)

    def classify(self, repo: Path | None = None) -> None:
        project_state(
            repo or self.repo,
            "init",
            "--workflow", "create-feature",
            "--complexity", "STANDARD",
            "--size", "M",
            "--phaseability", "none",
            "--phase", "review",
        )

    def record_review(self, status: str, unit: str | None = None) -> None:
        args = ["gate", "--gate", "review", "--status", status]
        if unit:
            args += ["--unit", unit]
        project_state(self.repo, *args)

    def assert_blocked(self, result: subprocess.CompletedProcess[str], *fragments: str) -> None:
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        self.assertIn("`review-code` on the branch for a change outside any workflow", result.stderr)
        self.assertNotIn("SKIP_PR_GATE", result.stderr)
        self.assertNotIn("--status PASS", result.stderr)
        for fragment in fragments:
            self.assertIn(fragment, result.stderr)

    def test_blocks_when_no_project_file_exists(self) -> None:
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "no PROJECT.md")

    def test_blocks_when_project_file_has_no_snapshot(self) -> None:
        (self.repo / "PROJECT.md").write_text("# Notes\n")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "no routing snapshot")

    def test_blocks_when_snapshot_never_recorded_review(self) -> None:
        self.classify()
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_allows_when_review_passed(self) -> None:
        self.classify()
        self.record_review("PASS")
        result = run_hook(PR_CREATE, self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_blocks_when_another_unit_is_still_open(self) -> None:
        self.classify()
        self.record_review("RETRY", unit="slice-two")
        self.record_review("PASS", unit="slice-one")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=RETRY", "slice-two")

    def test_blocks_review_pass_recorded_in_another_phase(self) -> None:
        self.classify()
        self.record_review("PASS")
        project_state(self.repo, "advance", "--to", "next-phase")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_resolves_project_file_from_a_subdirectory(self) -> None:
        self.classify()
        self.record_review("PASS")
        nested = self.repo / "pkg" / "src"
        nested.mkdir(parents=True)
        self.assertEqual(0, run_hook(PR_CREATE, nested).returncode)

    def test_bypass_prefix_and_environment_allow(self) -> None:
        self.assertEqual(0, run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
        self.assertEqual(0, run_hook(f"env SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
        self.assertEqual(0, run_hook(PR_CREATE, self.repo, SKIP_PR_GATE="1").returncode)
        self.assertEqual(2, run_hook(PR_CREATE, self.repo, SKIP_PR_GATE="0").returncode)

    def test_matches_pr_create_inside_compound_and_shell_commands(self) -> None:
        for command in (
            f"git push -u origin HEAD && {PR_CREATE}",
            f"cd . ; {PR_CREATE}",
            "git push -u origin HEAD\ngh pr create --fill",
            "git status\n\ngh pr new --fill",
            "if gh pr view --json url >/dev/null 2>&1; then echo exists; else gh pr create --fill; fi",
            "{ gh pr create --fill; }",
            "! gh pr create --fill",
            "then gh pr create --fill",
            f"bash -c '{PR_CREATE}'",
            f"bash -lc '{PR_CREATE}'",
            f"bash -ec '{PR_CREATE}'",
            "eval 'gh pr create --title t'",
            "env gh pr create --title t",
            "env GH_TOKEN=x gh pr create --title t",
            "timeout 60 gh pr create --fill",
            "echo x | xargs gh pr create",
            "GH_TOKEN=x gh pr create --draft",
            "/opt/homebrew/bin/gh pr create",
            "gh pr create --repo o/r --draft",
            "gh --repo o/r pr create --fill",
            "gh -R o/r pr create --fill",
            "gh pr new",
            "SKIP_PR_GATE=0 gh pr create --fill",
            "SKIP_PR_GATE= gh pr create --fill",
            "env -u UNUSED gh pr create --fill",
            "command -p gh pr create --fill",
            "timeout --signal TERM 60 gh pr create --fill",
            "xargs -I '{}' gh pr create",
            'printf \'%s\' "first \\"\nsecond"\ngh pr create --fill',
            "# open the PR\ngh pr create --fill",
            "git push # push first\ngh pr create --fill",
            "git push -u origin HEAD && \\\n  gh pr create --fill",
            "gh pr create --title \"x\" --body \"$(cat <<'EOF'\n## Summary\n- supports 12\" screens\nEOF\n)\"",
            "cat <<'END-BODY' > /dev/null\nit's here\nEND-BODY\ngh pr create --fill",
            "env -S 'gh pr create --fill'",
            "env --split-string='gh pr create --fill'",
            'echo "$(gh pr create --fill)"',
            "URL=`gh pr create --fill`",
            'gh pr create --title "never closed',
            "echo a\\ #; gh pr create --fill",
            "env -S '-u UNUSED gh pr create --fill'",
            "env -S 'gh\\_pr\\_create'",
        ):
            with self.subTest(command=command):
                self.assertEqual(2, run_hook(command, self.repo).returncode)

    def test_ignores_commands_that_are_not_pr_create(self) -> None:
        for command in (
            "gh pr view 12",
            "gh pr list --search create",
            "gh pr create --help",
            'git commit -m "docs: mention gh pr create"',
            'echo "gh pr create"',
            'git commit -m "first line\ngh pr create in the body"',
            "gh issue create --title t",
            "gh repo new",
            "cat <<'EOF' > notes.md\ngh pr create\nEOF",
            "cat <<-EOF\n\tgh pr create\n\tEOF\nls",
            "cat <<'END-DOC' > notes.md\ngh pr create\nEND-DOC",
            "# gh pr create later\nls",
            'git commit -m "x" # gh pr create',
            'echo "${#HOME} $#"',
            "ls",
        ):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_cd_inside_the_command_selects_the_repository_checked(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.repo.parent / (self.repo.name + "-other")
        other.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        subprocess.run(["git", "-C", str(other), "init", "-q", "-b", "main"], check=True)
        self.assert_blocked(run_hook(f"cd {other} && {PR_CREATE}", self.repo), "no PROJECT.md")
        self.assertEqual(0, run_hook(PR_CREATE, self.repo).returncode)
        # And the reverse: a gated target repo is allowed from an ungated session repo.
        self.classify(other)
        project_state(other, "gate", "--gate", "review", "--status", "PASS")
        with tempfile.TemporaryDirectory() as bare:
            subprocess.run(["git", "-C", bare, "init", "-q", "-b", "main"], check=True)
            self.assertEqual(0, run_hook(f"cd {other} && {PR_CREATE}", Path(bare)).returncode)

    def ungated_repo(self) -> Path:
        other = self.repo.parent / (self.repo.name + "-other")
        other.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        subprocess.run(["git", "-C", str(other), "init", "-q", "-b", "main"], check=True)
        return other

    def test_env_chdir_selects_the_repository_checked(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        for command in (
            f"env -C {other} gh pr create --fill",
            f"env --chdir={other} gh pr create --fill",
            f"env -C{other} gh pr create --fill",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "no PROJECT.md")

    def test_every_pr_creation_in_a_request_is_checked(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        self.assert_blocked(
            run_hook(f"{PR_CREATE}; cd {other} && {PR_CREATE}", self.repo), "no PROJECT.md"
        )
        self.assert_blocked(
            run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}; cd {other} && {PR_CREATE}", self.repo),
            "no PROJECT.md",
        )
        self.assertEqual(0, run_hook(f"{PR_CREATE}; git status", self.repo).returncode)

    def test_pending_reservation_from_another_workflow_does_not_count(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase-one")
        project_state(
            self.repo,
            "init", "--replace",
            "--workflow", "fix-bug",
            "--complexity", "STANDARD",
            "--size", "S",
            "--phaseability", "none",
            "--phase", "fix",
        )
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_directory_context_follows_the_command_order(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        (self.repo / "sub").mkdir()
        (other / "sub").mkdir()
        for command in (
            f'cd {other} && echo "$(gh pr create --fill)"',
            f'{PR_CREATE}; cd {other}; echo "$(gh pr create)"',
            f"env -C {other} env -C sub gh pr create --fill",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "no PROJECT.md")

    def test_unresolvable_target_blocks_instead_of_inheriting_a_pass(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        nested = f"cd {other} && gh pr create --fill"
        for _ in range(5):
            nested = f"sh -c {shlex.quote(nested)}"
        for command in (
            f"cd {other}; gh pr create --title $'it\\'s fixed' --body x",
            nested,
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "cannot follow")
        # Without a directory change the starting repo is the target, so a pass holds.
        self.assertEqual(0, run_hook("gh pr create --title $'it\\'s fixed' --body x", self.repo).returncode)

    def test_blocks_when_project_file_is_unreadable(self) -> None:
        project = self.repo / "PROJECT.md"
        project.write_text("# Notes\n")
        project.chmod(0)
        self.addCleanup(lambda: project.chmod(0o644))
        if os.access(project, os.R_OK):
            self.skipTest("file permissions are not enforced for this user")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "could not be read")

    def test_blocks_when_snapshot_is_malformed(self) -> None:
        (self.repo / "PROJECT.md").write_text(
            "<!-- aitk-project-state:v2 -->\n{\"schema_version\": 2}\n<!-- /aitk-project-state -->\n"
        )
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "unreadable")

    def test_pending_publish_reservation_survives_a_phase_advance(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase-one")
        project_state(self.repo, "advance", "--to", "next-phase")
        result = run_hook(PR_CREATE, self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_pending_reservation_never_overrides_a_later_retry(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase-one")
        self.record_review("RETRY", unit="slice-two")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=RETRY")

    def test_finds_project_file_in_a_subdirectory_workflow(self) -> None:
        nested = self.repo / "pkg"
        nested.mkdir()
        self.classify(nested)
        project_state(nested, "gate", "--gate", "review", "--status", "PASS")
        self.assertEqual(0, run_hook(PR_CREATE, nested).returncode)

    def test_allows_outside_a_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(0, run_hook(PR_CREATE, Path(outside)).returncode)


if __name__ == "__main__":
    unittest.main()
