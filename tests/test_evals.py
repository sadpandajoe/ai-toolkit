"""Tests for the minimal eval-harness (aitk.evals) and its `evals-run` CLI wiring."""

from pathlib import Path

import pytest

from aitk import cli
from aitk.cli import main
from aitk.evals import EvalError, EvalResult, load_fixtures, run_family, run_fixture

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_fixtures_on_missing_directory_returns_empty(tmp_path: Path):
    assert load_fixtures(tmp_path / "does-not-exist") == []


def test_load_fixtures_sorts_by_filename_and_defaults_name_to_stem(tmp_path: Path):
    (tmp_path / "b.json").write_text('{"input": "second"}')
    (tmp_path / "a.json").write_text('{"input": "first", "name": "explicit"}')

    fixtures = load_fixtures(tmp_path)

    assert [f["name"] for f in fixtures] == ["explicit", "b"]


def test_load_fixtures_rejects_invalid_json(tmp_path: Path):
    (tmp_path / "broken.json").write_text("{not valid json")

    with pytest.raises(EvalError):
        load_fixtures(tmp_path)


def test_load_fixtures_rejects_non_object_fixture(tmp_path: Path):
    (tmp_path / "list.json").write_text("[1, 2, 3]")

    with pytest.raises(EvalError):
        load_fixtures(tmp_path)


def test_run_fixture_reports_pass_and_fail():
    def checker(fixture):
        return (fixture["input"] == "expected", "checked input")

    passing = run_fixture({"name": "ok", "input": "expected"}, checker)
    failing = run_fixture({"name": "bad", "input": "other"}, checker)

    assert passing == EvalResult(name="ok", passed=True, reason="checked input")
    assert failing == EvalResult(name="bad", passed=False, reason="checked input")


def test_run_family_combines_load_and_run(tmp_path: Path):
    (tmp_path / "one.json").write_text('{"input": "x"}')
    (tmp_path / "two.json").write_text('{"input": "y"}')

    def checker(fixture):
        return (fixture["input"] == "x", fixture["input"])

    results = run_family(tmp_path, checker)

    assert [(r.name, r.passed) for r in results] == [("one", True), ("two", False)]


def test_cli_evals_run_rejects_unregistered_family(tmp_path: Path, capsys):
    exit_code = main(["evals-run", "--family", "no-such-family", "--root", str(tmp_path)])

    assert exit_code == 1
    assert "no checker registered" in capsys.readouterr().err


def test_cli_evals_run_passes_resolved_root_to_the_checker_factory(
    tmp_path: Path, capsys, monkeypatch
):
    seen_roots = []

    def factory(root):
        seen_roots.append(root)
        return lambda fixture: (True, "n/a")

    monkeypatch.setitem(cli.EVAL_CHECKERS, "demo", factory)

    main(["evals-run", "--family", "demo", "--root", str(tmp_path)])

    assert seen_roots == [tmp_path.resolve()]


