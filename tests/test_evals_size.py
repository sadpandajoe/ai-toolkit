"""Tests for the evals/size/ checker factory (aitk.evals_size)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_size import make_checker


def test_valid_fixture_passes(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, _ = checker({"scenario": "add a toggle", "expect_size": "S"})
    assert passed


def test_invalid_size_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker({"scenario": "add a toggle", "expect_size": "HUGE"})
    assert not passed
    assert "not one of" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "size"]) == 0
