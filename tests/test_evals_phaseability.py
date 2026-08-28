"""Tests for the evals/phaseability/ checker factory (aitk.evals_phaseability)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_phaseability import make_checker


def test_valid_fixture_passes(tmp_path: Path):
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


def test_missing_signal_summary_fails(tmp_path: Path):
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


def test_missing_expect_reason_fails(tmp_path: Path):
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


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "phaseability"]) == 0
