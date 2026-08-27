"""Tests for the minimal eval-harness (aitk.evals) and its `evals-run` CLI wiring."""

from pathlib import Path

import pytest

from aitk import cli
from aitk.cli import main
from aitk.evals import EvalError, EvalResult, load_fixtures, run_family, run_fixture


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