def test_cli_evals_run_reports_no_fixtures_when_family_dir_absent(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setitem(cli.EVAL_CHECKERS, "demo", lambda root: (lambda fixture: (True, "n/a")))

    exit_code = main(["evals-run", "--family", "demo", "--root", str(tmp_path)])

    assert exit_code == 0
    assert "no fixtures found" in capsys.readouterr().out


def test_cli_evals_run_live_refuses_unconditionally(tmp_path: Path, capsys):
    exit_code = main(["evals-run", "--family", "complexity", "--live", "--root", str(tmp_path)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "not implemented" in err
    assert "dispatch boundary" in err


def test_cli_evals_run_aggregates_pass_and_fail(tmp_path: Path, capsys, monkeypatch):
    family_dir = tmp_path / "evals" / "demo"
    family_dir.mkdir(parents=True)
    (family_dir / "good.json").write_text('{"input": "x"}')
    (family_dir / "bad.json").write_text('{"input": "y"}')

    monkeypatch.setitem(
        cli.EVAL_CHECKERS,
        "demo",
        lambda root: (lambda fixture: (fixture["input"] == "x", fixture["input"])),
    )

    exit_code = main(["evals-run", "--family", "demo", "--root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "[PASS] good" in output
    assert "[FAIL] bad" in output
    assert "1/2 passed" in output


# --- Per-family checker factories (aitk.evals_<family>) -------------------
# Each class below covers one evals/<family>/ checker: fixture validation
# plus one run against the real repo fixtures under evals/<family>/.


class TestComplexityChecker:
    """aitk.evals_complexity"""

    def test_valid_fixture_passes(self, tmp_path: Path):
        from aitk.evals_complexity import make_checker

        checker = make_checker(tmp_path)
        passed, _ = checker({"scenario": "add a toggle", "expect_complexity": "STANDARD"})
        assert passed

    def test_missing_scenario_fails(self, tmp_path: Path):
        from aitk.evals_complexity import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker({"expect_complexity": "STANDARD"})
        assert not passed
        assert "scenario" in reason

    def test_invalid_complexity_fails(self, tmp_path: Path):
        from aitk.evals_complexity import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker({"scenario": "add a toggle", "expect_complexity": "EASY"})
        assert not passed
        assert "not one of" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "complexity"]) == 0


class TestDecompositionChecker:
    """aitk.evals_decomposition"""

    @staticmethod
    def _valid_fixture():
        return {
            "scenario": "multi-subsystem editor",
            "boundaries": ["a", "b"],
            "dependencies": ["a before b"],
            "invariants": ["shared state stays consistent"],
            "risks": ["schema drift"],
            "phase_exit_goals": ["a done", "b done"],
        }

    def test_valid_fixture_passes(self, tmp_path: Path):
        from aitk.evals_decomposition import make_checker

        checker = make_checker(tmp_path)
        passed, _ = checker(self._valid_fixture())
        assert passed

    def test_empty_list_field_fails(self, tmp_path: Path):
        from aitk.evals_decomposition import make_checker

        checker = make_checker(tmp_path)
        fixture = self._valid_fixture()
        fixture["risks"] = []
        passed, reason = checker(fixture)
        assert not passed
        assert "risks" in reason

    def test_non_list_field_fails(self, tmp_path: Path):
        from aitk.evals_decomposition import make_checker

        checker = make_checker(tmp_path)
        fixture = self._valid_fixture()
        fixture["boundaries"] = "just one string"
        passed, reason = checker(fixture)
        assert not passed
        assert "boundaries" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "decomposition"]) == 0


class TestEscalationChecker:
    """aitk.evals_escalation"""

    def test_mechanical_never_advances_count(self, tmp_path: Path):
        from aitk.evals_escalation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "reason": "flaky test",
                "kind": "mechanical",
                "previous_count": 3,
                "expect_state": "RETRY",
                "expect_count": 3,
            }
        )
        assert passed, reason

    def test_reasoning_second_failure_escalates(self, tmp_path: Path):
        from aitk.evals_escalation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "reason": "root cause misdiagnosed",
                "kind": "reasoning",
                "previous_count": 1,
                "expect_state": "ESCALATE",
                "expect_count": 2,
            }
        )
        assert passed, reason

    def test_wrong_expected_state_fails(self, tmp_path: Path):
        from aitk.evals_escalation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "reason": "root cause misdiagnosed",
                "kind": "reasoning",
                "previous_count": 1,
                "expect_state": "RETRY",
            }
        )
        assert not passed
        assert "expected 'RETRY'" in reason

    def test_missing_field_fails(self, tmp_path: Path):
        from aitk.evals_escalation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker({"reason": "x", "kind": "mechanical"})
        assert not passed
        assert "previous_count" in reason

    def test_invalid_kind_fails(self, tmp_path: Path):
        from aitk.evals_escalation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {"reason": "x", "kind": "vibes", "previous_count": 0, "expect_state": "RETRY"}
        )
        assert not passed
        assert "decide_failure raised" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "escalation"]) == 0


