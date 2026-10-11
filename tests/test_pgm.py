from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from aitk.pgm import PGMPreflightError, preflight, run_after_preflight, thresholds


ROOT = Path(__file__).resolve().parents[1]


def valid_config(velocity: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "teams": [{"name": "Team", "id": "team-id"}],
        "members": [
            {
                "name": "Person",
                "github": "person",
                "shortcut_id": "member-id",
                "team_id": "team-id",
            }
        ],
        "bots": ["automation-bot"],
        "repos": [
            {
                "name": "repo",
                "path": str(ROOT),
                "team_id": "team-id",
                "strategy": "all_prs",
            }
        ],
    }
    if velocity:
        payload.update(
            {
                "month": "2026-07",
                "date_range": {"start": "2026-07-01", "end": "2026-07-31"},
            }
        )
    return payload


class PGMPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.pgm_dir = Path(self.temporary.name) / "pgm"
        self.pgm_dir.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def options(self) -> dict[str, object]:
        return {
            "environment": {},
            "shortcut_connector": True,
            "github_connector": True,
            "github_cli_available": False,
        }

    def test_missing_and_malformed_configuration_stop_before_effects(self) -> None:
        calls: list[dict[str, object]] = []
        result = preflight("create-status-report", self.pgm_dir, **self.options())
        self.assertEqual("blocked", result.status)
        self.assertTrue(
            any("config.json is missing" in item for item in result.findings)
        )
        with self.assertRaises(PGMPreflightError):
            run_after_preflight(
                "create-status-report",
                self.pgm_dir,
                calls.append,
                **self.options(),
            )
        self.assertEqual([], calls)

        (self.pgm_dir / "config.json").write_text("not json\n")
        result = preflight("create-status-report", self.pgm_dir, **self.options())
        self.assertEqual("blocked", result.status)
        self.assertTrue(
            any("not valid readable JSON" in item for item in result.findings)
        )
        self.assertNotIn("not json", " ".join(result.findings))

    def test_incomplete_config_and_missing_authorization_are_actionable(self) -> None:
        (self.pgm_dir / "config.json").write_text(json.dumps({"teams": []}))
        result = preflight(
            "create-status-report",
            self.pgm_dir,
            environment={},
            github_cli_available=False,
        )
        self.assertEqual("blocked", result.status)
        text = " ".join(result.findings)
        for expected in ("members", "repos", "bots", "Shortcut", "GitHub"):
            self.assertIn(expected, text)

    def test_empty_entry_objects_and_unauthenticated_cli_are_refused(self) -> None:
        (self.pgm_dir / "config.json").write_text(
            json.dumps({"teams": [{}], "members": [{}], "repos": [{}], "bots": []})
        )
        result = preflight(
            "create-status-report",
            self.pgm_dir,
            environment={"SHORTCUT_API_TOKEN": "present"},
            github_cli_available=True,
            github_cli_authenticated=False,
        )
        self.assertEqual("blocked", result.status)
        text = " ".join(result.findings)
        for expected in ("teams entry", "members entry", "repos entry", "GitHub"):
            self.assertIn(expected, text)

    def test_names_only_topology_and_missing_repo_are_not_ready(self) -> None:
        incomplete = {
            "teams": [{"name": "Team"}],
            "members": [{"name": "Person"}],
            "repos": [
                {
                    "name": "repo",
                    "path": str(self.pgm_dir / "missing"),
                    "strategy": "all_prs",
                }
            ],
            "bots": [],
        }
        (self.pgm_dir / "config.json").write_text(json.dumps(incomplete))

        result = preflight("create-status-report", self.pgm_dir, **self.options())

        self.assertEqual("blocked", result.status)
        text = " ".join(result.findings)
        for expected in (
            "id or uuid",
            "GitHub handle",
            "Shortcut ID",
            "team assignment",
            "existing directory",
            "team relationship",
        ):
            self.assertIn(expected, text)

    def test_valid_status_configuration_allows_exactly_one_guarded_effect(self) -> None:
        config = valid_config()
        (self.pgm_dir / "config.json").write_text(json.dumps(config))
        calls: list[dict[str, object]] = []
        returned = run_after_preflight(
            "create-status-report",
            self.pgm_dir,
            lambda payload: calls.append(payload) or "collected",
            **self.options(),
        )
        self.assertEqual("collected", returned)
        self.assertEqual([config], calls)
        self.assertEqual(
            "ready",
            preflight("create-status-report", self.pgm_dir, **self.options()).status,
        )

    def test_guard_rechecks_prerequisites_at_the_effect_boundary(self) -> None:
        config = self.pgm_dir / "config.json"
        config.write_text(json.dumps(valid_config()))
        calls: list[dict[str, object]] = []
        original = preflight
        checks = 0

        def changing_preflight(*args: object, **kwargs: object):
            nonlocal checks
            result = original(*args, **kwargs)
            checks += 1
            if checks == 1:
                config.unlink()
            return result

        with mock.patch("aitk.pgm.preflight", side_effect=changing_preflight):
            with self.assertRaisesRegex(PGMPreflightError, "config.json is missing"):
                run_after_preflight(
                    "create-status-report",
                    self.pgm_dir,
                    calls.append,
                    **self.options(),
                )

        self.assertEqual([], calls)

    def test_velocity_requires_dates_and_complete_safe_pipeline(self) -> None:
        (self.pgm_dir / "config.json").write_text(json.dumps(valid_config()))
        result = preflight("create-velocity-report", self.pgm_dir, **self.options())
        self.assertEqual("blocked", result.status)
        self.assertTrue(any("month" in item for item in result.findings))
        self.assertTrue(any("date_range" in item for item in result.findings))
        self.assertTrue(any("pipeline file" in item for item in result.findings))

        (self.pgm_dir / "config.json").write_text(json.dumps(valid_config(True)))
        for name in (
            "run.md",
            "collect_github.py",
            "collect_shortcut.py",
            "analyze.py",
            "report.py",
        ):
            (self.pgm_dir / name).write_text("# fixture\n")
        self.assertEqual(
            "ready",
            preflight("create-velocity-report", self.pgm_dir, **self.options()).status,
        )

    def test_thresholds_default_when_absent_and_read_when_set(self) -> None:
        config = valid_config()
        (self.pgm_dir / "config.json").write_text(json.dumps(config))
        self.assertEqual(
            "ready",
            preflight("create-status-report", self.pgm_dir, **self.options()).status,
        )
        self.assertEqual(
            {
                "stalled_days": 5,
                "pr_review_hours": 48,
                "team_wip_multiplier": 2,
                "member_wip_max": 3,
            },
            thresholds(config),
        )
        config["thresholds"] = {"stalled_days": 7, "pr_review_hours": 24.5}
        (self.pgm_dir / "config.json").write_text(json.dumps(config))
        self.assertEqual(
            "ready",
            preflight("create-status-report", self.pgm_dir, **self.options()).status,
        )
        self.assertEqual(
            {
                "stalled_days": 7,
                "pr_review_hours": 24.5,
                "team_wip_multiplier": 2,
                "member_wip_max": 3,
            },
            thresholds(config),
        )

    def test_non_positive_or_unknown_threshold_fails_the_preflight(self) -> None:
        cases = (
            ({"stalled_days": 0}, "thresholds.stalled_days must be a positive number"),
            ({"member_wip_max": -1}, "thresholds.member_wip_max must be a positive number"),
            ({"pr_review_hours": "48"}, "thresholds.pr_review_hours must be a positive number"),
            ({"team_wip_multiplier": True}, "thresholds.team_wip_multiplier must be a positive number"),
            ({"stale_days": 5}, "thresholds has unknown key stale_days"),
            ([], "thresholds must be an object"),
        )
        for value, expected in cases:
            with self.subTest(thresholds=value):
                config = valid_config()
                config["thresholds"] = value
                (self.pgm_dir / "config.json").write_text(json.dumps(config))
                result = preflight("create-status-report", self.pgm_dir, **self.options())
                self.assertEqual("blocked", result.status)
                self.assertTrue(
                    any(expected in item for item in result.findings), result.findings
                )
                with self.assertRaises(PGMPreflightError):
                    thresholds(config)

    def test_symlinked_config_is_refused_without_following_it(self) -> None:
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_text(json.dumps(valid_config()))
        (self.pgm_dir / "config.json").symlink_to(outside)
        before = outside.read_bytes()
        result = preflight("create-status-report", self.pgm_dir, **self.options())
        self.assertEqual("blocked", result.status)
        self.assertTrue(any("symlink" in item for item in result.findings))
        self.assertEqual(before, outside.read_bytes())

    def test_cli_emits_stable_json_and_exit_codes(self) -> None:
        (self.pgm_dir / "config.json").write_text(json.dumps(valid_config()))
        command = [
            str(ROOT / "bin/aitk"),
            "pgm-preflight",
            "--workflow",
            "create-status-report",
            "--pgm-dir",
            str(self.pgm_dir),
            "--shortcut-connector",
            "--github-connector",
            "--json",
        ]
        ready = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "SHORTCUT_API_TOKEN": ""},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, ready.returncode, ready.stderr)
        payload = json.loads(ready.stdout)
        self.assertEqual({"workflow", "status", "config", "findings"}, set(payload))
        (self.pgm_dir / "config.json").unlink()
        blocked = subprocess.run(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, blocked.returncode)
        self.assertEqual("blocked", json.loads(blocked.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
