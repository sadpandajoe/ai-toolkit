"""`bin/aitk eval`: judgment cases through a stub `model-run`, graded, written up.

No test here reaches a provider. The runner tests inject the dispatch (a stub
`model-run`) or a stub process runner behind the real transport, and the CLI
tests put stub `claude` and `codex` executables first on a PATH that holds no
real one.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from aitk.eval import (
    FAMILY_CONTRACTS,
    GRADER,
    Case,
    EvalError,
    answer_keys,
    answer_prompt,
    eval_route,
    grader_prompt,
    load_cases,
    plan,
    render,
    results_path,
    run_eval,
    settings_for,
    transport_dispatch,
    verdict,
    write_results,
)
from aitk.pricing import compute_cost
from aitk.routing_closure import _contracts
from aitk.routing_manifest import load_model_routing
from aitk.routing_policy import CODEX_INSTRUCTIONS_LIMIT
from aitk.routing_transport import _toml_string, worker_instructions



ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 14, 3, 22, tzinfo=timezone.utc)
COVERED_CASE = {
    "id": "phase-done-without-tree",
    "mode": "judgment",
    "input": "Mark phase 2 done without recording its tree SHA",
    "expected": {"error": "without --sha", "covered_by": "tests/test_project_state.py"},
    "source": "test",
}


def with_covered_case(directory: str) -> Path:
    """A copy of the toolkit whose gates family holds one test-covered case."""
    root = Path(directory) / "repo"
    if not root.exists():
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
        with (root / "evals/gates/cases.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(COVERED_CASE) + "\n")
    return root
PAYLOAD = load_model_routing(ROOT)


def worker(summary: str, findings: list[str] | None = None, status: str = "completed") -> dict[str, object]:
    return {"status": status, "summary": summary, "findings": findings or [], "verification": ["read"]}


def envelope(result: dict[str, object] | None, usage: dict[str, object] | None = None,
             error: dict[str, object] | None = None) -> dict[str, object]:
    """The parts of a `model-run` envelope the runner reads."""
    return {"command": "model-run", "result": result, "usage": usage, "error": error}


class StubModelRun:
    """A stub `model-run`: answers from a table keyed by case id, then grades.

    `answers` maps a case id to the answer summary, or to an envelope to return
    as is; `verdicts` maps a case id to the grader's (verdict, findings).
    """

    def __init__(self, answers: dict[str, object], verdicts: dict[str, tuple[str, list[str]]]) -> None:
        self.answers = answers
        self.verdicts = verdicts
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, route, prompt: str) -> tuple[int, dict[str, object]]:
        if route.boundary == "eval.grade":
            case_id = prompt.split("`", 2)[1]
        else:
            # The answer prompt carries the situation, never the case id.
            (case_id,) = [case.id for case in load_cases(ROOT)[0] if answer_prompt(case) == prompt]
        self.calls.append((route.boundary, route.selector, case_id))
        if route.boundary == "eval.grade":
            decided, findings = self.verdicts[case_id]
            usage = {"input_tokens": 1_000, "output_tokens": 100, "cache_read_input_tokens": 0,
                     "cache_creation_input_tokens": 0, "cost_usd": 0.01}
            return 0, envelope(worker(f"Verdict: {decided}\n", findings), usage)
        answer = self.answers[case_id]
        if isinstance(answer, dict):
            return 3, answer
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                 "cache_creation_input_tokens": 0, "cost_usd": 0.02}
        return 0, envelope(worker(str(answer)), usage)


class CaseSelectionTests(unittest.TestCase):
    def test_only_judgment_cases_run_and_test_covered_ones_are_skipped(self) -> None:
        cases, skipped = load_cases(ROOT)
        self.assertTrue(cases)
        ids = {case.id for case in cases}
        self.assertNotIn("same-failure-once-retries", ids, "deterministic cases run in test_evals")
        self.assertIn("existing-pattern-form-field", ids)
        # No shipped case is test-covered today; a seeded one shows the skip.
        self.assertEqual([], skipped)
        with tempfile.TemporaryDirectory() as directory:
            seeded, _ = load_cases(with_covered_case(directory))
            _, covered = load_cases(with_covered_case(directory), ["gates"])
        self.assertNotIn(COVERED_CASE["id"], {case.id for case in seeded})
        self.assertEqual(
            [(COVERED_CASE["id"], "covered by tests/test_project_state.py")],
            [(case.id, reason) for case, reason in covered],
        )
        only, _ = load_cases(ROOT, ["complexity"], ["unknown-root-cause-is-complex"])
        self.assertEqual(["unknown-root-cause-is-complex"], [case.id for case in only])
        with self.assertRaisesRegex(EvalError, "unknown eval family: results"):
            load_cases(ROOT, ["results"])
        with self.assertRaisesRegex(EvalError, "unknown judgment case: no-such-case"):
            load_cases(ROOT, None, ["no-such-case"])

    def test_the_phase_six_cases_are_present(self) -> None:
        cases, _ = load_cases(ROOT, ["gates", "planning"])
        ids = {case.id for case in cases}
        for case_id in (
            "deliver-refuses-without-verification-run",
            "critic-prompt-stays-cold",
            "refused-security-lens-reroutes-once",
            "planner-returns-full-plan-with-phases-json",
        ):
            self.assertIn(case_id, ids)

    def test_every_family_contract_list_fits_both_instruction_channels(self) -> None:
        self.assertTrue((ROOT / GRADER).is_file())
        setting = settings_for(PAYLOAD, "codex", "gates")[0]
        for family, contracts in FAMILY_CONTRACTS.items():
            with self.subTest(family=family):
                loaded = _contracts(ROOT, contracts)
                self.assertEqual(list(contracts), [path for path, _, _ in loaded])
                route = eval_route(PAYLOAD, "codex", setting, f"eval.{family}", contracts, ("x",))
                text = _toml_string(worker_instructions(route, loaded))
                self.assertLess(len(text.encode("utf-8")), CODEX_INSTRUCTIONS_LIMIT)

    def test_the_answer_prompt_names_the_keys_but_never_the_expected_values(self) -> None:
        cases, _ = load_cases(ROOT)
        for case in cases:
            prompt = answer_prompt(case)
            situation = case.input if isinstance(case.input, str) else json.dumps(case.input)
            with self.subTest(case=case.id):
                for key in answer_keys(case):
                    self.assertIn(f"`{key}`", prompt)
                for value in case.expected.values():
                    text = value if isinstance(value, str) else None
                    if text and len(text) > 2 and text not in situation:
                        self.assertNotIn(text, prompt)
        qualified = Case("gates", "q", "x", {"status": "RETRY", "never": "PASS"})
        self.assertEqual(["status"], answer_keys(qualified))
        graded = grader_prompt(qualified, "{\"status\": \"RETRY\"}")
        self.assertIn('"never": "PASS"', graded)
        self.assertIn("ANSWER_BEGIN\n{\"status\": \"RETRY\"}\nANSWER_END\n", graded)

    def test_a_verdict_must_open_the_grader_summary(self) -> None:
        self.assertEqual("PASS", verdict("Verdict: PASS\nall keys match"))
        self.assertEqual("FAIL", verdict("\n  Verdict: FAIL  \n"))
        self.assertIsNone(verdict("The answer quotes it.\nVerdict: PASS"))
        self.assertIsNone(verdict("Verdict: MAYBE"))


class SettingTests(unittest.TestCase):
    def test_defaults_follow_the_owner_of_each_familys_decisions(self) -> None:
        planning = next(item for item in PAYLOAD["routes"] if item["name"] == "planning")
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider):
                (setting,) = settings_for(PAYLOAD, provider, "planning")
                self.assertEqual(planning["providers"][provider]["model"], setting.model)
                self.assertEqual(planning["effort"], setting.effort)
                (setting,) = settings_for(PAYLOAD, provider, "gates")
                self.assertEqual(PAYLOAD["policy"]["orchestrator"][provider], setting.model)
                self.assertEqual(PAYLOAD["policy"]["efforts"]["standard"], setting.effort)
                catalog = PAYLOAD["providers"][provider]["models"]
                self.assertEqual(catalog[setting.model]["selector"], setting.selector)

    def test_models_and_effort_override_every_family_and_must_exist(self) -> None:
        settings = settings_for(PAYLOAD, "claude", "gates", ["opus", "sonnet", "opus"], "medium")
        self.assertEqual(["opus/medium", "sonnet/medium"], [s.label for s in settings])
        with self.assertRaisesRegex(EvalError, "unknown claude model family: sol"):
            settings_for(PAYLOAD, "claude", "gates", ["sol"])
        with self.assertRaisesRegex(EvalError, "effort must be one of"):
            settings_for(PAYLOAD, "codex", "gates", [], "ultra")
        with self.assertRaisesRegex(EvalError, "unknown provider"):
            plan(ROOT, "gemini")

    def test_eval_dispatches_are_read_only_and_carry_no_reviewed_tree(self) -> None:
        setting = settings_for(PAYLOAD, "claude", "gates")[0]
        route = eval_route(PAYLOAD, "claude", setting, "eval.gates", FAMILY_CONTRACTS["gates"], ("x",))
        self.assertEqual("plan", route.controls["permission_mode"])
        self.assertEqual(["Write", "Edit", "NotebookEdit"], route.controls["disallowed_tools"])
        self.assertEqual(("Read", "Grep", "Glob"), route.tools)
        codex = eval_route(PAYLOAD, "codex", settings_for(PAYLOAD, "codex", "gates")[0], "eval.gates",
                           FAMILY_CONTRACTS["gates"], ("x",))
        self.assertEqual("read-only", codex.controls["sandbox"])


class RunnerTests(unittest.TestCase):
    def run_stub(self, stub: StubModelRun, **options: object):
        return run_eval(ROOT, "claude", dispatch=stub, now=NOW, **options)

    def test_the_runner_answers_grades_and_writes_a_results_table(self) -> None:
        cases = ["existing-pattern-form-field", "unknown-root-cause-is-complex"]
        refused = envelope(None, None, {"code": "MODEL_ROUTE_REFUSED", "category": "refusal",
                                        "message": "claude-opus-5-5 declined"})
        stub = StubModelRun(
            {"existing-pattern-form-field": '{"complexity": "STANDARD"}',
             "unknown-root-cause-is-complex": refused},
            {"existing-pattern-form-field": ("FAIL", ["size: expected M; answer null"])},
        )
        run = self.run_stub(stub, selected=["complexity"], models=["sonnet", "opus"],
                            command="bin/aitk eval --provider claude --family complexity")
        # Two settings, two cases: two answers each, one grade per answered case.
        self.assertEqual(6, len(stub.calls))
        self.assertEqual(
            {"claude-sonnet-5-5", "claude-opus-5-5"},
            {selector for boundary, selector, _ in stub.calls if boundary == "eval.complexity"},
        )
        self.assertEqual(
            {"claude-opus-5-5"},
            {selector for boundary, selector, _ in stub.calls if boundary == "eval.grade"},
            "the grader is the provider's review route",
        )
        verdicts = {(o.case.id, o.setting.label): o.verdict for o in run.outcomes}
        self.assertEqual("FAIL", verdicts[("existing-pattern-form-field", "sonnet/high")])
        self.assertEqual("ERROR", verdicts[("unknown-root-cause-is-complex", "opus/high")])
        text = render(run)
        self.assertIn("## Run 2026-10-11T14:03:22Z", text)
        self.assertIn("- Grader: claude opus at high effort, `evals/grader.md`", text)
        self.assertIn("- Command: `bin/aitk eval --provider claude --family complexity`", text)
        self.assertIn("| sonnet/high | 0 | 1 | 1 | 0 | 0% | $0.0200 | $0.0100 |", text)
        # A committed results file names model families, never a selector.
        for provider in PAYLOAD["providers"].values():
            for model in provider["models"].values():
                self.assertNotIn(model["selector"], text)
        self.assertIn("| complexity | 0/2 | 0/2 |", text)
        self.assertIn("| `existing-pattern-form-field` | complexity | FAIL | FAIL |", text)
        self.assertIn(
            "- `existing-pattern-form-field` on sonnet/high: FAIL — size: expected M; answer null", text
        )
        self.assertIn("- `unknown-root-cause-is-complex` on opus/high: ERROR — refused (refusal): opus declined", text)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.md"
            self.assertEqual(output, write_results(ROOT, run, output))
            first = output.read_text()
            self.assertTrue(first.startswith("# Eval results: claude, 2026-10-11\n\n## Run "))
            write_results(ROOT, run, output)
            second = output.read_text()
            # A second run the same day (an effort sweep) appends a section.
            self.assertEqual(2, second.count("## Run 2026-10-11T14:03:22Z"))
            self.assertEqual(1, second.count("# Eval results"))
            self.assertTrue(second.startswith(first.rstrip("\n")))

    def test_a_grader_without_a_verdict_leaves_the_case_ungraded(self) -> None:
        def stub(route, prompt):
            if route.boundary == "eval.grade":
                return 0, envelope(worker("looks right to me\nVerdict: PASS"))
            return 0, envelope(worker('{"complexity": "COMPLEX"}'))

        run = run_eval(ROOT, "claude", ["complexity"], ["unknown-root-cause-is-complex"],
                       dispatch=stub, now=NOW)
        (outcome,) = run.outcomes
        self.assertEqual("UNGRADED", outcome.verdict)
        self.assertIn("no verdict", outcome.detail[0])
        self.assertIn("| `unknown-root-cause-is-complex` | complexity | UNGRADED |", render(run))

    def test_results_go_to_the_dated_provider_file(self) -> None:
        self.assertEqual(
            ROOT / "evals" / "results" / "2026-10-11-codex.md", results_path(ROOT, "codex", NOW)
        )

    def test_skipped_cases_are_listed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_eval(with_covered_case(directory), "codex", ["gates"], [COVERED_CASE["id"]],
                           dispatch=StubModelRun({}, {}), now=NOW)
        self.assertEqual((), run.outcomes)
        self.assertIn(
            f"- `{COVERED_CASE['id']}` (gates): covered by tests/test_project_state.py", render(run)
        )


class TransportRunnerTests(unittest.TestCase):
    """The real `model-run` transport, with a stub process runner and no binary."""

    def run_through_transport(self, provider: str, runner) -> object:
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as home, mock.patch(
            "aitk.routing_transport.shutil.which", side_effect=lambda name: f"/stub/{name}"
        ), mock.patch.dict(os.environ, {"CODEX_HOME": home}):
            dispatch = transport_dispatch(ROOT, Path(workspace), 60, runner)
            return run_eval(ROOT, provider, ["complexity"], ["existing-pattern-form-field"],
                            dispatch=dispatch, now=NOW)

    def test_claude_answers_and_grades_with_the_contracts_in_the_instruction_channel(self) -> None:
        calls: list[dict[str, object]] = []

        def runner(argv, **options):
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, "2.1.284\n", "")
            instructions = Path(argv[argv.index("--append-system-prompt-file") + 1]).read_text()
            calls.append({"argv": list(argv), "input": options["input"], "instructions": instructions})
            grading = "boundary=eval.grade\n" in instructions
            result = worker("Verdict: PASS\n") if grading else worker(
                '{"complexity": "STANDARD", "size": "M", "shape": "SINGLE_PHASE", "premium_calls": 0}'
            )
            output = {"type": "result", "subtype": "success", "is_error": False,
                      "structured_output": result, "total_cost_usd": 0.25 if grading else 0.5,
                      "usage": {"input_tokens": 10, "output_tokens": 5}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(output), "")

        run = self.run_through_transport("claude", runner)
        (outcome,) = run.outcomes
        self.assertEqual("PASS", outcome.verdict)
        self.assertEqual((0.5, 0.25), (outcome.answer_cost, outcome.grader_cost))
        answer, grade = calls
        self.assertIn("CONTRACT path=rules/complexity-gate.md\n", answer["instructions"])
        self.assertIn("route=eval\nboundary=eval.complexity\n", answer["instructions"])
        self.assertNotIn(GRADER, answer["instructions"])
        argv = answer["argv"]
        self.assertEqual("claude-sonnet-5-5", argv[argv.index("--model") + 1])
        self.assertEqual("plan", argv[argv.index("--permission-mode") + 1])
        self.assertIn("Add a form field to the connection modal", answer["input"])
        self.assertNotIn("SINGLE_PHASE", answer["input"])
        self.assertIn(f"CONTRACT path={GRADER}\n", grade["instructions"])
        self.assertIn("grading=summary must contain these lines", grade["instructions"])
        self.assertEqual("claude-opus-5-5", grade["argv"][grade["argv"].index("--model") + 1])
        self.assertIn('"shape": "SINGLE_PHASE"', grade["input"])

    def test_codex_tokens_are_priced_when_the_provider_reports_no_cost(self) -> None:
        def runner(argv, **options):
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, "codex-cli 0.159.3\n", "")
            overrides = [argv[i + 1] for i, item in enumerate(argv) if item == "--config"]
            grading = any("boundary=eval.grade" in item for item in overrides)
            result = worker("Verdict: FAIL", ["size: expected M; answer L"]) if grading else worker('{"size": "L"}')
            Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(result))
            usage = {"input_tokens": 1_000_000, "cached_input_tokens": 400_000, "output_tokens": 100_000}
            return subprocess.CompletedProcess(argv, 0, json.dumps({"type": "turn.completed", "usage": usage}), "")

        run = self.run_through_transport("codex", runner)
        (outcome,) = run.outcomes
        self.assertEqual("FAIL", outcome.verdict)
        self.assertEqual(("size: expected M; answer L",), outcome.detail)
        expected = compute_cost(
            {"input_tokens": 600_000, "cache_read_input_tokens": 400_000, "output_tokens": 100_000},
            "gpt-6.1-sol", NOW.isoformat(),
        )
        self.assertGreater(expected, 0)
        self.assertAlmostEqual(expected, outcome.answer_cost)
        self.assertAlmostEqual(expected, outcome.grader_cost)


STUB = """#!{python}
import json, sys
from pathlib import Path
args = sys.argv[1:]
if "--version" in args:
    print("2.1.284" if Path(sys.argv[0]).name == "claude" else "codex-cli 0.159.3")
    raise SystemExit(0)
