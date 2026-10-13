"""hooks/pre-push-validate.sh: blocks a push on failed or overdue checks.

Each case runs the hook with a synthetic PreToolUse payload against a scratch
repository whose `origin/main` is behind HEAD, with stub `pre-commit` and
`pytest` executables and a PATH built from symlinks, so the result does not
depend on what the machine has installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "pre-push-validate.sh"
TOOLS = ("bash", "cat", "dirname", "env", "git", "mktemp", "python3", "rm", "sleep")

STUB = """#!/bin/bash
case "${{{variable}:-pass}}" in
    fail) echo "{name}: 1 problem found" >&2; exit 1 ;;
    sleep) exec sleep 30 ;;
esac
exit 0
"""


def git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


class PrePushHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        base = Path(cls.temporary.name).resolve()
        origin = base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        cls.repo = base / "work"
        cls.repo.mkdir()
        git(cls.repo, "init", "-q", "-b", "main")
        (cls.repo / "README.md").write_text("readme\n")
        (cls.repo / ".pre-commit-config.yaml").write_text("repos: []\n")
        git(cls.repo, "add", "README.md", ".pre-commit-config.yaml")
        git(cls.repo, "commit", "-q", "-m", "base")
        git(cls.repo, "remote", "add", "origin", str(origin))
        git(cls.repo, "push", "-q", "-u", "origin", "main")
        (cls.repo / "app.py").write_text("VALUE = 1\n")
        (cls.repo / "tests").mkdir()
        (cls.repo / "tests" / "test_app.py").write_text("def test_value():\n    assert True\n")
        git(cls.repo, "add", "app.py", "tests/test_app.py")
        git(cls.repo, "commit", "-q", "-m", "change")

        # The repo's pinned pytest, untracked.
        venv_bin = cls.repo / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        cls.write_stub(venv_bin / "pytest", "STUB_PYTEST", "pytest")

        cls.stubs = base / "stubs"
        cls.stubs.mkdir()
        cls.write_stub(cls.stubs / "pre-commit", "STUB_PRECOMMIT", "pre-commit")
        cls.bins: dict[tuple[str, ...], Path] = {}
        cls.base = base

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @staticmethod
    def write_stub(path: Path, variable: str, name: str) -> None:
        path.write_text(STUB.format(variable=variable, name=name))
        path.chmod(0o755)

    def tool_dir(self, tools: tuple[str, ...]) -> Path:
        if tools not in self.bins:
            directory = Path(tempfile.mkdtemp(dir=self.base, prefix="bin-"))
            for tool in tools:
                found = shutil.which(tool)
                if found is None:
                    self.skipTest(f"{tool} is not installed")
                os.symlink(found, directory / tool)
            self.bins[tools] = directory
        return self.bins[tools]

    def run_hook(
        self,
        command: str,
        *,
        stubs: bool = True,
        tools: tuple[str, ...] = TOOLS + ("timeout",),
        **env: str,
    ) -> subprocess.CompletedProcess[str]:
        path = [str(self.tool_dir(tools))]
        if stubs:
            path.insert(0, str(self.stubs))
        environment = {"PATH": os.pathsep.join(path), "HOME": str(self.base), **env}
        payload = json.dumps({"tool_input": {"command": command}, "cwd": str(self.repo)})
        return subprocess.run(
            [shutil.which("bash"), str(HOOK)],
            input=payload,
            text=True,
            capture_output=True,
            env=environment,
            check=False,
            timeout=120,
        )

    def assert_blocked(self, result: subprocess.CompletedProcess[str], reason: str) -> None:
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("BLOCKED: pre-push validation failed", result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        self.assertNotIn("SKIP_PRECHECK", result.stderr)
        self.assertEqual("", result.stdout)

    def test_other_commands_exit_quietly(self) -> None:
        for command in ("git status", "echo push", "git log --oneline", "ls"):
            with self.subTest(command=command):
                result = self.run_hook(command, STUB_PRECOMMIT="fail")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)

    def test_passing_checks_allow_the_push(self) -> None:
        result = self.run_hook("git push origin main")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_failed_checks_block_without_a_bypass_recipe(self) -> None:
        self.assert_blocked(self.run_hook("git push", STUB_PRECOMMIT="fail"), "pre-commit failed")
        self.assert_blocked(self.run_hook("git push", STUB_PYTEST="fail"), "pytest failed")
        self.assert_blocked(
            self.run_hook("cd . && timeout 60 git push origin main", STUB_PRECOMMIT="fail"),
            "pre-commit failed",
        )

    def test_a_check_past_its_budget_blocks(self) -> None:
        for tools in (TOOLS + ("timeout",), TOOLS):
            with self.subTest(timeout_binary="timeout" in tools):
                lint = self.run_hook(
                    "git push", tools=tools, STUB_PRECOMMIT="sleep", AITK_PRECHECK_LINT_BUDGET="2"
                )
                self.assert_blocked(lint, "pre-commit did not finish within 2s")
                tests = self.run_hook(
                    "git push", tools=tools, STUB_PYTEST="sleep", AITK_PRECHECK_TEST_BUDGET="2"
                )
                self.assert_blocked(tests, "pytest did not finish within 2s")

    def test_budgets_fit_inside_the_hook_timeout_and_only_go_down(self) -> None:
        script = HOOK.read_text()
        lint = int(re.search(r"budget (\d+) \"\$\{AITK_PRECHECK_LINT_BUDGET", script).group(1))
        tests = int(re.search(r"budget (\d+) \"\$\{AITK_PRECHECK_TEST_BUDGET", script).group(1))
        grace = int(re.search(r"^GRACE=(\d+)$", script, re.M).group(1))
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"]
        outer = next(
            handler["timeout"]
            for group in hooks
            for handler in group["hooks"]
            if "pre-push-validate.sh" in handler["command"]
        )
        self.assertLess(lint + tests + 2 * grace, outer)
        function = re.search(r"^budget\(\) \{\n.*?^\}\n", script, re.M | re.S).group(0)
        for override, expected in (("", "180"), ("60", "60"), ("999", "180"), ("0", "180"), ("x", "180")):
            with self.subTest(override=override):
                result = subprocess.run(
                    ["bash", "-c", function + 'budget 180 "$1"', "budget", override],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertEqual(expected, result.stdout.strip())

    def test_skip_precheck_counts_only_as_the_users_prefix_on_the_push(self) -> None:
        for command in (
            "SKIP_PRECHECK=1 git push origin main",
            "env SKIP_PRECHECK=1 git push",
            "git status && SKIP_PRECHECK=1 git push",
        ):
            with self.subTest(command=command):
                result = self.run_hook(command, STUB_PRECOMMIT="fail")
                self.assertEqual(0, result.returncode, result.stderr)
        for command in (
            "echo SKIP_PRECHECK=1; git push origin main",
            "SKIP_PRECHECK=1 true && git push",
            "git push # SKIP_PRECHECK=1",
            "SKIP_PRECHECK=0 git push",
        ):
            with self.subTest(command=command):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")
        session = self.run_hook("git push", STUB_PRECOMMIT="fail", SKIP_PRECHECK="1")
        self.assertEqual(0, session.returncode, session.stderr)

    def test_warnings_reach_the_model_as_additional_context(self) -> None:
        result = self.run_hook("git push", stubs=False)
        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual("PreToolUse", output["hookSpecificOutput"]["hookEventName"])
        self.assertIn("`pre-commit` not installed", output["hookSpecificOutput"]["additionalContext"])

    def test_missing_python_allows_with_a_visible_warning(self) -> None:
        tools = tuple(tool for tool in TOOLS if tool != "python3")
        result = self.run_hook("git push", tools=tools, STUB_PRECOMMIT="fail")
        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("python3 is not on PATH", context)


if __name__ == "__main__":
    unittest.main()
