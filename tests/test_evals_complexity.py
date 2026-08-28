"""Tests for the evals/complexity/ checker factory (aitk.evals_complexity)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_complexity import make_checker


def test_valid_fixture_passes(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, _ = checker({"scenario": "add a toggle", "expect_complexity": "STANDARD"})
    assert passed


def test_missing_scenario_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker({"expect_complexity": "STANDARD"})
    assert not passed
    assert "scenario" in reason


def test_invalid_complexity_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker({"scenario": "add a toggle", "expect_complexity": "EASY"})
    assert not passed
    assert "not one of" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "complexity"]) == 0
