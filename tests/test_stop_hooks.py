"""The Stop hooks return their nudge where the runtime will show it.

Stderr from a hook that exits 0 goes only to the debug log, so a reminder
written there is never seen. The hooks return JSON with a ``systemMessage``
on stdout instead, and stay silent below their thresholds.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_hook(name: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / "hooks" / name)],
        input=json.dumps({"cwd": str(cwd), "hook_event_name": "Stop"}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def system_message(result: subprocess.CompletedProcess[str]) -> str | None:
    if not result.stdout.strip():
        return None
    payload = json.loads(result.stdout)
    return payload["systemMessage"]


class StopHookTests(unittest.TestCase):
    def test_observation_reminder_surfaces_at_the_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            queue = cwd / ".ai-toolkit" / "observations.jsonl"
            queue.parent.mkdir()
            queue.write_text("".join(f'{{"n": {i}}}\n' for i in range(9)))
            quiet = run_hook("observation-reminder.sh", cwd)
            self.assertEqual(0, quiet.returncode)
            self.assertIsNone(system_message(quiet))

            queue.write_text("".join(f'{{"n": {i}}}\n' for i in range(10)))
            loud = run_hook("observation-reminder.sh", cwd)
            self.assertEqual(0, loud.returncode)
            message = system_message(loud)
            self.assertIsNotNone(message)
            self.assertIn("10 unreviewed observations", message)
            self.assertIn("reflect observations", message)

    def test_plan_drift_surfaces_only_when_plan_outpaces_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            plan, project = cwd / "PLAN.md", cwd / "PROJECT.md"
            plan.write_text("plan\n")
            project.write_text("state\n")
            now = time.time()
            os.utime(project, (now, now))
            os.utime(plan, (now + 600, now + 600))
            fresh = run_hook("check-plan-drift.sh", cwd)
            self.assertEqual(0, fresh.returncode)
            self.assertIsNone(system_message(fresh))

            os.utime(plan, (now + 3600, now + 3600))
            stale = run_hook("check-plan-drift.sh", cwd)
            self.assertEqual(0, stale.returncode)
            message = system_message(stale)
            self.assertIsNotNone(message)
            self.assertIn("[plan-drift]", message)
            self.assertIn("60 minutes newer", message)

    def test_hooks_fail_open_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for name in ("observation-reminder.sh", "check-plan-drift.sh"):
                with self.subTest(hook=name):
                    result = run_hook(name, Path(temporary))
                    self.assertEqual(0, result.returncode)
                    self.assertEqual("", result.stdout)


if __name__ == "__main__":
    unittest.main()
