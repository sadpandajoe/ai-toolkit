from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import warnings

from aitk import cost
from aitk.pricing import PRICING, PROMOTIONS, get_pricing


ROOT = Path(__file__).resolve().parents[1]


class CostTests(unittest.TestCase):
    def test_unknown_models_are_never_mispriced(self) -> None:
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        self.assertIsNone(cost.get_pricing("unknown-provider-model"))
        self.assertEqual(0.0, cost.compute_cost(usage, "unknown-provider-model"))

    def test_a_routed_selector_without_an_exact_price_is_a_warning(self) -> None:
        """Prefix fallback would price a promoted model at its predecessor's rate.

        A missing price skews cost reports only, so it warns rather than fails.
        """
        catalog = json.loads((ROOT / "interfaces" / "model-routing.json").read_text())
        missing = sorted(
            model["selector"]
            for provider in catalog["providers"].values()
            for model in provider["models"].values()
            if model["selector"] not in PRICING
        )
        if missing:
            warnings.warn(
                "routed selectors without an exact price in aitk/pricing.py: "
                + ", ".join(missing)
            )

    def test_promotional_pricing_uses_each_records_absolute_timestamp(self) -> None:
        # Anthropic kept Sonnet 5 at $2/$10 after 2026-09-01 instead of the
        # announced $3/$15, so both sides of its boundary bill the same.
        sonnet_boundaries = {
            "2026-08-31T23:59:59.999999Z": 2.0,
            "2026-09-01T00:00:00Z": 2.0,
            "2026-09-01T01:00:00+01:00": 2.0,
            "2026-09-01T01:00:00+01:01": 2.0,
            "2026-08-31T20:00:00-04:00": 2.0,
        }
        # The Sol promotion still ends, so the same timezone spellings must
        # land on the right side of its boundary.
        sol_boundaries = {
            "2026-11-21T23:59:59.999999Z": 4.0,
            "2026-11-22T00:00:00Z": 5.0,
            "2026-11-22T01:00:00+01:00": 5.0,
            "2026-11-22T01:00:00+01:01": 4.0,
            "2026-11-21T20:00:00-04:00": 5.0,
        }
        usage = {"input_tokens": 1_000_000}
        for model, boundaries in (
            ("claude-sonnet-5", sonnet_boundaries),
            ("gpt-5.6-sol", sol_boundaries),
        ):
            for timestamp, expected in boundaries.items():
                with self.subTest(model=model, timestamp=timestamp):
                    self.assertEqual(expected, cost.get_pricing(model, timestamp)["input"])
                    self.assertEqual(expected, cost.compute_cost(usage, model, timestamp))

    def test_newer_selectors_never_inherit_an_older_models_promotion(self) -> None:
        """A promotion matches its selector or dated form only, never a longer name."""
        october = "2026-10-05T12:00:00Z"
        self.assertEqual(
            {"input": 2.0, "output": 10.0, "cache_read": 0.1, "cache_create": 2.5},
            cost.get_pricing("claude-sonnet-5-5", october),
        )
        # Flat-priced, so a record without a timestamp still prices.
        self.assertEqual(
            cost.get_pricing("claude-sonnet-5-5", october),
            cost.get_pricing("claude-sonnet-5-5", None, require_timestamp=True),
        )
        self.assertEqual(
            {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_create": 2.5},
            cost.get_pricing("claude-sonnet-5-20260601", october),
        )
        self.assertIsNone(
            cost.get_pricing("claude-sonnet-5-20260601", None, require_timestamp=True)
        )

    def test_long_prompt_tiers(self) -> None:
        # Haiku 5.5: a prompt over 100K tokens, cache included, bills the higher tier.
        self.assertEqual(
            {"input": 0.1, "output": 0.5, "cache_read": 0.01, "cache_create": 0.125},
            cost.get_pricing("claude-haiku-5-5"),
        )
        short = {"input_tokens": 60_000, "cache_read_input_tokens": 40_000, "output_tokens": 1_000}
        long = {"input_tokens": 60_000, "cache_read_input_tokens": 40_001, "output_tokens": 1_000}
        self.assertAlmostEqual(0.0069, cost.compute_cost(short, "claude-haiku-5-5"))
        self.assertAlmostEqual(0.03450005, cost.compute_cost(long, "claude-haiku-5-5"))
        # GPT-6 family: over 272K input tokens bills 2x input and cache, 1.5x output.
        self.assertEqual(
            {"input": 2.0, "output": 10.0, "cache_read": 0.1, "cache_create": 2.5},
            cost.get_pricing("gpt-6.1-sol"),
        )
        self.assertEqual(
            {"input": 0.1, "output": 0.5, "cache_read": 0.01, "cache_create": 0.125},
            cost.get_pricing("gpt-6-luna"),
        )
        at_limit = {"input_tokens": 272_000, "output_tokens": 1_000_000}
        over = {"input_tokens": 272_001, "output_tokens": 1_000_000}
        self.assertAlmostEqual(10.544, cost.compute_cost(at_limit, "gpt-6.1-sol"))
        self.assertAlmostEqual(16.088004, cost.compute_cost(over, "gpt-6.1-sol"))
        self.assertAlmostEqual(
            2 * 1.0 + 2 * 12.5,
            cost.compute_cost(
                {"input_tokens": 100_000, "cache_read_input_tokens": 1_000_000,
                 "cache_creation_input_tokens": 1_000_000},
                "gpt-6-astra",
            )
            - 100_000 * 20.0 / 1_000_000,
        )

    def test_missing_invalid_or_timezone_free_promotional_timestamps_are_unpriced(
        self,
    ) -> None:
        usage = {"input_tokens": 1_000_000}
        for timestamp in (None, "", "not-a-time", "2026-08-31T23:59:59"):
            with self.subTest(timestamp=timestamp):
                self.assertIsNone(
                    cost.get_pricing("claude-sonnet-5", timestamp, require_timestamp=True)
                )
                self.assertEqual(0.0, cost.compute_cost(usage, "claude-sonnet-5", timestamp))

    def test_session_parser_prices_records_individually_across_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.jsonl"
            records = [
                {
                    "timestamp": "2026-08-31T23:59:59Z",
                    "sessionId": "session",
                    "message": {
                        "model": "claude-sonnet-5",
                        "usage": {"input_tokens": 1_000_000},
                    },
                },
                {
                    "timestamp": "2026-09-01T00:00:00Z",
                    "sessionId": "session",
                    "message": {
                        "model": "claude-sonnet-5",
                        "usage": {"input_tokens": 1_000_000},
                    },
                },
            ]
            path.write_text("".join(json.dumps(item) + "\n" for item in records))
            session = cost.parse_one_session(str(path), "project", None)
            self.assertEqual(4.0, session["total_cost"])
            self.assertEqual(0, session["models"]["claude-sonnet-5"]["unpriced"])

class PricingMechanismTests(unittest.TestCase):
    """One case per lookup mechanism in aitk.pricing, independent of rates."""

    def test_exact_selector_returns_its_own_rates(self) -> None:
        for selector in PRICING:
            if any(selector == promoted for promoted, _, _ in PROMOTIONS):
                continue
            with self.subTest(selector=selector):
                self.assertEqual(PRICING[selector], get_pricing(selector))

    def test_dated_form_prices_as_its_selector(self) -> None:
        self.assertEqual(PRICING["claude-opus-5-5"], get_pricing("claude-opus-5-5-20261001"))
        for selector, standard_from, _ in PROMOTIONS:
            with self.subTest(selector=selector):
                before = (standard_from - timedelta(seconds=1)).isoformat()
                self.assertEqual(
                    get_pricing(selector, before), get_pricing(f"{selector}-20260101", before)
                )

    def test_prefix_fallback_takes_the_longest_known_selector(self) -> None:
        # claude-opus-5-5-preview starts with both claude-opus-5 and
        # claude-opus-5-5; the longer key wins.
        self.assertEqual(PRICING["claude-opus-5-5"], get_pricing("claude-opus-5-5-preview"))
        self.assertIsNone(get_pricing("claude-unknown-family"))

    def test_each_promotion_switches_exactly_at_its_boundary(self) -> None:
        for selector, standard_from, standard in PROMOTIONS:
            with self.subTest(selector=selector):
                before = (standard_from - timedelta(seconds=1)).isoformat()
                self.assertEqual(PRICING[selector], get_pricing(selector, before))
                self.assertEqual(standard, get_pricing(selector, standard_from.isoformat()))


def usage_record(message_id, request_id, usage, session="session-1"):
    return {
        "timestamp": "2026-09-30T12:00:00Z",
        "sessionId": session,
        "requestId": request_id,
        "message": {"id": message_id, "model": "claude-opus-5-5", "usage": usage},
    }


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item) + "\n" for item in records))


