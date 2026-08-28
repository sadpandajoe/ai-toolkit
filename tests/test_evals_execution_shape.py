"""Tests for the evals/execution_shape/ checker factory (aitk.evals_execution_shape)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_execution_shape import make_checker


def test_valid_fixture_passes(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, _ = checker({"scenario": "rename a symbol everywhere", "expect_execution_shape": "BATCHED"})
    assert passed


def test_invalid_shape_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, reason = checker({"scenario": "x", "expect_execution_shape": "ONE_SHOT"})
    assert not passed
    assert "not one of" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "execution_shape"]) == 0
