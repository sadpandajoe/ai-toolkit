from __future__ import annotations

import json
from pathlib import Path
import stat
import tomllib
import unittest

import aitk


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_runtime_entrypoints_are_executable(self) -> None:
        for relative in ("bin/aitk", "install.sh", "extensions/pgm/install.sh"):
            mode = stat.S_IMODE((ROOT / relative).stat().st_mode)
            self.assertTrue(mode & stat.S_IXUSR, relative)

    def test_versions_match_across_python_plugin_and_changelog(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        plugin = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        claude_plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(aitk.__version__, project["version"])
        self.assertEqual(aitk.__version__, plugin["version"])
        self.assertEqual(aitk.__version__, claude_plugin["version"])
        self.assertIn(f"## {aitk.__version__}", (ROOT / "CHANGELOG.md").read_text())

    def test_package_exposes_the_aitk_entrypoint(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual("aitk.cli:main", project["scripts"]["aitk"])
        self.assertEqual([], project["dependencies"])

    def test_every_python_package_ships_in_the_wheel(self) -> None:
        listed = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"]
        found = {
            ".".join(path.parent.relative_to(ROOT).parts)
            for path in (ROOT / "aitk").rglob("__init__.py")
            if "__pycache__" not in path.parts
        }
        self.assertEqual(sorted(found), sorted(listed))
        self.assertIn("aitk.hooks", listed)

    def test_ci_runs_the_same_local_gate_with_pinned_actions(self) -> None:
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("run: bin/aitk check", workflow)
        self.assertIn("python -m pip wheel --no-deps --wheel-dir dist .", workflow)
        self.assertNotIn("--no-build-isolation", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("python -m venv", workflow)
        self.assertIn('cd "$RUNNER_TEMP"', workflow)
        self.assertIn("git diff --check", workflow)
        action_lines = [
            line.strip() for line in workflow.splitlines() if "uses: actions/" in line
        ]
        self.assertGreaterEqual(len(action_lines), 2)
        for line in action_lines:
            self.assertRegex(line, r"uses: actions/[a-z-]+@[0-9a-f]{40}(?:\s+#.*)?$")


if __name__ == "__main__":
    unittest.main()