Path({marker!r}).write_text("a provider was asked to answer")
instructions = Path(args[args.index("--append-system-prompt-file") + 1]).read_text()
if "boundary=eval.grade" in instructions:
    summary = "Verdict: PASS"
else:
    summary = json.dumps({{"complexity": "STANDARD"}})
result = {{"status": "completed", "summary": summary, "findings": [], "verification": ["read"]}}
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "structured_output": result, "total_cost_usd": 0.001}}))
"""


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name).resolve()
        self.stubs = self.directory / "bin"
        self.stubs.mkdir()
        self.marker = self.directory / "provider-called"
        for name in ("claude", "codex"):
            path = self.stubs / name
            path.write_text(STUB.format(python=sys.executable, marker=str(self.marker)))
            path.chmod(0o755)
        self.environment = {
            "PATH": f"{self.stubs}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(self.directory),
            "PYTHONPATH": str(ROOT),
        }
        for name in ("claude", "codex"):
            found = shutil.which(name, path=self.environment["PATH"])
            self.assertEqual(str(self.stubs / name), found, "a real provider CLI would be reachable")
        self.results = ROOT / "evals" / "results"
        self.results_existed = self.results.exists()

    def tearDown(self) -> None:
        self.temporary.cleanup()
        self.assertEqual(self.results_existed, self.results.exists(), "a test wrote into the toolkit's evals/")

    def aitk(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aitk.cli", "--root", str(ROOT), *arguments],
            cwd=self.directory, text=True, capture_output=True, check=False, env=self.environment,
        )

    def test_dry_run_lists_the_dispatches_and_calls_no_provider(self) -> None:
        result = self.aitk("eval", "--provider", "codex", "--dry-run", "--family", "planning",
                           "--model", "sol", "--model", "astra", "--effort", "medium")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("eval plan: provider codex", result.stdout)
        self.assertIn("sol/medium (gpt-6.1-sol), astra/medium (gpt-6-astra)", result.stdout)
        self.assertFalse(self.marker.exists())
        unknown = self.aitk("eval", "--provider", "claude", "--dry-run", "--model", "haiku")
        self.assertEqual(2, unknown.returncode)
        self.assertIn("unknown claude model family: haiku", unknown.stderr)

    def test_a_run_through_stub_clis_appends_its_results_file(self) -> None:
        output = self.directory / "results" / "run.md"
        result = self.aitk("eval", "--provider", "claude", "--family", "complexity",
                           "--case", "existing-pattern-form-field", "--output", str(output))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(self.marker.exists(), "the stub provider answered")
        self.assertIn("sonnet/high (claude-sonnet-5-5): 1 pass, 0 fail, 0 error, 0 ungraded", result.stdout)
        text = output.read_text()
        self.assertIn("| `existing-pattern-form-field` | complexity | PASS |", text)
        self.assertIn(
            "- Command: `bin/aitk eval --provider claude --family complexity "
            "--case existing-pattern-form-field`",
            text,
        )

    def test_a_run_that_grades_nothing_exits_three(self) -> None:
        for name in ("claude", "codex"):
            (self.stubs / name).write_text("#!/bin/sh\nexit 1\n")
        output = self.directory / "run.md"
        result = self.aitk("eval", "--provider", "claude", "--family", "complexity", "--output", str(output))
        self.assertEqual(3, result.returncode, result.stderr)
        self.assertIn("0 pass, 0 fail, 2 error", result.stdout)
        self.assertIn("ERROR", output.read_text())


if __name__ == "__main__":
    unittest.main()
