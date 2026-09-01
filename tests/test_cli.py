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
    assert payload == {
        "file": str(path),
        "checkpoint": None,
        "routing": None,
        "gates": None,
        "size_axis": {},
    }


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
        "schema_version": 2,
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
                "MODERATE",
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


def test_gate_state_set_then_project_state_shows_it(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    exit_code = main(
        [
            "gate-state",
            "set",
            "--file",
            str(path),
            "--gate",
            "review",
            "--state",
            "RETRY",
            "--reason",
            "missing test coverage",
            "--count",
            "1",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()  # discard the human-readable confirmation

    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["gates"] == {
        "review": {
            "state": "RETRY",
            "reason": "missing test coverage",
            "count": 1,
            "kind": "reasoning",
        }
    }
    assert payload["checkpoint"] is None
    assert payload["routing"] is None


def test_gate_state_set_rejects_invalid_state_choice(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "gate-state",
                "set",
                "--file",
                str(path),
                "--gate",
                "review",
                "--state",
                "NOT_A_STATE",
                "--reason",
                "reason",
                "--count",
                "1",
            ]
        )
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_project_state_merges_valid_size_axis_frontmatter(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text(
        "---\n"
        "workflow: fix-bug\n"
        "size: M\n"
        "execution_shape: SINGLE_PHASE\n"
        "verification_status: PASS\n"
        "reasoning_attempts:\n"
        "  architecture: 0\n"
        "  phase_plan: 0\n"
        "  implementation: 1\n"
        "---\n"
    )
    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["size_axis"] == {
        "size": "M",
        "execution_shape": "SINGLE_PHASE",
        "verification_status": "PASS",
        "reasoning_attempts": {
            "architecture": 0,
            "phase_plan": 0,
            "implementation": 1,
        },
    }


def test_project_state_rejects_an_invalid_size_axis_value(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("---\nsize: HUGE\n---\n")
    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 1
    assert "size" in capsys.readouterr().err


def test_project_state_on_file_without_frontmatter_has_empty_size_axis(
    tmp_path: Path, capsys
):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo header here.\n")
    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["size_axis"] == {}


def test_checkpoint_accept_rca_then_record_evidence_and_reclassification(
    tmp_path: Path, capsys
):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    exit_code = main(
        ["checkpoint", "init", "--workflow", "fix-bug", "--file", str(path)]
    )
    assert exit_code == 0
    capsys.readouterr()

    exit_code = main(
        [
            "checkpoint",
            "accept-rca",
            "--workflow",
            "fix-bug",
            "--file",
            str(path),
            "--pointer",
            "rca.md",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["accepted_rca"] == "rca.md"

    exit_code = main(
        [
            "checkpoint",
            "record-evidence",
            "--workflow",
            "fix-bug",
            "--file",
            str(path),
            "--pointer",
            "gate=verify PASS",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["evidence"] == ["gate=verify PASS"]

    exit_code = main(
        [
            "checkpoint",
            "record-reclassification",
            "--workflow",
            "fix-bug",
            "--file",
            str(path),
            "--reason",
            "scope grew",
            "--from",
            "STANDARD",
            "--to",
            "COMPLEX",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reclassifications"] == [
        {"reason": "scope grew", "from": "STANDARD", "to": "COMPLEX"}
    ]


def test_checkpoint_accept_rca_twice_with_a_different_pointer_fails(
    tmp_path: Path, capsys
):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    main(["checkpoint", "init", "--workflow", "fix-bug", "--file", str(path)])
    capsys.readouterr()
    main(
        [
            "checkpoint",
            "accept-rca",
            "--workflow",
            "fix-bug",
            "--file",
            str(path),
            "--pointer",
            "rca.md",
        ]
    )
    capsys.readouterr()
    exit_code = main(
        [
            "checkpoint",
            "accept-rca",
            "--workflow",
            "fix-bug",
            "--file",
            str(path),
            "--pointer",
            "rca-v2.md",
        ]
    )
    assert exit_code == 1
    assert "cannot change once accepted" in capsys.readouterr().err


def test_gate_state_set_on_missing_file_fails(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    exit_code = main(
        [
            "gate-state",
            "set",
            "--file",
            str(path),
            "--gate",
            "review",
            "--state",
            "PASS",
            "--reason",
            "reason",
            "--count",
            "0",
        ]
    )
    assert exit_code == 1
    assert "gate-state artifact is missing" in capsys.readouterr().err


def test_usage_reports_json_against_an_empty_projects_root(tmp_path: Path, capsys):
    exit_code = main(["usage", "--projects-root", str(tmp_path), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "usage"
    assert payload["sessions"] == []
    assert payload["total_tokens"] == 0
    assert payload["premium_tokens"] == 0


def test_usage_reports_a_session_row_from_real_jsonl(tmp_path: Path, capsys):
    project_dir = tmp_path / "-Users-joeli-example"
    project_dir.mkdir()
    (project_dir / "session-1.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "cwd": "/Users/joeli/example",
                "sessionId": "session-1",
                "timestamp": "2026-08-01T00:00:00Z",
                "message": {
                    "model": "claude-opus-4-8",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            }
        )
        + "\n"
    )
    exit_code = main(["usage", "--projects-root", str(project_dir.parent), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["sessions"]) == 1
    session = payload["sessions"][0]
    assert session["cwd"] == "/Users/joeli/example"
    assert session["session_id"] == "session-1"
    assert session["total_tokens"] == 150
    # claude-opus-4-8 resolves to the "opus" role, which is premium.
    assert session["premium_tokens"] == 150
    assert payload["total_tokens"] == 150
    assert payload["premium_tokens"] == 150


def test_usage_prints_a_text_table_and_total_line(tmp_path: Path, capsys):
    exit_code = main(["usage", "--projects-root", str(tmp_path)])
    assert exit_code == 0
    assert "TOTAL:" in capsys.readouterr().out
