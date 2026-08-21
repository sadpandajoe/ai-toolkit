from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

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

    def test_current_model_families_have_explicit_pricing(self) -> None:
        module = load_script("show-cost.py")
        self.assertEqual(5.0, module.get_pricing("claude-opus-5")["input"])
        self.assertEqual(10.0, module.get_pricing("claude-fable-5")["input"])
        self.assertEqual(5.0, module.get_pricing("claude-opus-4-8")["input"])
        self.assertEqual(1.0, module.get_pricing("claude-haiku-4-5")["input"])
        self.assertIsNotNone(module.get_pricing("claude-sonnet-5"))
        self.assertEqual(
            {
                "input": 10.0,
                "output": 50.0,
                "cache_read": 1.0,
                "cache_create": 12.5,
            },
            module.get_pricing("claude-fable-5"),
        )
        self.assertEqual(
            {
                "input": 5.0,
                "output": 25.0,
                "cache_read": 0.5,
                "cache_create": 6.25,
            },
            module.get_pricing("claude-opus-4-6"),
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
            ),
        )
        self.assertEqual(
            {
                "input": 3.0,
                "output": 15.0,
                "cache_read": 0.3,
                "cache_create": 3.75,
            },
            module.get_pricing("claude-sonnet-4-6"),
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
            ),
        )

    def test_sonnet_5_pricing_is_flat_across_the_former_cutover(self) -> None:
        usage = {"input_tokens": 1_000_000}
        for script in ("show-cost.py", "optimize-cost.py"):
            with self.subTest(script=script):
                module = load_script(script)
                pricing = module.get_pricing("claude-sonnet-5")
                self.assertEqual(2.0, pricing["input"])
                self.assertEqual(10.0, pricing["output"])
                self.assertEqual(2.0, module.compute_cost(usage, "claude-sonnet-5"))

    def test_session_parser_prices_sonnet_5_records_flat_across_the_former_boundary(
        self,
    ) -> None:
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
            self.assertEqual(4.0, session["total_cost"])
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


if __name__ == "__main__":
    unittest.main()