class TestExecutionShapeChecker:
    """aitk.evals_execution_shape"""

    def test_valid_fixture_passes(self, tmp_path: Path):
        from aitk.evals_execution_shape import make_checker

        checker = make_checker(tmp_path)
        passed, _ = checker(
            {"scenario": "rename a symbol everywhere", "expect_execution_shape": "BATCHED"}
        )
        assert passed

    def test_invalid_shape_fails(self, tmp_path: Path):
        from aitk.evals_execution_shape import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker({"scenario": "x", "expect_execution_shape": "ONE_SHOT"})
        assert not passed
        assert "not one of" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "execution_shape"]) == 0


class TestPhaseabilityChecker:
    """aitk.evals_phaseability"""

    def test_valid_fixture_passes(self, tmp_path: Path):
        from aitk.evals_phaseability import make_checker

        checker = make_checker(tmp_path)
        passed, _ = checker(
            {
                "scenario": "big multi-subsystem editor",
                "signal_summary": "several independently verifiable subsystems",
                "expect_reason": "needs its own verification per boundary",
                "expect_execution_shape": "MULTI_PHASE",
            }
        )
        assert passed

    def test_missing_signal_summary_fails(self, tmp_path: Path):
        from aitk.evals_phaseability import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "scenario": "x",
                "expect_reason": "y",
                "expect_execution_shape": "SINGLE_PHASE",
            }
        )
        assert not passed
        assert "signal_summary" in reason

    def test_missing_expect_reason_fails(self, tmp_path: Path):
        from aitk.evals_phaseability import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "scenario": "x",
                "signal_summary": "y",
                "expect_execution_shape": "SINGLE_PHASE",
            }
        )
        assert not passed
        assert "expect_reason" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "phaseability"]) == 0


class TestReviewRemediationChecker:
    """aitk.evals_review_remediation"""

    def test_approve_maps_to_pass(self, tmp_path: Path):
        from aitk.evals_review_remediation import make_checker

        checker = make_checker(tmp_path)
        passed, _ = checker(
            {"scenario": "x", "review_verdict": "APPROVE", "expect_gate_state": "PASS"}
        )
        assert passed

    def test_replan_may_map_to_either_reclassify_or_escalate(self, tmp_path: Path):
        from aitk.evals_review_remediation import make_checker

        checker = make_checker(tmp_path)
        for state in ("RECLASSIFY", "ESCALATE"):
            passed, _ = checker(
                {"scenario": "x", "review_verdict": "REPLAN", "expect_gate_state": state}
            )
            assert passed

    def test_approve_cannot_map_to_retry(self, tmp_path: Path):
        from aitk.evals_review_remediation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {"scenario": "x", "review_verdict": "APPROVE", "expect_gate_state": "RETRY"}
        )
        assert not passed
        assert "maps to" in reason

    def test_unknown_verdict_fails(self, tmp_path: Path):
        from aitk.evals_review_remediation import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {"scenario": "x", "review_verdict": "LGTM", "expect_gate_state": "PASS"}
        )
        assert not passed
        assert "not one of" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "review_remediation"]) == 0


class TestSizeChecker:
    """aitk.evals_size"""

    def test_valid_fixture_passes(self, tmp_path: Path):
        from aitk.evals_size import make_checker

        checker = make_checker(tmp_path)
        passed, _ = checker({"scenario": "add a toggle", "expect_size": "S"})
        assert passed

    def test_invalid_size_fails(self, tmp_path: Path):
        from aitk.evals_size import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker({"scenario": "add a toggle", "expect_size": "HUGE"})
        assert not passed
        assert "not one of" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "size"]) == 0


