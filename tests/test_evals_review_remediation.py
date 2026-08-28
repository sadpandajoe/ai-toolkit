"""Tests for the evals/review_remediation/ checker factory (aitk.evals_review_remediation)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_review_remediation import make_checker


def test_approve_maps_to_pass(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, _ = checker(
        {"scenario": "x", "review_verdict": "APPROVE", "expect_gate_state": "PASS"}
    )
    assert passed


def test_replan_may_map_to_either_reclassify_or_escalate(tmp_path: Path):
    checker = make_checker(tmp_path)
    for state in ("RECLASSIFY", "ESCALATE"):
        passed, _ = checker(
            {"scenario": "x", "review_verdict": "REPLAN", "expect_gate_state": state}
        )
        assert passed


def test_approve_cannot_map_to_retry(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker(
        {"scenario": "x", "review_verdict": "APPROVE", "expect_gate_state": "RETRY"}
    )
    assert not passed
    assert "maps to" in reason


def test_unknown_verdict_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker(
        {"scenario": "x", "review_verdict": "LGTM", "expect_gate_state": "PASS"}
    )
    assert not passed
    assert "not one of" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "review_remediation"]) == 0
