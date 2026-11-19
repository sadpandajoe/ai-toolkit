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
READY = {"AITK_PR_READY": "1"}  # past the draft rule, to reach the verify gate
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
        # rerunning cannot clear it while the file is still here, so the message says what can
        self.verify("true")
        message = self.assert_blocked(
            "changes the commit doesn't (scratch.py)", "Commit them if they belong", "stop and tell the user"
        )
        self.assertNotIn("record the closest real check", message)

    def test_a_failing_check_blocks_until_that_command_passes_on_the_tree(self) -> None:
        self.assertEqual(3, self.verify("sh", "-c", "exit 3").returncode)
        self.assert_blocked("failed (exit 3)")
        # another command passing does not clear it, a partial one included: the failed one
        # has to pass again, and the message says so instead of offering `--partial`
        self.verify("true")
        self.verify("true", partial="the full suite")
        message = self.assert_blocked(
            "the newest run of `sh -c 'exit 3'` on this tree failed (exit 3)",
            "Only a pass of that same command",
            "a different command does not",
        )
        self.assertNotIn("record the closest real check", message)
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

    def test_a_failure_survives_many_later_runs_of_other_commands(self) -> None:
        self.verify("false")
        base = verify_record.commit(str(self.repo))
        for number in range(25):
            record = verify_record.new_record(base, {}, f"check-{number}", 0, "strong", "", True)
            verify_record.append(str(self.repo), record)
        self.assert_blocked("failed (exit 1)")

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

    def test_a_word_that_may_hide_a_flag_or_a_command_is_a_creation_the_gate_checks(self) -> None:
        for command in (
            "$(command -v gh) pr create --draft --fill",
            "`which gh` pr create --draft --fill",
            '"${GH:-gh}" pr create --draft --fill',
            "{gh,} pr create --draft --fill",
        ):
            with self.subTest(command=command):
                self.assert_blocked("no check has been recorded", command=command)
        self.assert_blocked("Spell the flags out", command="H='--head other'; gh pr create --draft --fill $H", env=READY)
        self.assert_blocked("`--some-new-flag`", "gh 2.103.0", command="gh pr create --draft --fill --some-new-flag", env=READY)
        self.assert_blocked("Write the command and the verb literally", command="gh pr $V --draft --fill", env=READY)

    def test_flags_are_read_the_way_gh_reads_them(self) -> None:
        # a flag's value is no flag: `-h` as a title or `--help` as a body asks for no help
        self.assert_blocked("no check has been recorded", command="gh pr create --draft --title -h --body x")
        self.assert_blocked("no check has been recorded", command="gh pr create --draft --title t --body --help")
        self.assert_blocked("no check has been recorded", command="gh pr new --draft --fill")
        # the verb as gh finds it (an unknown flag before it takes the next word), or one the
        # guard cannot read, is a creation the gate checks
        for command in ("gh pr -t list create --draft --fill", "V=create; gh pr $V --draft --fill"):
            with self.subTest(command=command):
                self.assert_blocked(command=command)
        # nor is `--help=false`, or a value of a flag gh has and the guard must know;
        # help is read only as a word of its own, never inside a bundle (`-fh`)
        for command in (
            "gh pr create --draft --help=false --fill",
            "gh pr create --draft --fill --attach -h.png",
            "gh pr create --draft --fill --recover -h",
            "gh pr create --draft -fh",
        ):
            with self.subTest(command=command):
                self.assert_blocked("no check has been recorded", command=command)
        self.verify("true")
        self.git("switch", "-q", "-c", "other")
        self.write("app.py", "print('other')\n")
        self.commit("app.py")
        self.git("switch", "-q", "feature")
        # `-H` bundled after another short flag still names the head branch
        for command in ("gh pr create -dH other --fill", "gh pr create --fill -dHother", f"{CREATE} -H=other"):
            with self.subTest(command=command):
                self.assert_blocked(command=command)
        # and a title that starts with `-H` names none
        self.assertIsNone(self.gate(command=f'{CREATE} --title "-Hotfix for login"'))
        # two different heads: which one gh opens is not the guard's guess to make
        self.assert_blocked("more than one `--head`", command=f"{CREATE} --head feature --head other")

    def test_a_head_inside_a_flag_value_is_not_the_head(self) -> None:
        self.verify("true")
        self.write("app.py", "print('untested')\n")
        self.commit("app.py")
        # HEAD~1 has the passing record; `--head=HEAD~1` here is the body, so HEAD is opened
        self.assert_blocked(command=f"{CREATE} --body --head=HEAD~1")
        self.assert_blocked(command="gh pr create --draft --fill -b -HHEAD~1")

    def test_a_head_given_as_another_flags_value_is_not_the_head(self) -> None:
        self.verify("true")
        self.git("switch", "-q", "-c", "other")
        self.write("app.py", "print('other')\n")
        self.commit("app.py")
        self.git("switch", "-q", "feature")
        # `--head=other` is the file to attach: gh opens the verified current branch
        self.assertIsNone(self.gate(command=f"{CREATE} --attach --head=other"))

    def test_a_head_branch_that_is_not_checked_out_says_where_to_run_the_check(self) -> None:
        self.verify("true")
        self.git("switch", "-q", "-c", "other")
        self.write("app.py", "print('other')\n")
        self.commit("app.py")
        self.git("switch", "-q", "feature")
        # a run here records this checkout, never `other`, however often it repeats
        self.verify("true")
        message = self.assert_blocked("checkout of `other`", command=f"{CREATE} --head other")
        self.assertNotIn("record the closest real check", message)
        message = self.assert_blocked("checkout of that branch", command=f"{CREATE} -H someone:missing")
        self.assertNotIn("record the closest real check", message)

    def test_outside_a_checkout_or_before_a_commit_the_block_says_so(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        message = self.assert_blocked("not inside a git checkout", "from the repository", cwd=outside)
        self.assertNotIn("record the closest real check", message)
        empty = Path(self.temporary.name) / "empty"
        empty.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=empty, env=clean_env(), check=True)
        message = self.assert_blocked("no commit yet", "Commit the change", cwd=empty)
        self.assertNotIn("record the closest real check", message)

    def test_after_an_unstable_run_only_that_command_clears_the_tree(self) -> None:
        self.verify("echo x >> app.py")
        self.git("checkout", "--", "app.py")
        self.verify("true")
        message = self.assert_blocked("changed files while it ran", "that same command")
        self.assertNotIn("record the closest real check", message)

    def test_a_check_that_restores_a_deleted_file_does_not_count(self) -> None:
        (self.repo / "app.py").unlink()
        self.assertIn("changed files while it ran", self.verify("git checkout -- app.py").stderr)

    def test_check_outputs_stay_outputs_past_the_record_cap(self) -> None:
        self.verify("echo r > report.txt")
        base = verify_record.commit(str(self.repo))
        for _ in range(verify_record.KEEP):
            verify_record.append(str(self.repo), verify_record.new_record(base, {}, "true", 0, "strong", "", True))
        self.write("app.py", "print('two')\n")
        self.commit("app.py")
        self.verify("true")
        self.assertIsNone(self.gate())

    def test_an_unreadable_creation_blocks_even_as_a_draft(self) -> None:
        self.verify("true")
        message = self.assert_blocked(
            "could not be read in full", command="bash -c \"gh pr create --draft --title 'x\""
        )
        self.assertIn("cannot rule out", message)

    def test_a_command_that_cannot_start_records_nothing(self) -> None:
        result = self.verify("no-such-command-here --flag")
        self.assertEqual(127, result.returncode)
        self.assertIn("nothing recorded", result.stderr)
        self.assertEqual([], verify_record.load(str(self.repo)))
        self.assert_blocked("no check has been recorded")

    def test_a_program_that_is_not_there_records_nothing_in_either_form(self) -> None:
        result = self.verify("no-such-command-here", "--flag")
        self.assertEqual(127, result.returncode)
        self.assertIn("nothing recorded", result.stderr)
        self.assertEqual([], verify_record.load(str(self.repo)))

    def test_a_check_that_ran_and_exited_127_is_a_failure(self) -> None:
        # it ran (and wrote its report) before a later step was missing: that is a failure
        self.assertEqual(127, self.verify("echo r > report.txt; exit 127").returncode)
        self.verify("true")
        self.assert_blocked("failed (exit 127)")
        self.assertIn("report.txt", verify_record.known_outputs(str(self.repo)))

    def assert_recorded_failure(self, command: str, code: int, **kwargs) -> None:
        result = self.verify(command, **kwargs)
        self.assertEqual(code, result.returncode, result.stderr)
        self.assertNotIn("nothing recorded", result.stderr)
        records = verify_record.load(str(self.repo))
        self.assertTrue(records, "nothing was recorded")
        self.assertEqual((command, code), (records[-1]["command"], records[-1]["exit"]))

    def test_a_first_word_the_shell_resolves_is_a_check_that_ran(self) -> None:
        for command in (
            "exit 127",
            "if true; then exit 127; fi",
            "exec sh -c 'exit 127'",
            "{ exit 127; }",
            "${AITK_UNSET_FOR_TEST:-sh} -c 'exit 127'",
        ):
            with self.subTest(command=command):
                self.assert_recorded_failure(command, 127)
        with self.subTest(command="exit 126"):
            self.assert_recorded_failure("exit 126", 126)

    def test_a_first_word_with_an_expansion_is_a_check_that_ran(self) -> None:
        home = Path(self.temporary.name).resolve() / "home"
        home.mkdir()
        tool = home / "tool"
        tool.write_text("#!/bin/sh\nexit 127\n")
        tool.chmod(0o755)
        self.assert_recorded_failure("~/tool", 127, env={"HOME": str(home)})

    def test_a_path_assignment_in_front_is_a_check_that_ran(self) -> None:
        self.write("bin/tool", "#!/bin/sh\nexit 127\n")
        (self.repo / "bin" / "tool").chmod(0o755)
        self.assert_recorded_failure("PATH=./bin:$PATH tool", 127)

    def test_the_argv_form_that_exits_127_is_a_failure(self) -> None:
        result = self.verify("sh", "-c", "exit 127")
        self.assertEqual(127, result.returncode)
        self.assertNotIn("nothing recorded", result.stderr)
        records = verify_record.load(str(self.repo))
        self.assertTrue(records, "nothing was recorded")
        self.assertEqual(127, records[-1]["exit"])

    def test_a_stale_pass_cannot_survive_a_127_of_the_same_command(self) -> None:
        check = "exit ${AITK_CODE:-0}"
        self.assertEqual(0, self.verify(check).returncode)
        self.assertIsNone(self.gate())
        self.assertEqual(127, self.verify(check, env={"AITK_CODE": "127"}).returncode)
        self.assert_blocked("failed (exit 127)")

    def test_a_script_that_is_missing_or_not_executable_records_nothing(self) -> None:
        self.write("check.sh", "#!/bin/sh\nexit 0\n")
        for command, code in (("./missing.sh", 127), ("./check.sh", 126)):
            with self.subTest(command=command):
                result = self.verify(command)
                self.assertEqual(code, result.returncode)
                self.assertIn("nothing recorded", result.stderr)
                self.assertEqual([], verify_record.load(str(self.repo)))

    @unittest.skipUnless(os.path.exists("/bin/dash"), "needs /bin/dash")
    def test_a_dash_sh_reads_the_same_way(self) -> None:
        shims = Path(self.temporary.name).resolve() / "shims"
        shims.mkdir()
        (shims / "sh").symlink_to("/bin/dash")
        env = {"PATH": f"{shims}{os.pathsep}{os.environ.get('PATH', '')}"}
        self.write("check.sh", "#!/bin/sh\nexit 0\n")
        self.assert_recorded_failure("exit 127", 127, env=env)
        for command, code in (("no-such-command-here", 127), ("./check.sh", 126)):
            with self.subTest(command=command):
                result = self.verify(command, env=env)
                self.assertEqual(code, result.returncode)
                self.assertIn("nothing recorded", result.stderr)
        self.assertEqual(1, len(verify_record.load(str(self.repo))))

    def test_an_unquoted_compound_command_is_refused(self) -> None:
        (self.repo / "sub").mkdir()
        for command in (("cd", "sub"), ("ulimit", "-n", "1024"), ("umask", "022"), ("cd",)):
            with self.subTest(command=command):
                result = self.verify(*command)
                self.assertEqual(2, result.returncode)
                self.assertIn("one quoted argument", result.stderr)
                self.assertEqual([], verify_record.load(str(self.repo)))
        # a quoted compound runs
        self.assertEqual(0, self.verify("cd sub && true").returncode)

    def test_outputs_that_are_gone_are_forgotten(self) -> None:
        self.verify("echo r > report.txt")
        (self.repo / "report.txt").unlink()
        self.verify("true")
        self.assertNotIn("report.txt", verify_record.known_outputs(str(self.repo)))

    def test_outputs_that_are_not_a_list_are_ignored(self) -> None:
        record = {"base": "x", "changes": {}, "command": "true", "exit": 0, "outputs": 5}
        (self.repo / ".ai-toolkit").mkdir(exist_ok=True)
        (self.repo / ".ai-toolkit" / "verify.json").write_text(json.dumps({"records": [record], "outputs": "report.txt"}))
        self.assertEqual(frozenset(), verify_record.known_outputs(str(self.repo)))
        self.assertEqual(0, self.verify("true").returncode)

    def test_a_check_before_the_first_commit_counts_once_it_is_committed(self) -> None:
        fresh = Path(self.temporary.name) / "fresh"
        fresh.mkdir()
        run = lambda *a: subprocess.run(a, cwd=fresh, env=clean_env(), check=True, capture_output=True)
        run("git", "init", "-q", "-b", "feature")
        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test")
        (fresh / "app.py").write_text("print('one')\n")
        self.assertEqual(0, self.verify("true", cwd=fresh).returncode)
        run("git", "add", "app.py")
        run("git", "commit", "-q", "-m", "first")
        self.assertIsNone(self.gate(cwd=fresh))

    def test_status_without_a_record_exits_1(self) -> None:
        status = subprocess.run(
            [sys.executable, str(VERIFY), "--status"], cwd=self.repo, env=clean_env(), capture_output=True, text=True
        )
        self.assertEqual(1, status.returncode)
        self.assertIn("no check has been recorded", status.stderr)

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
