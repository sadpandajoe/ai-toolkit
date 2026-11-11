"""The verify gate: `gh pr create` needs a passing scripts/verify.py record on
the exact tree it opens (hooks/lib/verify_record.py, git_guard.check_pr_verified)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import git_guard  # noqa: E402
import verify_record  # noqa: E402

sys.path.pop(0)

VERIFY = ROOT / "scripts" / "verify.py"
WRAPPER = ROOT / "hooks" / "prevent-project-commit.sh"
CREATE = "gh pr create --draft --fill"
OVERRIDES = ("AITK_PR_READY", "SKIP_PR_GATE", "SKIP_PRECHECK")


def clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in OVERRIDES}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return env


class VerifyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name).resolve() / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "feature")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.write("app.py", "print('one')\n")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "base")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, env=clean_env(), check=True, capture_output=True, text=True
        ).stdout

    def write(self, name: str, text: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, *paths: str, message: str = "change") -> None:
        self.git("add", "--", *paths)
        self.git("commit", "-q", "-m", message)

    def verify(
        self, *command: str, partial: str | None = None, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        args = [sys.executable, str(VERIFY)] + (["--partial", partial] if partial else []) + ["--", *command]
        return subprocess.run(
            args, cwd=cwd or self.repo, env={**clean_env(), **(env or {})}, capture_output=True, text=True, check=False
        )

    def gate(self, command: str = CREATE, env: dict[str, str] | None = None, cwd: Path | None = None) -> str | None:
        """The block message, or None when the guard allows the command."""
        try:
            git_guard.evaluate(command, str(cwd or self.repo), env or {})
        except git_guard.Blocked as blocked:
            return str(blocked)
        return None

    def assert_blocked(self, *needles: str, **kwargs) -> str:
        message = self.gate(**kwargs)
        self.assertIsNotNone(message, "expected the verify gate to block")
        for needle in needles:
            self.assertIn(needle, message)
        return message

    def test_no_record_blocks_and_names_the_script(self) -> None:
        message = self.assert_blocked("no check has been recorded", "scripts/verify.py", "--partial")
        self.assertIn("with their agreement, record the closest real check", message)

    def test_a_check_on_the_clean_commit_opens_the_pr(self) -> None:
        self.write("app.py", "print('two')\n")
        self.commit("app.py")
        self.assertEqual(0, self.verify("true").returncode)
        self.assertIsNone(self.gate())

    def test_a_check_before_the_commit_counts_once_the_commit_matches(self) -> None:
        self.write("app.py", "print('two')\n")
        self.write("new_module.py", "x = 1\n")  # untracked when the check ran
        result = self.verify("true")
        self.assertIn("2 uncommitted change(s)", result.stderr)
        # HEAD is still the base: what was tested is not committed yet
        self.assert_blocked("no recorded check ran on this tree", "tested but not in the commit")
        self.commit("app.py", "new_module.py")
        self.assertIsNone(self.gate())

    def test_a_deletion_is_part_of_the_tree(self) -> None:
        self.write("old.py", "x = 1\n")
        self.commit("old.py")
        (self.repo / "old.py").unlink()
        self.verify("true")
        self.git("rm", "-q", "old.py")
        self.git("commit", "-q", "-m", "drop old")
        self.assertIsNone(self.gate())

    def test_an_edit_after_the_check_blocks_and_says_which_file(self) -> None:
        self.write("app.py", "print('two')\n")
        self.verify("true")
        self.write("app.py", "print('three')\n")
        self.commit("app.py")
        self.assert_blocked("changed since the run: app.py")

    def test_a_tested_file_left_out_of_the_commit_blocks(self) -> None:
        self.write("app.py", "print('two')\n")
        self.write("scratch.py", "debug = True\n")
        self.verify("true")
        self.commit("app.py")
        self.assert_blocked("tested but not in the commit: scratch.py")

    def test_a_failing_check_blocks_until_that_command_passes_on_the_tree(self) -> None:
        self.assertEqual(3, self.verify("sh", "-c", "exit 3").returncode)
        self.assert_blocked("failed (exit 3)")
        # another command passing does not clear it: the failed one has to pass again
        self.verify("true")
        self.assert_blocked("the newest run of `sh -c 'exit 3'` on this tree failed (exit 3)")
        self.verify("sh", "-c", "exit 0")
        self.verify("sh -c 'exit 3' || true")
        self.assert_blocked("sh -c 'exit 3'")
        self.verify("false")
        self.assert_blocked("failed")

    def test_a_pass_after_a_fail_of_the_same_command_opens_the_pr(self) -> None:
        self.write("flag", "fail\n")
        self.commit("flag")
        self.verify("grep -q pass flag")
        self.assert_blocked("failed (exit 1)")
        # a fix on a new tree: the old failure belongs to the old tree
        self.write("flag", "pass\n")
        self.commit("flag")
        self.verify("grep -q pass flag")
        self.assertIsNone(self.gate())

    def test_each_command_counts_by_its_newest_run(self) -> None:
        self.verify("sh -c 'exit 0'")
        self.verify("true")
        self.assertIsNone(self.gate())
        self.verify("sh -c 'exit 0' && false")
        self.assert_blocked("failed")

    def test_a_check_that_edits_tracked_files_does_not_count(self) -> None:
        result = self.verify("sh", "-c", "echo changed >> app.py")
        self.assertIn("changed files while it ran", result.stderr)
        self.assert_blocked("changed files while it ran, so it did not check this tree")

    def test_files_a_check_creates_are_output_not_changes(self) -> None:
        self.assertEqual(0, self.verify("sh", "-c", "echo report > report.txt").returncode)
        self.assertIsNone(self.gate())

    def test_a_file_an_earlier_check_left_behind_cannot_hide_a_newer_failure(self) -> None:
        check = "touch .coverage; [ -z \"$FAIL\" ]"
        self.assertEqual(0, self.verify(check).returncode)
        self.assertIsNone(self.gate())
        # the same command fails on the same commit, next to the file its first run left
        self.assertEqual(1, self.verify(check, env={"FAIL": "1"}).returncode)
        self.assert_blocked("the newest run of", "failed (exit 1)")
        # and passes again: the leftover is output, so the run still matches the commit
        self.verify(check)
        self.assertIsNone(self.gate())

    def test_an_untracked_leftover_from_outside_verify_cannot_hide_a_failure(self) -> None:
        self.verify("true")
        self.write(".coverage", "left by a plain test run\n")
        self.verify("false")
        self.verify("true")  # passes with the leftover present: does not match the commit
        self.assert_blocked("the newest run of `false` on this tree failed")

    def test_local_notes_never_count(self) -> None:
        self.write("PROJECT.md", "notes\n")
        self.write(".ai-toolkit/config.json", "{}\n")
        self.verify("true")
        self.write("PROJECT.md", "more notes\n")
        self.assertIsNone(self.gate())

    def test_partial_is_recorded_with_what_ci_still_runs(self) -> None:
        self.verify("true", partial="the integration suite")
        records = json.loads((self.repo / ".ai-toolkit" / "verify.json").read_text())["records"]
        self.assertEqual(("partial", "the integration suite"), (records[-1]["level"], records[-1]["left_to_ci"]))
        self.assertIsNone(self.gate())
        status = subprocess.run(
            [sys.executable, str(VERIFY), "--status"], cwd=self.repo, env=clean_env(), capture_output=True, text=True
        )
        self.assertEqual(0, status.returncode)
        self.assertIn("CI still runs: the integration suite", status.stdout)

    def test_the_record_stays_out_of_git_status(self) -> None:
        self.verify("true")
        self.assertNotIn(".ai-toolkit", self.git("status", "--porcelain"))

    def test_records_are_capped(self) -> None:
        for _ in range(verify_record.KEEP + 3):
            verify_record.append(str(self.repo), verify_record.new_record("x", {}, "true", 0, "strong", "", True))
        self.assertEqual(verify_record.KEEP, len(verify_record.load(str(self.repo))))

    def test_no_override_lifts_the_gate(self) -> None:
        # v0.3's retired override and the ready-PR override both leave it on
        for env in ({"SKIP_PR_GATE": "1"}, {"AITK_PR_READY": "1"}, {"SKIP_PRECHECK": "1"}):
            with self.subTest(env=env):
                self.assert_blocked("no check has been recorded", env=env)
        self.assert_blocked("no check has been recorded", env={"AITK_PR_READY": "1"}, command="gh pr create --fill")
        self.assert_blocked("no check has been recorded", command=f"SKIP_PR_GATE=1 {CREATE}")
        # the way past it when nothing meaningful runs: a disclosed partial record
        self.verify("git diff --check", partial="nothing to test: docs only")
        self.assertIsNone(self.gate())

    def test_the_directory_the_command_runs_in_is_the_one_checked(self) -> None:
        other = Path(self.temporary.name).resolve() / "other"
        other.mkdir()
        self.assert_blocked(command=f"cd {self.repo} && {CREATE}", cwd=other)
        self.verify("true")
        self.assertIsNone(self.gate(command=f"cd {self.repo} && {CREATE}", cwd=other))
        self.assert_blocked("not inside a git checkout", command=CREATE, cwd=other)
        self.assert_blocked("cannot follow the directory", command=f'cd "$X" && {CREATE}')

    def test_a_head_branch_is_checked_instead_of_head(self) -> None:
        self.verify("true")
        self.git("switch", "-q", "-c", "other")
        self.write("app.py", "print('other')\n")
        self.commit("app.py")
        self.git("switch", "-q", "feature")
        self.assertIsNone(self.gate(command=f"{CREATE} --head feature"))
        self.assert_blocked(command=f"{CREATE} --head other")
        self.assert_blocked("not a local branch", command=f"{CREATE} -H someone:missing")

    def test_other_gh_commands_and_help_pass(self) -> None:
        for command in ("gh pr view 12", "gh pr create --help", "gh pr list", "echo gh pr create"):
            with self.subTest(command=command):
                self.assertIsNone(self.gate(command=command))

    def test_the_wrapper_runs_the_gate(self) -> None:
        payload = json.dumps({"tool_input": {"command": CREATE}, "cwd": str(self.repo)})
        run = lambda: subprocess.run(  # noqa: E731
            ["bash", str(WRAPPER)], input=payload, text=True, capture_output=True, env=clean_env(), check=False
        )
        blocked = run()
        self.assertEqual(2, blocked.returncode, blocked.stderr)
        self.assertIn("scripts/verify.py", blocked.stderr)
        self.verify("true")
        self.assertEqual(0, run().returncode)


if __name__ == "__main__":
    unittest.main()
