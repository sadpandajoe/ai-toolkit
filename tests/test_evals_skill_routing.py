"""Tests for the evals/skill_routing/ checker factory (aitk.evals_skill_routing)."""

from pathlib import Path

import pytest

from aitk.cli import main
from aitk.evals_skill_routing import make_checker


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / "skills/goals" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n")


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    _write_skill(tmp_path, "fix-bug", "Use when the user reports a bug. Do NOT use for features.")
    _write_skill(tmp_path, "create-feature", "Use to build a new feature. Do NOT use for bugs.")
    _write_skill(tmp_path, "fix-ci", "Use when a CI build or check has failed.")
    _write_skill(tmp_path, "code-review", "Use for a code review of local changes.")
    _write_skill(tmp_path, "address-feedback", "Use for review comments that need investigation.")
    _write_skill(tmp_path, "test-pr", "Use to manually verify a PR's behavior.")
    _write_skill(tmp_path, "cherry-pick", "Cherry-pick, backport, or apply commits.")
    return tmp_path


def test_unique_phrase_passes(repo_root: Path):
    checker = make_checker(repo_root)
    passed, reason = checker({"phrase": "reports a bug", "expect_skill": "fix-bug"})
    assert passed
    assert "fix-bug" in reason


def test_phrase_missing_from_expected_skill_fails(repo_root: Path):
    checker = make_checker(repo_root)
    passed, reason = checker({"phrase": "nonexistent trigger", "expect_skill": "fix-bug"})
    assert not passed
    assert "not found" in reason


def test_ambiguous_phrase_across_two_skills_fails(repo_root: Path):
    _write_skill(repo_root, "fix-bug", "Use when the user reports a bug.")
    _write_skill(repo_root, "create-feature", "Also handles cases where the user reports a bug.")
    checker = make_checker(repo_root)

    passed, reason = checker({"phrase": "reports a bug", "expect_skill": "fix-bug"})

    assert not passed
    assert "ambiguous" in reason


def test_unknown_expect_skill_fails(repo_root: Path):
    checker = make_checker(repo_root)
    passed, reason = checker({"phrase": "anything", "expect_skill": "not-a-goal-skill"})
    assert not passed
    assert "unknown expect_skill" in reason


def test_cli_evals_run_against_real_repo_fixtures():
    exit_code = main(["evals-run", "--family", "skill_routing"])

    assert exit_code == 0
