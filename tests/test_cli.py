"""Tests for the aitk CLI's project-state / routing-state subcommands."""

import json
from pathlib import Path

import pytest

from aitk.cli import main


def test_project_state_on_missing_file_reports_both_null(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"file": str(path), "checkpoint": None, "routing": None}


def test_routing_state_set_then_project_state_shows_it(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    exit_code = main(
        [
            "routing-state",
            "set",
            "--file",
            str(path),
            "--complexity",
            "STANDARD",
            "--confidence",
            "7",
            "--reason",
            "touches three modules",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()  # discard the human-readable confirmation

    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["routing"] == {
        "schema_version": 1,
        "complexity": "STANDARD",
        "confidence": 7,
        "reason": "touches three modules",
    }
    assert payload["checkpoint"] is None


def test_routing_state_set_json_flag_prints_payload(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    exit_code = main(
        [
            "routing-state",
            "set",
            "--file",
            str(path),
            "--complexity",
            "TRIVIAL",
            "--confidence",
            "9",
            "--reason",
            "one-line fix",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complexity"] == "TRIVIAL"
    assert payload["confidence"] == 9


def test_routing_state_set_on_missing_file_fails(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    exit_code = main(
        [
            "routing-state",
            "set",
            "--file",
            str(path),
            "--complexity",
            "TRIVIAL",
            "--confidence",
            "5",
            "--reason",
            "reason",
        ]
    )
    assert exit_code == 1
    assert "routing-state artifact is missing" in capsys.readouterr().err


def test_routing_state_set_rejects_invalid_complexity_choice(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "routing-state",
                "set",
                "--file",
                str(path),
                "--complexity",
                "COMPLEX",
                "--confidence",
                "5",
                "--reason",
                "reason",
            ]
        )
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_project_state_defaults_to_cwd_project_md(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    exit_code = main(["project-state"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["file"] == str(tmp_path / "PROJECT.md")
