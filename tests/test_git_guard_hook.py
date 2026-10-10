"""The git guard (aitk/hooks/git_guard.py) behind hooks/prevent-project-commit.sh.

Every case runs the wrapper end to end with a synthetic PreToolUse payload in a
scratch repository under a fresh temporary directory, and checks the exit code:
0 allows, 2 blocks. The cases port hooks/test-prevent-project-commit.sh and add
the P1 ones: commands behind `timeout`, `nohup`, `xargs` and `nice`,
newline-separated commands, `git add <state> && git commit`, and `gh pr ready`
and `gh pr merge` without the user's AITK_PR_READY=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from aitk.project_state import STATE_FILES


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "hooks" / "prevent-project-commit.sh"
OVERRIDES = ("AITK_PR_READY", "SKIP_PR_GATE")


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def base_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in OVERRIDES}
    env.pop("PYTHONPATH", None)
    return env


# Blocked in a repository where PROJECT.md is staged.
STAGED_BLOCK = (
    "git commit -m state",
    "cd {repo} && git commit -m state",
    "cd / && git -C {repo_rel} commit -m state",
    "cd / && env -C {repo} git commit -m state",
    "cd / && env --chdir={repo} git commit -m state",
    "env -C / true; git commit -m state",
    "cd / && GIT_DIR={repo}/.git GIT_WORK_TREE={repo} git commit -m state",
    "git --work-tree={repo} --git-dir={repo}/.git commit -m state",
    "git -c alias.ci=commit ci -m state",
    "git ci -m state",
    'f(){{ git "$@"; }}; f commit -m state',
    "g=git; $g commit -m state",
)

# Blocked in a repository with nothing staged in its default index.
CLEAN_BLOCK = (
    "GIT_INDEX_FILE={index} git commit -m state",
    # --no-verify, -n and signing overrides, in every spelling and wrapper
    "git commit --no-verify -m bad",
    "git commit --no-verif -m bad",
    "git commit --no-veri -m bad",
    "/usr/bin/git commit --no-verify -m bad",
    "git --no-pager commit --no-verify -m bad",
    "command git commit --no-verify -m bad",
    "env FOO=bar git commit --no-verify -m bad",
    "( git commit --no-verify -m bad )",
    "if git commit --no-verify -m bad; then echo ok; fi",
    "for x in 1; do git commit --no-verify -m bad; done",
    "sudo git commit --no-verify -m bad",
    "bash -lc 'git commit --no-verify -m bad'",
    "bash -lc -- 'git commit --no-verify -m bad'",
    "sh -c 'git commit --no-verify -m bad'",
    "sh -c -- 'git commit --no-verify -m bad'",
    "sh -c 'git \"$1\" --no-verify -m bad' x commit",
    'sh -c "git \\"\\$1\\" --no-verify -m bad" x commit',
    "zsh -c 'git commit --no-verify -m bad'",
    "zsh -c -- 'git commit --no-verify -m bad'",
    "sh -c 'git \"$@\"' sh commit --no-verify -m bad",
    'sh -c "git \\"\\$@\\"" sh commit --no-verify -m bad',
    "bash -lc 'f(){{ git commit --no-verify -m bad; }}; f'",
    'f(){{ git "$@"; }}; f commit --no-verify -m bad',
    'function f {{ git "$@"; }}; f commit --no-verify -m bad',
    'function f() {{ git "$@"; }}; f commit --no-verify -m bad',
    "bash -lc 'f(){{ git \"$@\"; }}; f commit --no-verify -m bad'",
    "bash -lc 'function f {{ git \"$@\"; }}; f commit --no-verify -m bad'",
    "g=git; $g commit --no-verify -m bad",
    "eval 'git commit --no-verify -m bad'",
    "git${{IFS}}commit --no-verify -m bad",
    "git${{IFS}} commit --no-verify -m bad",
    "git -c user.name=Test commit -n -m bad",
    "git -c alias.nv='commit --no-verify' nv -m bad",
    "git -c alias.nvshell='!git commit --no-verify' nvshell -m bad",
    "git -c alias.a='!git nv' -c alias.nv='commit --no-verify' a --allow-empty -m bad",
    "git -c alias.outer='!git -c alias.inner=\"commit --no-verify\" inner' outer --allow-empty -m bad",
    "git nv -m bad",
    "git nvshell -m bad",
    "GIT_CONFIG_GLOBAL={global_config} git bad -m bypass",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.nv GIT_CONFIG_VALUE_0='commit --no-verify' git nv -m bad",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.nv GIT_CONFIG_VALUE_0='commit --no-verify'; git nv -m bad",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null; git commit -m bad",
    "A='commit --no-verify' git --config-env=alias.nv=A nv -m bad",
    "export A='commit --no-verify'; git --config-env=alias.nv=A nv -m bad",
    "git -c core.hooksPath=/dev/null commit -m bad",
    "git -c commit.gpgsign=false commit -m bad",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m bad",
    "HP=/dev/null git --config-env=core.hooksPath=HP commit -m bad",
    "GS=false git --config-env=commit.gpgsign=GS commit -m bad",
    "git -C {repo} commit --no-verify -m bad",
    "git commit -nm bad",
    "git commit --no-gpg-sign -m bad",
    "git commit --no-gpg-sig -m bad",
    "git commit --no-g -m bad",
    # force-push and delete of main, and --no-verify on push
    "git push -f",
    "( git push -f )",
    "( git push --force )",
    "( git push -f origin )",
    "git -C {repo} push -f",
    "git push -f origin",
    "git push --force-w origin main",
    "git push --force-wi origin main",
    "git push --force-with origin main",
    "git push --force-with-l origin main",
    "git push --force-with-le origin main",
    "git push --force-with-lea origin main",
    "git push --force-with-leas origin main",
    "git push -f origin main",
    "git push -uf origin main",
    "git push --force-with-lease=refs/heads/main origin main",
    "git push -f origin HEAD",
    "git push --force --all origin",
    "git push --mirror --force origin",
    "git push --no-verify origin feature",
    "git push --no-verif origin feature",
    "git push --no-veri origin feature",
    "git -c alias.fpm='push --force origin main' fpm",
    "git -c alias.fpshell='!f(){{ git push --force origin main; }}; f' fpshell",
    "git fpm",
    "git fpshell",
    "git -c core.hooksPath=/dev/null push origin feature",
    "git push origin :main",
    "git push --delete origin main",
    "git push --del origin main",
    "git push --force origin :",
    "git push origin +:",
    "git push origin +main",
    "git push origin +HEAD:main",
    # command and process substitution
    "echo `git commit --no-verify -m bad`",
    ': "$(git commit --no-verify -m bad)"',
    "cat <(git commit --no-verify -m bad)",
    ': "$(git${{IFS}}commit --no-verify -m bad)"',
    "echo `git${{IFS}}commit --no-verify -m bad`",
    "cat <(git${{IFS}}commit --no-verify -m bad)",
    ': "$(git -c core.hooksPath=/dev/null commit -m bad)"',
    ': "$(g=git; $g commit --no-verify -m bad)"',
    # P1: wrappers that run the rest of the line, and newline-separated commands
    "timeout 60 git commit --no-verify -m bad",
    "timeout -s KILL 60 git push -f origin main",
    "nohup git push -f origin main",
    "nohup git commit -n -m bad &",
    "printf 'x\\n' | xargs git commit --no-verify -m",
    "xargs -n 1 git push --force origin main < /dev/null",
    "nice git commit --no-verify -m bad",
    "nice -n 5 git push -f origin main",
    "echo first\ngit commit --no-verify -m bad",
    "git status\ngit push -f origin main",
    "true\n\ntimeout 30 git commit -n -m bad",
    # P1: state files and .ai-toolkit/ added earlier in the same command
    "git add PROJECT.md && git commit -m state",
    "git add PROJECT.md; git commit -m state",
    "git add -A && git commit -m everything",
    "git add . && git commit -m everything",
    "git add .ai-toolkit/config.json && git commit -m config",
    "git add -f .ai-toolkit/config.json && git commit -m config",
    "git add notes.txt PLAN.md && git commit -m state",
    "git add PROJECT.md\ngit commit -m state",
    "timeout 60 git add PROJECT.md && nice git commit -m state",
    "git commit -m first; git add PROJECT.md && git commit -m state",
    # A command that mentions git and does not parse
    "git commit -m 'unbalanced",
)

CLEAN_ALLOW = (
    "echo --no-verify",
    "echo git commit --no-verify",
    "git commit -m 'mention -n flag'",
    "git commit -mnope",
    "git push -uf origin feature",
    "git push --force-with-lease origin feature",
    "git add notes.txt && git commit -m notes",
    "timeout 60 git commit -m fine",
    "nohup git push origin feature",
    "nice -n 5 git status",
    "echo first\ngit commit -m fine",
    "echo 'unbalanced",
    "ls -la",
)

PR_PUBLISH_BLOCK = (
    "gh pr merge 12 --squash",
    "gh pr ready 12",
    "gh pr merge",
    "gh -R owner/repo pr merge 12",
    "gh pr merge --auto --squash 12",
    "SKIP_PR_GATE=1 gh pr ready 12",
    "SKIP_PR_GATE=1 gh pr merge 12",
    "timeout 30 gh pr merge 12",
    "nohup gh pr ready 12",
    "echo ok\ngh pr ready 12",
    "git status && gh pr merge 12",
    "bash -c 'gh pr merge 12'",
    "env FOO=1 gh pr ready 12",
    "gh pr merge 'unbalanced",
)

PR_PUBLISH_ALLOW = (
    "AITK_PR_READY=1 gh pr merge 12 --squash",
    "AITK_PR_READY=1 gh pr ready 12",
    "env AITK_PR_READY=1 gh pr ready 12",
    "gh pr ready 12 --undo",
    "gh pr merge --help",
    "gh pr view 12",
    "gh pr checks 12",
    "gh pr create --draft --title t --body b",
    "echo gh pr merge",
)


class GitGuardHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        base = Path(cls.temporary.name).resolve()
        cls.global_config = base / "global.gitconfig"
        cls.staged = cls.make_repo(base / "staged")
        cls.clean = cls.make_repo(base / "clean")
        cls.alt_index = base / "alt.index"

        # PROJECT.md staged in the default index of one repository, and every
        # state file staged in its own non-default index.
        (cls.staged / "PROJECT.md").write_text("state\n")
        git(cls.staged, "add", "PROJECT.md")
        for state_file in STATE_FILES:
            (cls.staged / state_file).write_text("state\n")
            index = {"GIT_INDEX_FILE": str(cls.staged / f"{state_file}.index")}
            git(cls.staged, "read-tree", "--empty", env=index)
            git(cls.staged, "add", state_file, env=index)

        # The other repository stages nothing by default; PROJECT.md sits in an
        # alternate index, and state files and .ai-toolkit/ wait unstaged.
        for name in ("PROJECT.md", "PLAN.md", "notes.txt"):
            (cls.clean / name).write_text("state\n")
        (cls.clean / ".ai-toolkit").mkdir()
        (cls.clean / ".ai-toolkit" / "config.json").write_text("{}\n")
        git(cls.clean, "add", "PROJECT.md", env={"GIT_INDEX_FILE": str(cls.alt_index)})

        git(
            cls.clean,
            "config",
            "--global",
            "alias.bad",
            "commit --no-verify",
            env={"GIT_CONFIG_GLOBAL": str(cls.global_config)},
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def make_repo(cls, path: Path) -> Path:
        path.mkdir()
        git(path, "init", "-q", "-b", "main")
        git(path, "config", "user.email", "test@example.com")
        git(path, "config", "user.name", "Test")
        git(path, "config", "alias.ci", "commit")
        git(path, "config", "alias.nv", "commit --no-verify")
        git(path, "config", "alias.nvshell", "!git commit --no-verify")
        git(path, "config", "alias.fpm", "push --force origin main")
        git(path, "config", "alias.fpshell", "!f(){ git push --force origin main; }; f")
        return path

    def expand(self, template: str, repo: Path) -> str:
        return template.format(
            repo=repo,
            repo_rel=str(repo).lstrip("/"),
            index=self.alt_index,
            global_config=self.global_config,
        )

    def run_hook(
        self,
        command: str,
        cwd: Path,
        env: dict[str, str] | None = None,
        wrapper_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
        return subprocess.run(
            ["bash", str(WRAPPER)],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            env=wrapper_env if wrapper_env is not None else {**base_env(), **(env or {})},
            timeout=60,
        )

    def assert_cases(self, templates: tuple[str, ...], repo: Path, expected: int, **kwargs) -> None:
        for template in templates:
            command = self.expand(template, repo)
            with self.subTest(command=command, expected=expected):
                result = self.run_hook(command, repo, **kwargs)
                self.assertEqual(expected, result.returncode, result.stderr)
                if expected == 2:
                    self.assertIn("BLOCKED", result.stderr)

    def test_staged_state_files_block_a_commit(self) -> None:
        self.assert_cases(STAGED_BLOCK, self.staged, 2)

    def test_every_state_file_in_a_non_default_index_blocks(self) -> None:
        templates = tuple(
            f"GIT_INDEX_FILE={{repo}}/{state_file}.index git commit -m state" for state_file in STATE_FILES
        )
        self.assert_cases(templates, self.staged, 2)

    def test_bypasses_and_force_pushes_block(self) -> None:
        self.assert_cases(CLEAN_BLOCK, self.clean, 2)

    def test_ordinary_commands_are_allowed(self) -> None:
        self.assert_cases(CLEAN_ALLOW, self.clean, 0)
        self.assert_cases(("echo --no-verify", "echo git commit --no-verify"), self.staged, 0)

    def test_state_commit_names_the_files(self) -> None:
        result = self.run_hook("git add .ai-toolkit/config.json && git commit -m config", self.clean)
        self.assertEqual(2, result.returncode)
        self.assertIn(".ai-toolkit/config.json", result.stderr)
        self.assertIn("stay out of commits", result.stderr)

    def test_pr_ready_and_merge_need_the_users_override(self) -> None:
        self.assert_cases(PR_PUBLISH_BLOCK, self.clean, 2)
        self.assert_cases(PR_PUBLISH_BLOCK, self.clean, 2, env={"SKIP_PR_GATE": "1"})
        self.assert_cases(PR_PUBLISH_ALLOW, self.clean, 0)
        self.assert_cases(
            ("gh pr merge 12 --squash", "gh pr ready 12", "nohup gh pr ready 12"),
            self.clean,
            0,
            env={"AITK_PR_READY": "1"},
        )
        self.assert_cases(("gh pr ready 12",), self.clean, 2, env={"AITK_PR_READY": "0"})
        merge = self.run_hook("gh pr merge 12", self.clean)
        self.assertIn("ask the user", merge.stderr)
        self.assertNotIn("AITK_PR_READY", merge.stderr)

    def test_missing_python_fails_closed_on_guarded_commands(self) -> None:
        with tempfile.TemporaryDirectory() as bin_dir:
            for tool in ("bash", "cat", "dirname"):
                found = shutil.which(tool)
                self.assertIsNotNone(found, tool)
                os.symlink(found, Path(bin_dir) / tool)
            env = {"PATH": bin_dir, "HOME": str(self.clean)}
            blocked = self.run_hook("git commit -m fine", self.clean, wrapper_env=env)
            self.assertEqual(2, blocked.returncode, blocked.stderr)
            self.assertIn("python3 is not on PATH", blocked.stderr)
            pr = self.run_hook("gh pr merge 12", self.clean, wrapper_env=env)
            self.assertEqual(2, pr.returncode, pr.stderr)
            allowed = self.run_hook("ls -la", self.clean, wrapper_env=env)
            self.assertEqual(0, allowed.returncode, allowed.stderr)

    def test_a_module_in_the_project_directory_cannot_shadow_the_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            git(project, "init", "-q", "-b", "main")
            (project / "aitk").mkdir()
            (project / "aitk" / "__init__.py").write_text("raise SystemExit(0)\n")
            (project / "json.py").write_text("raise SystemExit(0)\n")
            result = subprocess.run(
                ["bash", str(WRAPPER)],
                input=json.dumps({"tool_input": {"command": "git commit --no-verify -m x"}, "cwd": str(project)}),
                text=True,
                capture_output=True,
                check=False,
                cwd=project,
                env=base_env(),
                timeout=60,
            )
            self.assertEqual(2, result.returncode, result.stderr)

    def test_guard_import_loads_neither_doctor_nor_installer(self) -> None:
        probe = (
            "import json, sys\n"
            "import aitk.hooks.git_guard, aitk.hooks.review_gate\n"
            "print(json.dumps(sorted(name for name in sys.modules if name.startswith('aitk'))))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
            env={**base_env(), "PYTHONPATH": str(ROOT)},
        )
        loaded = json.loads(result.stdout)
        self.assertIn("aitk.project_state", loaded)
        for heavy in ("aitk.doctor", "aitk.installer", "aitk.build", "aitk.conformance", "aitk.model_routing"):
            self.assertNotIn(heavy, loaded)


if __name__ == "__main__":
    unittest.main()
