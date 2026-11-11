"""install.sh: the Codex agent links and the hook-trust check in Codex's AGENTS.md."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
BEGIN = "# >>> ai-toolkit hook check >>>"
END = "# <<< ai-toolkit hook check <<<"


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name).resolve()
        self.codex = self.home / ".codex"
        self.agents_md = self.codex / "AGENTS.md"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_install(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex)}
        env.pop("CLAUDE_CONFIG_DIR", None)
        return subprocess.run(["sh", str(INSTALL), *args], env=env, capture_output=True, text=True, check=False)

    def test_install_links_agents_and_adds_the_check_once(self) -> None:
        self.assertEqual(0, self.run_install().returncode)
        for agent in (ROOT / "agents" / "codex").glob("*.toml"):
            link = self.codex / "agents" / agent.name
            self.assertTrue(link.is_symlink(), link)
            self.assertEqual(agent, Path(os.readlink(link)))
        text = self.agents_md.read_text()
        self.assertEqual(1, text.count(BEGIN))
        self.assertIn("AI Toolkit Rules", text)
        self.assertIn("/hooks", text)
        again = self.run_install()
        self.assertEqual(0, again.returncode)
        self.assertNotIn("added the hook check", again.stdout)
        self.assertEqual(text, self.agents_md.read_text())

    def test_the_users_own_guidance_is_kept_and_uninstall_removes_only_the_block(self) -> None:
        self.codex.mkdir()
        mine = "# My rules\n\nPrefer small commits.\nno trailing newline here"
        self.agents_md.write_text(mine)
        self.run_install()
        text = self.agents_md.read_text()
        self.assertTrue(text.startswith(mine + "\n"), text)
        self.assertIn(BEGIN, text)
        self.assertEqual(0, self.run_install("--uninstall").returncode)
        self.assertEqual(mine + "\n", self.agents_md.read_text())
        self.assertFalse(any((self.codex / "agents").glob("*.toml")))

    def test_an_outdated_block_is_replaced_in_place_of_a_second_one(self) -> None:
        self.codex.mkdir()
        self.agents_md.write_text(f"before\n{BEGIN}\nold wording\n{END}\nafter\n")
        self.run_install()
        text = self.agents_md.read_text()
        self.assertEqual(1, text.count(BEGIN))
        self.assertNotIn("old wording", text)
        self.assertIn("before\nafter\n", text)

    def test_a_block_missing_its_end_marker_is_left_alone(self) -> None:
        self.codex.mkdir()
        broken = f"mine\n{BEGIN}\nold wording\nthe user's own text below\n"
        self.agents_md.write_text(broken)
        install = self.run_install()
        self.assertEqual(0, install.returncode, install.stderr)
        self.assertIn("no end marker", install.stderr)
        self.assertEqual(broken, self.agents_md.read_text())
        uninstall = self.run_install("--uninstall")
        self.assertIn("no end marker", uninstall.stderr)
        self.assertEqual(broken, self.agents_md.read_text())

    def test_a_symlinked_agents_md_is_written_through(self) -> None:
        self.codex.mkdir()
        real = self.home / "dotfiles-AGENTS.md"
        real.write_text("mine\n")
        self.agents_md.symlink_to(real)
        self.run_install()
        self.assertTrue(self.agents_md.is_symlink())
        self.assertIn(BEGIN, real.read_text())
        self.run_install("--uninstall")
        self.assertEqual("mine\n", real.read_text())

    def test_a_file_that_is_not_its_link_is_left_alone(self) -> None:
        agents = self.codex / "agents"
        agents.mkdir(parents=True)
        (agents / "reviewer.toml").write_text("mine\n")
        result = self.run_install()
        self.assertIn("skipped", result.stderr)
        self.assertEqual("mine\n", (agents / "reviewer.toml").read_text())
        self.run_install("--uninstall")
        self.assertEqual("mine\n", (agents / "reviewer.toml").read_text())


if __name__ == "__main__":
    unittest.main()
