"""`bin/aitk metrics emit` fills events from the snapshot; `bin/aitk metrics` sums them."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from aitk.metrics import (
    MetricsError,
    aggregate,
    build_event,
    emit,
    normalise,
    read_events,
    render_project,
    render_summary,
    select,
)
from aitk.project_state import initialize, record_gate, set_phases


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def event(command: str, status: str, **fields: object) -> dict[str, object]:
    return {"timestamp": "2026-10-01T12:00:00Z", "command": command, "status": status, **fields}


class EmitTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.work)], check=True, env=ENVIRONMENT)
        self.project = self.work / "PROJECT.md"

    def test_emit_fills_the_snapshot_fields_and_excludes_the_data_directory(self) -> None:
        initialize(self.project, "create-feature", "COMPLEX", "L", phaseability="phased", phaseability_reason="two layers")
        set_phases(
            self.project,
            [
                {"name": "one", "complexity": "STANDARD", "size": "M", "status": "active"},
                {"name": "two", "complexity": "STANDARD", "size": "S", "status": "pending"},
            ],
        )
        record_gate(self.project, "plan", "PASS")
        record_gate(self.project, "verification", "RETRY")
        subdirectory = self.work / "sub"
        subdirectory.mkdir()
        path, written = emit(
            subdirectory,
            "create-feature",
            "PASS",
            project_file=self.project,
            workers=["review=2", "deep-review=1", "implementation=3"],
            extra=["worker_usage={\"tester\": 1}", "gate_decisions={\"pr_created\": \"yes\"}", "rounds=2"],
        )
        self.assertEqual(self.work / ".ai-toolkit/metrics.jsonl", path)
        line = json.loads(path.read_text().splitlines()[-1])
        self.assertEqual(written, line)
        self.assertEqual(
            {
                "command": "create-feature",
                "workflow": "create-feature",
                "status": "PASS",
                "complexity": "complex",
                "size": "L",
                "shape": "multi_phase",
                "phases": 2,
                "retries": 1,
                "escalations": 0,
                "workers": {"tester": 1, "review": 2, "deep-review": 1, "implementation": 3},
                "premium_calls": 1,
                "decisions": {"pr_created": "yes"},
                "rounds": 2,
            },
            {key: value for key, value in line.items() if key not in {"timestamp", "gates"}},
        )
        self.assertEqual({"status": "PASS"}, line["gates"]["plan"])
        self.assertEqual("RETRY", line["gates"]["verification"]["status"])
        self.assertIn(".ai-toolkit/", (self.work / ".git/info/exclude").read_text())

    def test_emit_without_a_snapshot_and_with_a_review_merge_file(self) -> None:
        review = self.work / "merge.json"
        review.write_text(json.dumps({"command": "review merge", "lanes": {"independent": {"raised": 2, "converged": 0}}}))
        _, written = emit(self.work, "review-code", "PASS", project_file=self.project, review_file=review)
        self.assertEqual({"lanes": {"independent": {"raised": 2, "converged": 0}}}, written["review"])
        self.assertNotIn("complexity", written)

    def test_bad_arguments_are_refused(self) -> None:
        for kwargs in ({"workers": ["review"]}, {"workers": ["review=-1"]}, {"workers": ["review=two"]}, {"extra": ["=1"]}):
            with self.subTest(**kwargs):
                with self.assertRaises(MetricsError):
                    emit(self.work, "fix-bug", "PASS", **kwargs)  # type: ignore[arg-type]
        with self.assertRaises(MetricsError):
            build_event("", "PASS")
        self.assertFalse((self.work / ".ai-toolkit/metrics.jsonl").exists())

    def test_normalises_the_names_workflows_hand_wrote(self) -> None:
        self.assertEqual(
            {"workers": {"a": 1}, "decisions": {}, "retries": 2, "status": "clean", "complexity": "standard", "shape": "batched"},
            normalise(
                {
                    "worker_usage": {"a": 1},
                    "gate_decisions": {},
                    "retry_count": 2,
                    "outcome": "clean",
                    "complexity": "non-trivial",
                    "execution_shape": "BATCHED",
                }
            ),
        )
        # The caller's identity fields never overwrite the event's own.
        built = build_event("fix-ci", "PASS", extra={"command": "other", "outcome": "BLOCKED"})
        self.assertEqual(("fix-ci", "BLOCKED"), (built["command"], built["status"]))


class SummaryTests(unittest.TestCase):
    EVENTS = [
        event("fix-bug", "PASS", complexity="trivial", retries=0, workers={"review": 1}),
        event("fix-bug", "ESCALATE", complexity="standard", retries=2, escalations=1),
        event("create-pr", "clean", complexity="standard", workers={"review": 1, "planning": 2}),
        event("fix-ci", "BLOCKED", complexity="trivial", reclassifications=1),
        event(
            "review-code",
            "PASS",
            complexity="complex",
            review={"lanes": {"independent": {"raised": 4, "accepted": 3}, "adversarial": {"raised": 2, "accepted": 0}}},
        ),
    ]

    def test_aggregates_status_retries_workers_complexity_and_yield(self) -> None:
        summary = aggregate(self.EVENTS)
        self.assertEqual(5, summary["events"])
        self.assertEqual({"PASS": 3, "ESCALATE": 1, "USER_DECISION": 0, "BLOCKED": 1, "OTHER": 0}, summary["statuses"])
        fix_bug = summary["workflows"]["fix-bug"]
        self.assertEqual((2, 1.0, 2, 1), (fix_bug["runs"], fix_bug["avg_retries"], fix_bug["max_retries"], fix_bug["escalations"]))
        self.assertEqual({"review": {"invocations": 2, "share": 50}, "planning": {"invocations": 2, "share": 50}}, summary["workers"])
        self.assertEqual({"trivial": 2, "standard": 2, "complex": 1}, summary["complexity"])
        self.assertEqual(1, summary["trivial_pass_without_reclassification"])
        self.assertEqual({"adversarial": {"raised": 2, "accepted": 0}, "independent": {"raised": 4, "accepted": 3}}, summary["lanes"])

    def test_filters_by_period_command_and_since(self) -> None:
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        events = [event("a", "PASS", timestamp="2026-10-09T00:00:00Z"), event("b", "PASS", timestamp="2026-09-01T00:00:00+00:00")]
        self.assertEqual(["a"], [item["command"] for item in select(events, period="7d", now=now)])
        self.assertEqual(["a", "b"], [item["command"] for item in select(events, period="all", now=now)])
        self.assertEqual(["b"], [item["command"] for item in select(events, command="b")])
        self.assertEqual(["a"], [item["command"] for item in select(events, since="2026-10-01")])
        for bad in ({"period": "week"}, {"since": "yesterday"}):
            with self.subTest(**bad):
                with self.assertRaises(MetricsError):
                    select(events, **bad)  # type: ignore[arg-type]

    def test_project_format_and_the_empty_summaries(self) -> None:
        text = render_project(aggregate(self.EVENTS))
        self.assertTrue(text.startswith("## Project Metrics Summary"))
        self.assertIn("| Total commands run | 5 |", text)
        self.assertIn("| Pass rate (`PASS`) | 60% |", text)
        self.assertIn("| Gate retries / escalations | 2 / 1 |", text)
        self.assertIn("adversarial 0/2, independent 3/4", text)
        self.assertIn("| fix-bug | 2 | 1 | 1 | 0 |", text)
        self.assertEqual("No metrics recorded for this project", render_project(aggregate([])))
        self.assertTrue(render_summary(aggregate([]), "all").startswith("No metrics recorded yet."))
        summary = render_summary(aggregate(self.EVENTS), "30d")
        self.assertIn("| fix-bug | 2 | 1 | 1 | 0 | 0 |", summary)
        self.assertIn("Not enough data for trend analysis", summary)

    def test_reads_the_legacy_file_only_when_the_canonical_one_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            legacy = work / ".claude/metrics.jsonl"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps(event("old", "PASS")) + "\nnot json\n")
            path, events = read_events(work)
            self.assertEqual((legacy, ["old"]), (path, [item["command"] for item in events]))
            canonical = work / ".ai-toolkit/metrics.jsonl"
            canonical.parent.mkdir()
            canonical.write_text(json.dumps(event("new", "PASS")) + "\n")
            path, events = read_events(work)
            self.assertEqual((canonical, ["new"]), (path, [item["command"] for item in events]))


class MetricsCliTests(unittest.TestCase):
    def test_emit_then_summarize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            run = lambda *args: subprocess.run(  # noqa: E731
                [str(ROOT / "bin/aitk"), "metrics", *args], cwd=work, text=True, capture_output=True, check=False
            )
            emitted = run("emit", "--workflow", "fix-bug", "--status", "PASS", "--workers", "review=1", "--json")
            self.assertEqual(0, emitted.returncode, emitted.stderr)
            self.assertEqual({"command", "file", "event"}, set(json.loads(emitted.stdout)))
            text = run("emit", "--workflow", "fix-ci", "--status", "BLOCKED")
            self.assertTrue(text.stdout.startswith("## Metrics Recorded\nEvent: fix-ci | Status: BLOCKED"))
            summary = run("--json")
            self.assertEqual(0, summary.returncode, summary.stderr)
            payload = json.loads(summary.stdout)
            self.assertEqual(2, payload["events"])
            self.assertTrue({"command", "file", "period", "workflows", "statuses", "workers", "lanes"} <= set(payload))
            project = run("--since", "2000-01-01", "--format", "project")
            self.assertIn("| Total commands run | 2 |", project.stdout)
            bad = run("emit", "--workflow", "fix-bug", "--status", "PASS", "--workers", "review")
            self.assertEqual(1, bad.returncode)
            self.assertIn("metrics never gate progress", bad.stderr)
            self.assertIn("Metrics never gate", " ".join(run("--help").stdout.split()))


if __name__ == "__main__":
    unittest.main()
