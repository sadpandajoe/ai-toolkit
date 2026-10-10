from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from aitk.pricing import PRICING
from aitk.workflows import load_workflows


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CostScriptTests(unittest.TestCase):
    def test_unknown_models_are_never_mispriced(self) -> None:
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        for script in ("show-cost.py", "optimize-cost.py"):
            module = load_script(script)
            self.assertIsNone(module.get_pricing("unknown-provider-model"), script)
            self.assertEqual(
                0.0, module.compute_cost(usage, "unknown-provider-model"), script
            )

    def test_every_routed_selector_has_an_exact_pricing_key(self) -> None:
        """Prefix fallback would price a promoted model at its predecessor's rate."""
        catalog = json.loads(
            (Path(__file__).resolve().parents[1] / "interfaces" / "model-routing.json").read_text()
        )
        for provider in catalog["providers"].values():
            for model in provider["models"].values():
                with self.subTest(selector=model["selector"]):
                    self.assertIn(model["selector"], PRICING)

    def test_current_model_families_have_explicit_pricing(self) -> None:
        module = load_script("show-cost.py")
        timestamp = "2026-07-16T12:00:00Z"
        self.assertEqual(5.0, module.get_pricing("claude-opus-4-8", timestamp)["input"])
        self.assertEqual(
            1.0, module.get_pricing("claude-haiku-4-5", timestamp)["input"]
        )
        self.assertIsNotNone(module.get_pricing("claude-sonnet-5", timestamp))
        # Opus 5.5 is cheaper than Opus 5 and its cache reads bill at 0.05x input.
        self.assertEqual(
            {"input": 4.0, "output": 20.0, "cache_read": 0.2, "cache_create": 5.0},
            module.get_pricing("claude-opus-5-5", timestamp),
        )
        self.assertEqual(5.0, module.get_pricing("claude-opus-5", timestamp)["input"])
        self.assertEqual(
            {
                "input": 5.0,
                "output": 25.0,
                "cache_read": 0.5,
                "cache_create": 6.25,
            },
            module.get_pricing("claude-opus-4-6", timestamp),
        )
        self.assertEqual(
            36.75,
            module.compute_cost(
                {
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "cache_read_input_tokens": 1_000_000,
                    "cache_creation_input_tokens": 1_000_000,
                },
                "claude-opus-4-6",
                timestamp,
            ),
        )
        self.assertEqual(
            {
                "input": 3.0,
                "output": 15.0,
                "cache_read": 0.3,
                "cache_create": 3.75,
            },
            module.get_pricing("claude-sonnet-4-6", timestamp),
        )
        self.assertAlmostEqual(
            22.05,
            module.compute_cost(
                {
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "cache_read_input_tokens": 1_000_000,
                    "cache_creation_input_tokens": 1_000_000,
                },
                "claude-sonnet-4-6",
                timestamp,
            ),
        )

    def test_codex_families_are_priced_and_the_sol_promotion_ends_on_time(self) -> None:
        """Astra and Sol are priced by selector; Sol's promotion is timestamp-aware."""
        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
        }
        for script in ("show-cost.py", "optimize-cost.py"):
            module = load_script(script)
            with self.subTest(script=script):
                self.assertEqual(
                    {"input": 10.0, "output": 50.0, "cache_read": 1.0, "cache_create": 12.5},
                    module.get_pricing("gpt-6-astra", "2026-09-05T00:00:00Z"),
                )
                self.assertEqual(73.5, module.compute_cost(usage, "gpt-6-astra", "2026-09-05T00:00:00Z"))
                # Promotional Sol until the announced end date, standard after it.
                self.assertEqual(4.0, module.get_pricing("gpt-5.6-sol", "2026-11-21T23:59:59Z")["input"])
                self.assertEqual(5.0, module.get_pricing("gpt-5.6-sol", "2026-11-22T00:00:00Z")["input"])
                self.assertEqual(20.0, module.get_pricing("gpt-5.6-sol", "2026-09-05T00:00:00Z")["output"])
                self.assertEqual(30.0, module.get_pricing("gpt-5.6-sol", "2026-12-01T00:00:00Z")["output"])
                # A promotional model without a timestamp stays unpriced, as for Sonnet.
                self.assertEqual(0.0, module.compute_cost(usage, "gpt-5.6-sol"))
                # GPT-6 Sol is flat-priced, so it needs no timestamp.
                self.assertEqual(
                    {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_create": 2.5},
                    module.get_pricing("gpt-6-sol", "2026-12-01T00:00:00Z"),
                )
                self.assertEqual(14.7, round(module.compute_cost(usage, "gpt-6-sol", "2026-09-25T00:00:00Z"), 6))
                self.assertEqual(14.7, round(module.compute_cost(usage, "gpt-6-sol"), 6))

    def test_promotional_pricing_uses_each_records_absolute_timestamp(self) -> None:
        boundaries = {
            "2026-08-31T23:59:59.999999Z": 2.0,
            "2026-09-01T00:00:00Z": 3.0,
            "2026-09-01T01:00:00+01:00": 3.0,
            "2026-09-01T01:00:00+01:01": 2.0,
            "2026-08-31T20:00:00-04:00": 3.0,
        }
        usage = {"input_tokens": 1_000_000}
        for script in ("show-cost.py", "optimize-cost.py"):
            module = load_script(script)
            for timestamp, expected in boundaries.items():
                with self.subTest(script=script, timestamp=timestamp):
                    self.assertEqual(
                        expected,
                        module.get_pricing("claude-sonnet-5", timestamp)["input"],
                    )
                    self.assertEqual(
                        expected,
                        module.compute_cost(usage, "claude-sonnet-5", timestamp),
                    )

    def test_missing_invalid_or_timezone_free_promotional_timestamps_are_unpriced(
        self,
    ) -> None:
        usage = {"input_tokens": 1_000_000}
        for script in ("show-cost.py", "optimize-cost.py"):
            module = load_script(script)
            for timestamp in (None, "", "not-a-time", "2026-08-31T23:59:59"):
                with self.subTest(script=script, timestamp=timestamp):
                    self.assertIsNone(
                        module.get_pricing(
                            "claude-sonnet-5",
                            timestamp,
                            require_timestamp=True,
                        )
                    )
                    self.assertEqual(
                        0.0,
                        module.compute_cost(usage, "claude-sonnet-5", timestamp),
                    )

    def test_session_parser_prices_records_individually_across_boundary(self) -> None:
        module = load_script("show-cost.py")
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
            session = module.parse_one_session(str(path), "project", None)
            self.assertEqual(5.0, session["total_cost"])
            self.assertEqual(0, session["models"]["claude-sonnet-5"]["unpriced"])

    def test_project_shortening_has_no_personal_username_constant(self) -> None:
        for script in ("show-cost.py", "optimize-cost.py"):
            text = (ROOT / "scripts" / script).read_text()
            self.assertNotIn("joeli", text.lower())

    def test_cost_attribution_recognizes_canonical_and_legacy_invocations(self) -> None:
        module = load_script("optimize-cost.py")
        self.assertEqual(
            ["create-feature", "fix-bug", "create-status-report"],
            module.extract_commands(
                "$workflows create-feature then /fix-bug and $pgm create-status-report"
            ),
        )
        for workflow in load_workflows(ROOT, include_pgm=True):
            owner = "$pgm" if workflow.owner_skill == "pgm" else "$workflows"
            with self.subTest(workflow=workflow.name):
                self.assertEqual(
                    [workflow.name],
                    module.extract_commands(f"{owner} {workflow.name}"),
                )
                self.assertEqual(
                    [workflow.name], module.extract_commands(f"/{workflow.name}")
                )
        self.assertEqual(
            ["review-code-adversarial"],
            module.extract_commands("$workflows review-code-adversarial"),
        )


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
        module = load_script("show-cost.py")
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
            session = module.parse_one_session(str(path), "project", None)
        # (msg-1, req-1) twice is one response; (msg-1, req-2) is another.
        self.assertEqual(2, session["messages"])
        self.assertEqual(8.0, session["total_cost"])

    def test_subagent_transcripts_count_toward_their_session(self) -> None:
        module = load_script("show-cost.py")
        with tempfile.TemporaryDirectory() as temporary:
            base = write_sample_projects(Path(temporary))
            sessions = module.parse_sessions(str(base))
        self.assertEqual(1, len(sessions))
        self.assertEqual(3, sessions[0]["messages"])
        self.assertEqual(44.0, sessions[0]["total_cost"])

    def test_documented_invocation_runs_from_root_and_elsewhere(self) -> None:
        """`python3 scripts/show-cost.py` and an absolute path from another cwd."""
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            elsewhere = Path(temporary) / "elsewhere"
            elsewhere.mkdir()
            write_sample_projects(home)
            env = {**os.environ, "HOME": str(home)}
            env.pop("PYTHONPATH", None)
            invocations = (
                (ROOT, "scripts/show-cost.py"),
                (elsewhere, str(ROOT / "scripts" / "show-cost.py")),
            )
            for cwd, script in invocations:
                with self.subTest(cwd=str(cwd)):
                    result = subprocess.run(
                        [sys.executable, script, "all"],
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
