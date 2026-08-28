"""Tests for the evals/escalation/ checker factory (aitk.evals_escalation)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_escalation import make_checker


def test_mechanical_never_advances_count(tmp_path: Path):
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


def test_reasoning_second_failure_escalates(tmp_path: Path):
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


def test_wrong_expected_state_fails(tmp_path: Path):
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


def test_missing_field_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker({"reason": "x", "kind": "mechanical"})
    assert not passed
    assert "previous_count" in reason


def test_invalid_kind_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker(
        {"reason": "x", "kind": "vibes", "previous_count": 0, "expect_state": "RETRY"}
    )
    assert not passed
    assert "decide_failure raised" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "escalation"]) == 0
