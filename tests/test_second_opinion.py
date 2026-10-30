"""scripts/second-opinion.py: the cross-family, read-only review wrapper.

Only command construction is tested here; a real run needs a provider login.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "second-opinion.py"
spec = importlib.util.spec_from_file_location("second_opinion", SCRIPT)
second_opinion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(second_opinion)


class CommandTests(unittest.TestCase):
    def test_claude_code_asks_codex_and_anything_else_asks_claude(self) -> None:
        self.assertEqual("codex", second_opinion.default_provider({"CLAUDECODE": "1"}))
        self.assertEqual("claude", second_opinion.default_provider({}))

    def test_codex_runs_read_only_on_the_pinned_model(self) -> None:
        contract = 'say "hi"'
        command = second_opinion.build_command("codex", "standard", Path("/repo"), contract)
        self.assertEqual(["codex", "exec"], command[:2])
        self.assertEqual("read-only", command[command.index("--sandbox") + 1])
        self.assertEqual("gpt-6.1-sol", command[command.index("--model") + 1])
        self.assertIn('model_reasoning_effort="high"', command)
        # The contract is one TOML basic string, quotes escaped.
        self.assertIn("developer_instructions=" + json.dumps(contract), command)
        self.assertEqual("-", command[-1])

    def test_claude_cannot_write_and_runs_only_read_only_git(self) -> None:
        command = second_opinion.build_command("claude", "deep", Path("/repo"), "contract")
        self.assertEqual("plan", command[command.index("--permission-mode") + 1])
        self.assertEqual("claude-fable-5-1", command[command.index("--model") + 1])
        self.assertEqual("xhigh", command[command.index("--effort") + 1])
        disallowed = command[command.index("--disallowedTools") + 1 : command.index("--tools")]
        self.assertEqual(["Write", "Edit", "NotebookEdit"], disallowed)
        allowed = command[command.index("--allowedTools") + 1 :]
        self.assertTrue(allowed)
        for rule in allowed:
            self.assertRegex(rule, r"^Bash\(git (log|show|diff|blame) \*\)$")
        self.assertIn("--restricted", command)

    def test_prompt_carries_the_brief_and_the_diff(self) -> None:
        prompt = second_opinion.build_prompt("+x\n", "main", "Fixes the race in save().")
        self.assertIn("against main", prompt)
        self.assertIn("Fixes the race in save().", prompt)
        self.assertIn("```diff\n+x\n```", prompt)


class CliTests(unittest.TestCase):
    def run_script(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

    def repo(self) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        git = ["git", "-C", str(tmp), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git[:3], "init", "-q", "-b", "main"], check=True)
        (tmp / "a.txt").write_text("one\n")
        subprocess.run([*git, "add", "a.txt"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "base"], check=True)
        return tmp

    def test_dry_run_shows_the_command_without_the_contract(self) -> None:
        repo = self.repo()
        (repo / "a.txt").write_text("two\n")
        result = self.run_script(repo, "--dry-run", "--via", "claude")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("<reviewer contract>", result.stdout)
        self.assertIn("diff against main", result.stdout)

    def test_no_changes_is_a_usage_error(self) -> None:
        result = self.run_script(self.repo(), "--dry-run")
        self.assertEqual(2, result.returncode)
        self.assertIn("no changes against main", result.stderr)

    def test_outside_a_repository_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(Path(tmp), "--dry-run")
        self.assertEqual(2, result.returncode)


if __name__ == "__main__":
    unittest.main()