class TestSkillRoutingChecker:
    """aitk.evals_skill_routing"""

    @staticmethod
    def _write_skill(root: Path, name: str, description: str) -> None:
        skill_dir = root / "skills/goals" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n"
        )

    @pytest.fixture
    def repo_root(self, tmp_path: Path) -> Path:
        self._write_skill(
            tmp_path, "fix-bug", "Use when the user reports a bug. Do NOT use for features."
        )
        self._write_skill(
            tmp_path, "create-feature", "Use to build a new feature. Do NOT use for bugs."
        )
        self._write_skill(tmp_path, "fix-ci", "Use when a CI build or check has failed.")
        self._write_skill(tmp_path, "code-review", "Use for a code review of local changes.")
        self._write_skill(
            tmp_path,
            "address-feedback",
            "Use for review comments that need investigation.",
        )
        self._write_skill(tmp_path, "test-pr", "Use to manually verify a PR's behavior.")
        self._write_skill(tmp_path, "cherry-pick", "Cherry-pick, backport, or apply commits.")
        self._write_skill(tmp_path, "refactor", "Refactor, restructure, simplify, clean up code.")
        self._write_skill(
            tmp_path, "watch-pr", "Watch, babysit, and monitor an open PR until stable."
        )
        self._write_skill(
            tmp_path, "release-prep", "Check branch, artifacts, and CI for release readiness."
        )
        return tmp_path

    def test_unique_phrase_passes(self, repo_root: Path):
        from aitk.evals_skill_routing import make_checker

        checker = make_checker(repo_root)
        passed, reason = checker({"phrase": "reports a bug", "expect_skill": "fix-bug"})
        assert passed
        assert "fix-bug" in reason

    def test_phrase_missing_from_expected_skill_fails(self, repo_root: Path):
        from aitk.evals_skill_routing import make_checker

        checker = make_checker(repo_root)
        passed, reason = checker({"phrase": "nonexistent trigger", "expect_skill": "fix-bug"})
        assert not passed
        assert "not found" in reason

    def test_ambiguous_phrase_across_two_skills_fails(self, repo_root: Path):
        from aitk.evals_skill_routing import make_checker

        self._write_skill(repo_root, "fix-bug", "Use when the user reports a bug.")
        self._write_skill(
            repo_root, "create-feature", "Also handles cases where the user reports a bug."
        )
        checker = make_checker(repo_root)

        passed, reason = checker({"phrase": "reports a bug", "expect_skill": "fix-bug"})

        assert not passed
        assert "ambiguous" in reason

    def test_unknown_expect_skill_fails(self, repo_root: Path):
        from aitk.evals_skill_routing import make_checker

        checker = make_checker(repo_root)
        passed, reason = checker({"phrase": "anything", "expect_skill": "not-a-goal-skill"})
        assert not passed
        assert "unknown expect_skill" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        exit_code = main(["evals-run", "--family", "skill_routing"])

        assert exit_code == 0


class TestResumeChecker:
    """aitk.evals_resume"""

    def test_pending_effect_with_observed_digest_applies_it(self, tmp_path: Path):
        from aitk.evals_resume import make_checker

        checker = make_checker(tmp_path)
        digest = "sha256:" + "ab" * 32
        passed, reason = checker(
            {
                "effect": {"status": "pending", "operation_id": "op-1"},
                "strategy": "provider_idempotency",
                "observed_digest": digest,
                "expect_action": "apply-observed",
                "expect_digest": digest,
            }
        )
        assert passed, reason

    def test_manual_stop_strategy_always_halts(self, tmp_path: Path):
        from aitk.evals_resume import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "effect": {"status": "pending", "operation_id": "op-2"},
                "strategy": "manual_stop",
                "observed_digest": "sha256:" + "cd" * 32,
                "expect_action": "stop-for-user",
            }
        )
        assert passed, reason

    def test_wrong_expected_action_fails(self, tmp_path: Path):
        from aitk.evals_resume import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "effect": {"status": "pending", "operation_id": "op-3"},
                "strategy": "provider_idempotency",
                "observed_digest": None,
                "expect_action": "apply-observed",
            }
        )
        assert not passed
        assert "expected 'apply-observed'" in reason

    def test_missing_field_fails_cleanly(self, tmp_path: Path):
        from aitk.evals_resume import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker({"effect": {"status": "pending", "operation_id": "op-4"}})
        assert not passed
        assert "missing required field" in reason

    def test_malformed_effect_fails_cleanly(self, tmp_path: Path):
        from aitk.evals_resume import make_checker

        checker = make_checker(tmp_path)
        passed, reason = checker(
            {
                "effect": {"operation_id": "op-5"},
                "strategy": "provider_idempotency",
                "expect_action": "retry-same-operation-id",
            }
        )
        assert not passed
        assert "missing required field" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "resume"]) == 0


