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
SCRIPT = ROOT / "statusline" / "statusline-command.sh"
ANSI = re.compile(r"\x1b(?:\[[0-9;]*m|\]8;;[^\x1b]*\x1b\\)")


@unittest.skipUnless(shutil.which("jq"), "statusline needs jq")
class StatuslineEffortTests(unittest.TestCase):
    def render(
        self, payload: dict, settings_effort: str | None = "high", raw: bool = False
    ) -> str:
        with tempfile.TemporaryDirectory() as home:
            if settings_effort is not None:
                claude_dir = Path(home) / ".claude"
                claude_dir.mkdir()
                (claude_dir / "settings.json").write_text(
                    json.dumps({"effortLevel": settings_effort})
                )
            env = {**os.environ, "HOME": home}
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
        first = result.stdout.splitlines()[0]
        return first if raw else ANSI.sub("", first)

    def payload(self, **extra: object) -> dict:
        return {
            "model": {"display_name": "Claude Sonnet 5"},
            "workspace": {"current_dir": "/nonexistent"},
            **extra,
        }

    def test_shows_live_session_effort_not_the_settings_default(self):
        for level in ("low", "medium", "xhigh", "max"):
            with self.subTest(level=level):
                line = self.render(
                    self.payload(effort={"level": level}), settings_effort="high"
                )
                self.assertEqual(line, f"Sonnet 5 {level}")

    def test_colors_effort_by_intensity(self):
        expected = {
            "max": "\x1b[31mmax",
            "xhigh": "\x1b[33mxhigh",
            "high": "\x1b[33mhigh",
            "medium": "\x1b[90mmedium",
            "low": "\x1b[90mlow",
        }
        for level, colored in expected.items():
            with self.subTest(level=level):
                line = self.render(self.payload(effort={"level": level}), raw=True)
                self.assertIn(colored, line)

    def test_omits_effort_when_the_model_reports_none(self):
        line = self.render(self.payload(), settings_effort="high")
        self.assertEqual(line, "Sonnet 5")


if __name__ == "__main__":
    unittest.main()