def write_sample_projects(home: Path) -> Path:
    """One session with a repeated usage record and one subagent transcript.

    Opus 5.5 bills $4/MTok input and $20/MTok output, so by hand:
    msg-1 $4 (written twice, counted once) + msg-2 $20 + subagent msg-3 $20
    = $44 over 3 messages. Without dedupe it would be $48 over 4; without the
    subagent, $24 over 2.
    """
    project = home / ".claude" / "projects" / "-work-sample"
    million_in = {"input_tokens": 1_000_000}
    write_jsonl(
        project / "session-1.jsonl",
        [
            usage_record("msg-1", "req-1", million_in),
            usage_record("msg-1", "req-1", million_in),
            usage_record("msg-2", "req-2", {"output_tokens": 1_000_000}),
        ],
    )
    write_jsonl(
        project / "session-1" / "subagents" / "agent-1.jsonl",
        [usage_record("msg-3", "req-3", {"output_tokens": 1_000_000})],
    )
    return project.parent


class ShowCostCountingTests(unittest.TestCase):
    def test_repeated_usage_records_are_counted_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.jsonl"
            million_in = {"input_tokens": 1_000_000}
            write_jsonl(
                path,
                [
                    usage_record("msg-1", "req-1", million_in),
                    usage_record("msg-1", "req-1", million_in),
                    usage_record("msg-1", "req-2", million_in),
                ],
            )
            session = cost.parse_one_session(str(path), "project", None)
        # (msg-1, req-1) twice is one response; (msg-1, req-2) is another.
        self.assertEqual(2, session["messages"])
        self.assertEqual(8.0, session["total_cost"])

    def test_subagent_transcripts_count_toward_their_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = write_sample_projects(Path(temporary))
            sessions = cost.parse_sessions(str(base))
        self.assertEqual(1, len(sessions))
        self.assertEqual(3, sessions[0]["messages"])
        self.assertEqual(44.0, sessions[0]["total_cost"])

    def test_documented_invocation_runs_from_root_and_elsewhere(self) -> None:
        """`bin/aitk cost` from the toolkit root and by absolute path from another cwd."""
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            elsewhere = Path(temporary) / "elsewhere"
            elsewhere.mkdir()
            write_sample_projects(home)
            env = {**os.environ, "HOME": str(home)}
            env.pop("PYTHONPATH", None)
            invocations = (
                (ROOT, "bin/aitk"),
                (elsewhere, str(ROOT / "bin" / "aitk")),
            )
            for cwd, command in invocations:
                with self.subTest(cwd=str(cwd)):
                    result = subprocess.run(
                        [command, "cost", "all"],
                        cwd=cwd,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
                    self.assertIn("Cost: $44.00", output)
                    self.assertIn("Messages: 3", output)
                    self.assertIn("1 sessions", output)


if __name__ == "__main__":
    unittest.main()