class TestGateTransitionChecker:
    """aitk.evals_gate_transition"""

    def test_legal_single_step_transition_passes(self):
        from aitk.evals_gate_transition import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker(
            {"workflow": "address-feedback", "to_phase": "execute", "expect_result": "legal"}
        )
        assert passed, reason

    def test_illegal_skip_transition_passes_when_expected_illegal(self):
        from aitk.evals_gate_transition import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker(
            {"workflow": "address-feedback", "to_phase": "verify", "expect_result": "illegal"}
        )
        assert passed, reason

    def test_wrong_expectation_fails_with_reason(self):
        from aitk.evals_gate_transition import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker(
            {"workflow": "address-feedback", "to_phase": "verify", "expect_result": "legal"}
        )
        assert not passed
        assert "'illegal'" in reason
        assert "expected 'legal'" in reason

    def test_missing_field_fails_cleanly(self):
        from aitk.evals_gate_transition import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker({"workflow": "address-feedback", "to_phase": "execute"})
        assert not passed
        assert "missing required field" in reason

    def test_unknown_workflow_fails_cleanly(self):
        from aitk.evals_gate_transition import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker(
            {"workflow": "not-a-real-workflow", "to_phase": "execute", "expect_result": "legal"}
        )
        assert not passed
        assert "raised" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "gate_transition"]) == 0


class TestSafetyEffectsChecker:
    """aitk.evals_safety_effects"""

    def test_reserve_then_apply_succeeds(self):
        from aitk.evals_safety_effects import make_checker

        checker = make_checker(REPO_ROOT)
        digest = "sha256:" + "12" * 32
        passed, reason = checker(
            {
                "steps": [
                    {"action": "reserve", "operation_id": "op-1"},
                    {"action": "apply", "operation_id": "op-1", "result_digest": digest},
                ],
                "expect_outcome": "ok",
            }
        )
        assert passed, reason

    def test_apply_without_reserve_fails_at_expected_step(self):
        from aitk.evals_safety_effects import make_checker

        checker = make_checker(REPO_ROOT)
        digest = "sha256:" + "34" * 32
        passed, reason = checker(
            {
                "steps": [{"action": "apply", "operation_id": "op-2", "result_digest": digest}],
                "expect_outcome": "reserved before",
                "expect_fail_step": 0,
            }
        )
        assert passed, reason

    def test_failure_at_wrong_step_is_rejected(self):
        from aitk.evals_safety_effects import make_checker

        checker = make_checker(REPO_ROOT)
        digest = "sha256:" + "56" * 32
        passed, reason = checker(
            {
                "steps": [{"action": "apply", "operation_id": "op-3", "result_digest": digest}],
                "expect_outcome": "reserved before",
                "expect_fail_step": 1,
            }
        )
        assert not passed
        assert "expected the failure at step 1" in reason

    def test_missing_field_fails_cleanly(self):
        from aitk.evals_safety_effects import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker({"steps": []})
        assert not passed
        assert "missing required field" in reason or "nonempty list" in reason

    def test_malformed_step_fails_cleanly(self):
        from aitk.evals_safety_effects import make_checker

        checker = make_checker(REPO_ROOT)
        passed, reason = checker(
            {
                "steps": [{"action": "teleport", "operation_id": "op-4"}],
                "expect_outcome": "ok",
            }
        )
        assert not passed
        assert "invalid action" in reason

    def test_cli_evals_run_against_real_repo_fixtures(self):
        assert main(["evals-run", "--family", "safety_effects"]) == 0
