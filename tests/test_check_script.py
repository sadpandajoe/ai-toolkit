"""scripts/check.py: the runtime-free repository checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check.py"
spec = importlib.util.spec_from_file_location("check_script", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class CheckTests(unittest.TestCase):
    def fixture(self) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        (tmp / "skills" / "demo").mkdir(parents=True)
        (tmp / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\ndescription: A demo.\n---\n\nSee [notes](notes.md).\n"
        )
        (tmp / "skills" / "demo" / "notes.md").write_text("notes\n")
        (tmp / "hooks").mkdir()
        (tmp / "hooks" / "guard.sh").write_text("#!/bin/bash\n")
        (tmp / "hooks" / "hooks.json").write_text(json.dumps({"command": "bash hooks/guard.sh"}))
        for manifest in check.PLUGIN_MANIFESTS:
            (tmp / manifest).parent.mkdir(exist_ok=True)
            (tmp / manifest).write_text(json.dumps({"skills": ["./skills/"], "hooks": "./hooks/hooks.json"}))
        return tmp

    def test_a_clean_tree_passes_every_check(self) -> None:
        root = self.fixture()
        for label, run in check.CHECKS:
            self.assertEqual([], run(root), label)

    def test_a_broken_link_fails(self) -> None:
        root = self.fixture()
        (root / "skills" / "demo" / "notes.md").unlink()
        self.assertEqual(["skills/demo/SKILL.md -> notes.md"], check.check_markdown_links(root))

    def test_provider_fields_in_frontmatter_fail(self) -> None:
        root = self.fixture()
        (root / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: d\nmodel: opus\n---\n")
        self.assertEqual(1, len(check.check_skill_frontmatter(root)))

    def test_a_manifest_path_or_hook_script_that_is_missing_fails(self) -> None:
        root = self.fixture()
        (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"skills": ["./nowhere/"]}))
        (root / "hooks" / "guard.sh").unlink()
        problems = check.check_plugin_manifests(root)
        self.assertIn(".codex-plugin/plugin.json: skills path ./nowhere/ does not exist", problems)
        self.assertIn("hooks/hooks.json: hooks/guard.sh does not exist", problems)

    def test_personal_paths_and_echoed_secrets_fail(self) -> None:
        root = self.fixture()
        (root / "skills" / "demo" / "notes.md").write_text("cd /Users/someone/code\n")
        (root / "hooks" / "guard.sh").write_text('echo "$API_TOKEN"\n')
        (root / "leak.py").write_text("print(api_token)\n")
        self.assertEqual(["skills/demo/notes.md"], check.check_personal_paths(root))
        self.assertEqual(["hooks/guard.sh", "leak.py"], check.check_secret_output(root))

    def test_this_repository_passes(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stdout)


if __name__ == "__main__":
    unittest.main()
