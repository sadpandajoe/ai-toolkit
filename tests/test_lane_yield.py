"""`aitk lane-yield` applies the yield table in rules/code-review.md to metrics."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from aitk.lane_yield import DEEP_LENSES, LANE_WINDOW, LENS_WINDOW, evaluate, load_events


ROOT = Path(__file__).resolve().parents[1]


def event(**lanes: dict[str, int]) -> dict[str, object]:
    return {"command": "review-code", "review": {"lanes": lanes}}


class LaneYieldTests(unittest.TestCase):
    def test_lanes_below_their_window_are_not_judged(self) -> None:
        events = [event(adversarial={"raised": 3, "accepted": 0})] * (LENS_WINDOW - 1)
        events += [event(**{"second-family": {"raised": 2, "accepted": 0}})] * (LANE_WINDOW - 1)
        self.assertEqual([], evaluate(events))

    def test_deep_lens_is_demoted_on_low_yield_and_independent_never_is(self) -> None:
        low = [event(adversarial={"raised": 4, "accepted": 0}, independent={"raised": 1, "accepted": 0})]
        demotions = evaluate(low * LENS_WINDOW + [event(independent={"raised": 0, "accepted": 0})] * LANE_WINDOW)
        self.assertEqual(["adversarial"], [item.lane for item in demotions])
        self.assertEqual({"raised": 20, "accepted": 0}, demotions[0].observed)
        # One accepted in four raised keeps the lens: the threshold is "fewer than".
        healthy = [event(**{"lenses/deep-quality.md": {"raised": 4, "accepted": 1}})] * LENS_WINDOW
        self.assertEqual([], evaluate(healthy))
        for lens in DEEP_LENSES:
            self.assertIn(lens, ("adversarial", "deep-quality", "architecture"))

    def test_second_family_verifier_and_delta_apply_their_own_thresholds(self) -> None:
        idle = event(
            **{
                "second-family": {"raised": 3, "accepted": 3, "converged": 3, "refuted": 0},
                "verify-major": {"confirmed": 0, "refuted": 1},
                "delta": {"not_fixed": 0, "introduced": 0},
            }
        )
        demoted = {item.lane: item for item in evaluate([idle] * LANE_WINDOW)}
        self.assertEqual({"second-family", "verify-major", "delta"}, set(demoted))
        self.assertIn("COMPLEX only", demoted["second-family"].consequence)
        self.assertIn("[minor]", demoted["verify-major"].consequence)
        self.assertIn("[major] fix", demoted["delta"].consequence)
        earning = event(
            **{
                "second-family": {"raised": 2, "accepted": 1, "converged": 0},
                "verify-major": {"confirmed": 1},
                "delta": {"not_fixed": 1},
            }
        )
        # Only the most recent window counts, so one good run inside it is enough
        # for the verifier at three confirmed and clears the other two lanes.
        self.assertEqual(
            ["verify-major"],
            [item.lane for item in evaluate([idle] * (LANE_WINDOW - 1) + [earning])],
        )
        self.assertEqual([], evaluate([idle] * (LANE_WINDOW - 3) + [earning] * 3))

    def test_malformed_lines_and_missing_file_read_as_no_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metrics.jsonl"
            self.assertEqual([], load_events(path))
            path.write_text('not json\n[1,2]\n{"review": {"lanes": "bad"}}\n' + json.dumps(event(delta={"not_fixed": "x"})) + "\n")
            events = load_events(path)
            self.assertEqual(2, len(events))
            self.assertEqual([], evaluate(events))

    def test_cli_reports_demotions_as_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary).resolve()
            metrics = cwd / ".ai-toolkit" / "metrics.jsonl"
            metrics.parent.mkdir()
            metrics.write_text("".join(json.dumps(event(architecture={"raised": 2, "accepted": 0})) + "\n" for _ in range(LENS_WINDOW)))
            base = [str(ROOT / "bin/aitk"), "lane-yield"]
            env = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}
            as_json = subprocess.run(base + ["--json"], cwd=cwd, text=True, capture_output=True, check=False, env=env)
            self.assertEqual(0, as_json.returncode, as_json.stderr)
            payload = json.loads(as_json.stdout)
            self.assertEqual(str(metrics), payload["metrics"])
            self.assertEqual(["architecture"], [item["lane"] for item in payload["demotions"]])
            as_text = subprocess.run(base, cwd=cwd, text=True, capture_output=True, check=False, env=env)
            self.assertEqual(0, as_text.returncode, as_text.stderr)
            self.assertIn("architecture: demoted over last 5 runs (raised=10, accepted=0)", as_text.stdout)
            empty = subprocess.run(base + ["--metrics", str(cwd / "missing.jsonl")], cwd=cwd, text=True, capture_output=True, check=False, env=env)
            self.assertEqual(0, empty.returncode, empty.stderr)
            self.assertIn("no lane below its yield threshold", empty.stdout)


if __name__ == "__main__":
    unittest.main()
