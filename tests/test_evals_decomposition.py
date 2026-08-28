"""Tests for the evals/decomposition/ checker factory (aitk.evals_decomposition)."""

from pathlib import Path

from aitk.cli import main
from aitk.evals_decomposition import make_checker


def _valid_fixture():
    return {
        "scenario": "multi-subsystem editor",
        "boundaries": ["a", "b"],
        "dependencies": ["a before b"],
        "invariants": ["shared state stays consistent"],
        "risks": ["schema drift"],
        "phase_exit_goals": ["a done", "b done"],
    }


def test_valid_fixture_passes(tmp_path: Path):
    checker = make_checker(tmp_path)
    passed, _ = checker(_valid_fixture())
    assert passed


def test_empty_list_field_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    fixture = _valid_fixture()
    fixture["risks"] = []
    passed, reason = checker(fixture)
    assert not passed
    assert "risks" in reason


def test_non_list_field_fails(tmp_path: Path):
    checker = make_checker(tmp_path)
    fixture = _valid_fixture()
    fixture["boundaries"] = "just one string"
    passed, reason = checker(fixture)
    assert not passed
    assert "boundaries" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    assert main(["evals-run", "--family", "decomposition"]) == 0
