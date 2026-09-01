"""Tests for aitk.context_budget and the `aitk context-budget` CLI command."""

import json
from pathlib import Path

from aitk.cli import main
from aitk.context_budget import GOAL_SKILL_BUDGET_BYTES, measure_goal_skills


def _write_skill(root: Path, name: str, byte_count: int) -> Path:
    skill_dir = root / "skills/goals" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_bytes(b"x" * byte_count)
    return skill_file


def test_skill_under_budget_passes(tmp_path: Path):
    _write_skill(tmp_path, "under-budget", GOAL_SKILL_BUDGET_BYTES - 1)

    results = measure_goal_skills(tmp_path)

    assert len(results) == 1
    result = results[0]
    assert result.name == "under-budget"
    assert result.byte_count == GOAL_SKILL_BUDGET_BYTES - 1
    assert result.budget == GOAL_SKILL_BUDGET_BYTES
    assert result.passed is True
    assert result.overage == 0


def test_skill_at_budget_passes(tmp_path: Path):
    _write_skill(tmp_path, "at-budget", GOAL_SKILL_BUDGET_BYTES)

    results = measure_goal_skills(tmp_path)

    assert results[0].passed is True
    assert results[0].overage == 0


def test_skill_over_budget_fails_with_correct_overage(tmp_path: Path):
    over_by = 137
    _write_skill(tmp_path, "over-budget", GOAL_SKILL_BUDGET_BYTES + over_by)

    results = measure_goal_skills(tmp_path)

    assert len(results) == 1
    result = results[0]
    assert result.passed is False
    assert result.overage == over_by


def test_results_sorted_by_skill_name(tmp_path: Path):
    _write_skill(tmp_path, "zeta", 100)
    _write_skill(tmp_path, "alpha", 100)

    results = measure_goal_skills(tmp_path)

    assert [result.name for result in results] == ["alpha", "zeta"]


def test_missing_goals_directory_returns_empty(tmp_path: Path):
    assert measure_goal_skills(tmp_path) == []


def test_skill_dir_without_skill_md_is_skipped(tmp_path: Path):
    (tmp_path / "skills/goals/no-skill-file").mkdir(parents=True)

    assert measure_goal_skills(tmp_path) == []


def test_cli_context_budget_exit_code_reflects_failures(tmp_path: Path, capsys):
    _write_skill(tmp_path, "passing", 100)
    _write_skill(tmp_path, "failing", GOAL_SKILL_BUDGET_BYTES + 1)

    exit_code = main(["--root", str(tmp_path), "context-budget"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "passing" in output
    assert "PASS" in output
    assert "failing" in output
    assert "FAIL" in output


def test_cli_context_budget_json_output(tmp_path: Path, capsys):
    _write_skill(tmp_path, "solo", 100)

    exit_code = main(["--root", str(tmp_path), "context-budget", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "context-budget"
    assert payload["summary"] == {"PASS": 1, "FAIL": 0}
    assert payload["skills"][0]["name"] == "solo"
    assert payload["skills"][0]["status"] == "PASS"


def test_real_repo_goal_skills_all_pass_budget():
    """Regression test for G2's exit criterion: every real goal skill's
    SKILL.md must fit within the context budget after trimming."""
    root = Path(__file__).resolve().parents[1]

    results = measure_goal_skills(root)

    assert results, "expected skills/goals/*/SKILL.md to exist"
    failing = [result for result in results if not result.passed]
    assert not failing, [
        f"{result.name}: {result.byte_count} bytes (over by {result.overage})"
        for result in failing
    ]
