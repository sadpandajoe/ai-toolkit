"""The Claude Code and Codex plugins: manifests, the session-start hook, and the
hook commands as each provider runs them.

These cases keep the committed files consistent offline. Whether a provider
really loads the plugin (the rules reach the model, the agents and skills are
listed, a hook fires in a session, Codex hook trust) is the plugin proof in
scripts/plugin-proof.sh, which needs real installs and model access.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import aitk


ROOT = Path(__file__).resolve().parents[1]
MARKER = "# >>> ai-toolkit managed guidance >>>"
OLD_INSTALL = "older `bin/aitk install`"
PLUGIN_VARIABLES = ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT")


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text())


def handlers() -> list[tuple[str, dict]]:
    return [
        (event, handler)
        for event, groups in load("hooks/hooks.json")["hooks"].items()
        for group in groups
        for handler in group["hooks"]
    ]


class PluginManifestTests(unittest.TestCase):
    def test_both_manifests_name_the_plugin_and_carry_the_package_version(self) -> None:
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            with self.subTest(manifest=relative):
                manifest = load(relative)
                self.assertEqual("ai-toolkit", manifest["name"])
                self.assertEqual(aitk.__version__, manifest["version"])

    def test_component_paths_stay_inside_the_plugin_and_exist(self) -> None:
        for relative, keys in (
            (".claude-plugin/plugin.json", ("skills", "agents")),
            (".codex-plugin/plugin.json", ("skills", "hooks")),
        ):
            manifest = load(relative)
            for key in keys:
                values = manifest[key]
                for value in [values] if isinstance(values, str) else values:
                    with self.subTest(manifest=relative, path=value):
                        self.assertTrue(value.startswith("./"))
                        self.assertNotIn("..", Path(value).parts)
                        self.assertTrue((ROOT / value).exists())

    def test_claude_manifest_lists_the_agents_and_the_pgm_skills(self) -> None:
        manifest = load(".claude-plugin/plugin.json")
        agents = sorted(
            f"./{path.relative_to(ROOT).as_posix()}"
            for path in (ROOT / "agents/claude").glob("*.md")
        )
        self.assertEqual(agents, manifest["agents"])
        # Claude Code always scans ./skills/ and adds the directories listed;
        # listing ./skills/ again would load every skill twice.
        self.assertEqual(["./extensions/pgm/skills/"], manifest["skills"])
        self.assertTrue(list((ROOT / "skills").glob("*/SKILL.md")))
        self.assertTrue((ROOT / "extensions/pgm/skills/pgm/SKILL.md").is_file())

    def test_codex_manifest_lists_both_skill_directories(self) -> None:
        self.assertEqual(
            ["./skills/", "./extensions/pgm/skills/"], load(".codex-plugin/plugin.json")["skills"]
        )

    def test_both_plugins_register_hooks_json(self) -> None:
        # Codex reads the path its manifest names. Claude Code loads
        # hooks/hooks.json from that default place, and a manifest `hooks`
        # entry is loaded in addition to it, so naming the file again would
        # register every hook twice.
        self.assertEqual("./hooks/hooks.json", load(".codex-plugin/plugin.json")["hooks"])
        self.assertNotIn("hooks", load(".claude-plugin/plugin.json"))
        self.assertTrue((ROOT / "hooks/hooks.json").is_file())

    def test_marketplace_serves_this_checkout_as_the_one_plugin(self) -> None:
        marketplace = load(".claude-plugin/marketplace.json")
        self.assertEqual("ai-toolkit", marketplace["name"])
        self.assertTrue(marketplace["owner"]["name"])
        self.assertEqual(1, len(marketplace["plugins"]))
        entry = marketplace["plugins"][0]
        self.assertEqual("ai-toolkit", entry["name"])
        self.assertEqual("./", entry["source"])
        # plugin.json's version wins; a copy in the entry could only drift.
        self.assertNotIn("version", entry)


class SessionStartHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name).resolve() / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_hook(
        self, payload: str = '{"source": "startup"}', **variables: str
    ) -> subprocess.CompletedProcess[str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {*PLUGIN_VARIABLES, "CODEX_HOME", "CLAUDE_CONFIG_DIR"}
        }
        env["HOME"] = str(self.home)
        env.update(variables)
        result = subprocess.run(
            ["bash", str(ROOT / "hooks/session-start.sh")],
            input=payload,
            text=True,
            capture_output=True,
            env=env,
            cwd=self.home,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def assert_rules(self, output: str) -> None:
        rules = load("interfaces/guidance.json")["always_on_rules"]
        self.assertTrue(rules)
        for rule in rules:
            self.assertIn((ROOT / rule).read_text().strip(), output)
        self.assertIn(f"{ROOT}/bin/aitk", output)
        # Claude Code keeps 10,000 characters of SessionStart output in context.
        self.assertLess(len(output), 10_000)

    def seed(self, relative: str, text: str) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_claude_gets_every_always_on_rule_and_the_claude_binding(self) -> None:
        output = self.run_hook(CLAUDE_PLUGIN_ROOT=str(ROOT)).stdout
        self.assert_rules(output)
        self.assertIn(f"{ROOT}/config/providers/claude.md", output)
        self.assertNotIn("config/providers/codex.md", output)
        self.assertNotIn(OLD_INSTALL, output)

    def test_codex_gets_every_always_on_rule_and_the_codex_binding(self) -> None:
        # Codex sets PLUGIN_ROOT and, for compatibility, CLAUDE_PLUGIN_ROOT too.
        output = self.run_hook(PLUGIN_ROOT=str(ROOT), CLAUDE_PLUGIN_ROOT=str(ROOT)).stdout
        self.assert_rules(output)
        self.assertIn(f"{ROOT}/config/providers/codex.md", output)
        self.assertNotIn("config/providers/claude.md", output)

    def test_prints_nothing_outside_a_plugin(self) -> None:
        self.seed(".claude/CLAUDE.md", f"{MARKER}\n")
        result = self.run_hook()
        self.assertEqual("", result.stdout)

    def test_warns_about_each_old_install_piece_and_leaves_it_untouched(self) -> None:
        seeds = {
            "claude guidance": (".claude/CLAUDE.md", f"# Mine\n\n{MARKER}\n@/opt/ai-toolkit/build/config/rules/universal.md\n"),
            "codex guidance": (".codex/AGENTS.md", f"{MARKER}\nAI Toolkit is installed at `/opt/ai-toolkit`.\n"),
            "settings hook": (
                ".claude/settings.json",
                json.dumps(
                    {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "matcher": "^Bash$",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": 'bash "/opt/ai-toolkit/hooks/prevent-project-commit.sh"',
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                    indent=2,
                )
                + "\n",
            ),
        }
        for label, (relative, text) in seeds.items():
            with self.subTest(piece=label):
                for leftover in (".claude", ".codex"):
                    for path in sorted((self.home / leftover).rglob("*"), reverse=True):
                        path.unlink() if path.is_file() else path.rmdir()
                path = self.seed(relative, text)
                before = path.read_bytes()
                result = self.run_hook(CLAUDE_PLUGIN_ROOT=str(ROOT))
                self.assertIn(OLD_INSTALL, result.stdout)
                self.assertIn(str(path), result.stdout)
                self.assertIn("docs/MIGRATION.md", result.stdout)
                self.assert_rules(result.stdout)
                self.assertEqual(before, path.read_bytes())

    def test_reads_codex_home_and_claude_config_dir(self) -> None:
        codex = self.seed("custom-codex/AGENTS.md", f"{MARKER}\n")
        claude = self.seed("custom-claude/CLAUDE.md", f"{MARKER}\n")
        output = self.run_hook(
            CLAUDE_PLUGIN_ROOT=str(ROOT),
            CODEX_HOME=str(codex.parent),
            CLAUDE_CONFIG_DIR=str(claude.parent),
        ).stdout
        self.assertIn(str(codex), output)
        self.assertIn(str(claude), output)

    def test_warns_only_when_the_session_starts(self) -> None:
        self.seed(".claude/CLAUDE.md", f"{MARKER}\n")
        for source in ("resume", "clear", "compact"):
            with self.subTest(source=source):
                output = self.run_hook(json.dumps({"source": source}), CLAUDE_PLUGIN_ROOT=str(ROOT)).stdout
                self.assert_rules(output)
                self.assertNotIn(OLD_INSTALL, output)
        output = self.run_hook(json.dumps({"source": "startup"}), CLAUDE_PLUGIN_ROOT=str(ROOT)).stdout
        self.assertIn(OLD_INSTALL, output)

    def test_no_warning_for_the_users_own_guidance_and_hooks(self) -> None:
        self.seed(".claude/CLAUDE.md", "# My instructions\n")
        self.seed(".codex/AGENTS.md", "# My Codex instructions\n")
        self.seed(
            ".claude/settings.json",
            json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-hook.sh"}]}]}}),
        )
        output = self.run_hook(CLAUDE_PLUGIN_ROOT=str(ROOT)).stdout
        self.assertNotIn(OLD_INSTALL, output)


class PluginHookCommandTests(unittest.TestCase):
    """Each hooks.json command as a provider runs it: through a shell, with only
    the variable that provider sets. A command whose script is not found exits
    127, which providers treat as a non-blocking error, so a guard would fail
    open."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.work = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_command(self, command: str, variable: str, payload: dict) -> subprocess.CompletedProcess[str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {*PLUGIN_VARIABLES, "CODEX_HOME", "CLAUDE_CONFIG_DIR"}
        }
        env["HOME"] = str(self.work)
        env[variable] = str(ROOT)
        return subprocess.run(
            ["bash", "-c", command],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            cwd=self.work,
            timeout=120,
            check=False,
        )

    def test_every_command_resolves_its_script_under_either_variable(self) -> None:
        payloads = {
            "SessionStart": {"source": "resume", "cwd": str(self.work)},
            "PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(self.work)},
            "PostToolUse": {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(self.work / "notes.txt")},
                "cwd": str(self.work),
            },
            "Stop": {"stop_hook_active": False, "cwd": str(self.work)},
        }
        for event, handler in handlers():
            self.assertIn(event, payloads)
            for variable in PLUGIN_VARIABLES:
                with self.subTest(command=handler["command"], variable=variable):
                    result = self.run_command(handler["command"], variable, payloads[event])
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_git_guard_blocks_no_verify_under_either_variable(self) -> None:
        guards = [
            handler["command"]
            for event, handler in handlers()
            if event == "PreToolUse" and "prevent-project-commit.sh" in handler["command"]
        ]
        self.assertEqual(1, len(guards))
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit --no-verify -m x"},
            "cwd": str(self.work),
        }
        for variable in PLUGIN_VARIABLES:
            with self.subTest(variable=variable):
                result = self.run_command(guards[0], variable, payload)
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertIn("--no-verify", result.stderr)


if __name__ == "__main__":
    unittest.main()
