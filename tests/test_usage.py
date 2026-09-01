from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from aitk.usage import SessionUsage, UsageReport, collect_usage, premium_selectors

ROOT = Path(__file__).resolve().parents[1]
OPUS_SELECTOR = "claude-opus-4-8"
SOL_SELECTOR = "gpt-5.6-sol"
SELECTORS = (OPUS_SELECTOR, SOL_SELECTOR)


def _line(**fields: object) -> str:
    return json.dumps(fields)


class CollectUsageTests(unittest.TestCase):
    def test_missing_projects_dir_returns_empty_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = collect_usage(Path(temporary) / "does-not-exist", SELECTORS)
        self.assertEqual(
            UsageReport(sessions=(), total_tokens=0, premium_tokens=0, cost=0.0),
            report,
        )

    def test_empty_projects_dir_returns_empty_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = collect_usage(Path(temporary), SELECTORS)
        self.assertEqual((), report.sessions)
        self.assertEqual(0, report.total_tokens)

    def test_mixed_premium_and_non_premium_lines_split_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "-Users-joeli-example"
            project_dir.mkdir()
            session_file = project_dir / "session-1.jsonl"
            lines = [
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:00:00Z",
                    message={
                        "model": "claude-opus-4-8",
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "cache_creation_input_tokens": 10,
                            "cache_read_input_tokens": 5,
                        },
                    },
                ),
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:01:00Z",
                    message={
                        "model": "claude-sonnet-5",
                        "usage": {
                            "input_tokens": 200,
                            "output_tokens": 20,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                        },
                    },
                ),
            ]
            session_file.write_text("\n".join(lines) + "\n")
            report = collect_usage(root, SELECTORS)

        self.assertEqual(1, len(report.sessions))
        session = report.sessions[0]
        self.assertEqual("/Users/joeli/example", session.cwd)
        self.assertEqual("session-1", session.session_id)
        self.assertEqual(165 + 220, session.total_tokens)
        # Only the opus line (165 tokens) is premium.
        self.assertEqual(165, session.premium_tokens)
        self.assertEqual(session.total_tokens, report.total_tokens)
        self.assertEqual(session.premium_tokens, report.premium_tokens)

    def test_malformed_json_line_is_skipped_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "-Users-joeli-example"
            project_dir.mkdir()
            session_file = project_dir / "session-1.jsonl"
            good_line = _line(
                type="assistant",
                cwd="/Users/joeli/example",
                sessionId="session-1",
                timestamp="2026-08-01T00:00:00Z",
                message={
                    "model": "claude-sonnet-5",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )
            session_file.write_text(
                good_line + "\n" + "{not valid json" + "\n" + good_line + "\n"
            )
            report = collect_usage(root, SELECTORS)

        self.assertEqual(1, len(report.sessions))
        self.assertEqual(30, report.sessions[0].total_tokens)

    def test_line_missing_usage_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "-Users-joeli-example"
            project_dir.mkdir()
            session_file = project_dir / "session-1.jsonl"
            lines = [
                _line(
                    type="user",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    message={"role": "user", "content": "hello"},
                ),
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:00:00Z",
                    message={
                        "model": "claude-sonnet-5",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                    },
                ),
            ]
            session_file.write_text("\n".join(lines) + "\n")
            report = collect_usage(root, SELECTORS)

        self.assertEqual(1, len(report.sessions))
        self.assertEqual(15, report.sessions[0].total_tokens)

    def test_premium_classification_covers_opus_and_codex_sol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "-Users-joeli-example"
            project_dir.mkdir()
            session_file = project_dir / "session-1.jsonl"
            lines = [
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:00:00Z",
                    message={
                        "model": "claude-opus-4-8",
                        "usage": {"input_tokens": 100, "output_tokens": 0},
                    },
                ),
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:01:00Z",
                    message={
                        "model": "gpt-5.6-sol",
                        "usage": {"input_tokens": 50, "output_tokens": 0},
                    },
                ),
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:02:00Z",
                    message={
                        "model": "claude-haiku-4-5",
                        "usage": {"input_tokens": 25, "output_tokens": 0},
                    },
                ),
            ]
            session_file.write_text("\n".join(lines) + "\n")
            report = collect_usage(root, SELECTORS)

        session = report.sessions[0]
        self.assertEqual(175, session.total_tokens)
        # opus (100) + sol (50) are premium; haiku (25) is not.
        self.assertEqual(150, session.premium_tokens)

    def test_grouping_is_per_cwd_and_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "-Users-joeli-example"
            project_dir.mkdir()
            session_file = project_dir / "session-1.jsonl"
            lines = [
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-a",
                    timestamp="2026-08-01T00:00:00Z",
                    message={
                        "model": "claude-sonnet-5",
                        "usage": {"input_tokens": 10, "output_tokens": 0},
                    },
                ),
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-b",
                    timestamp="2026-08-01T00:00:00Z",
                    message={
                        "model": "claude-sonnet-5",
                        "usage": {"input_tokens": 20, "output_tokens": 0},
                    },
                ),
            ]
            session_file.write_text("\n".join(lines) + "\n")
            report = collect_usage(root, SELECTORS)

        self.assertEqual(2, len(report.sessions))
        self.assertEqual(30, report.total_tokens)

    def test_cost_is_computed_via_pricing_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "-Users-joeli-example"
            project_dir.mkdir()
            session_file = project_dir / "session-1.jsonl"
            session_file.write_text(
                _line(
                    type="assistant",
                    cwd="/Users/joeli/example",
                    sessionId="session-1",
                    timestamp="2026-08-01T00:00:00Z",
                    message={
                        "model": "claude-opus-4-8",
                        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
                    },
                )
                + "\n"
            )
            report = collect_usage(root, SELECTORS)

        # claude-opus-4-8 input pricing is $5.00 / 1M tokens.
        self.assertAlmostEqual(5.00, report.sessions[0].cost)


class PremiumSelectorsTests(unittest.TestCase):
    def test_resolves_opus_and_sol_selectors_from_the_live_manifest(self) -> None:
        # Pins the manifest-drift guard: if interfaces/model-routing.json's
        # opus/sol selectors change, this test forces a look rather than a
        # silent reclassification of premium spend.
        self.assertEqual(
            (OPUS_SELECTOR, SOL_SELECTOR), premium_selectors(ROOT)
        )


class SessionUsageAsDictTests(unittest.TestCase):
    def test_as_dict_round_trips_fields(self) -> None:
        session = SessionUsage(
            cwd="/tmp/x", session_id="s1", total_tokens=10, premium_tokens=5, cost=1.5
        )
        self.assertEqual(
            {
                "cwd": "/tmp/x",
                "session_id": "s1",
                "total_tokens": 10,
                "premium_tokens": 5,
                "cost": 1.5,
            },
            session.as_dict(),
        )


if __name__ == "__main__":
    unittest.main()
