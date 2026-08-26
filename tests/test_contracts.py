"""PROJECT.md v2 schema round-trip: proves the three independent state
modules (checkpoint, routing, gate_state) coexist in one file without one's
marker block corrupting another's, and that `aitk project-state` surfaces
all three together."""

import json
from pathlib import Path

from aitk import gate_state, routing
from aitk.checkpoint import canonical_json, read_snapshot
from aitk.cli import main

CHECKPOINT_BEGIN = "<!-- aitk-checkpoint:v1 -->"
CHECKPOINT_END = "<!-- /aitk-checkpoint -->"


def _write_checkpoint_block(path: Path, payload: dict[str, object]) -> None:
    existing = path.read_text() if path.is_file() else ""
    block = f"{CHECKPOINT_BEGIN}\n{canonical_json(payload)}\n{CHECKPOINT_END}"
    separator = "" if not existing or existing.endswith("\n\n") else "\n"
    path.write_text(existing + separator + block + "\n")


def test_three_state_blocks_coexist_and_round_trip_independently(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    checkpoint_payload = {
        "schema_version": 1,
        "workflow": "fix-bug",
        "phase": "implement",
    }
    _write_checkpoint_block(path, checkpoint_payload)
    routing.set_classification(path, "STANDARD", 7, "touches three modules")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)

    # Each block round-trips through its own module, undisturbed by the others.
    assert read_snapshot(path) == checkpoint_payload
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 7,
        "reason": "touches three modules",
    }
    assert gate_state.read(path) == {
        "review": {"state": "RETRY", "reason": "missing tests", "count": 1}
    }

    content = path.read_text()
    for begin, end in (
        (CHECKPOINT_BEGIN, CHECKPOINT_END),
        (routing.BEGIN, routing.END),
        (gate_state.BEGIN, gate_state.END),
    ):
        assert content.count(begin) == 1
        assert content.count(end) == 1


def test_updating_one_block_leaves_the_others_untouched(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    checkpoint_payload = {"schema_version": 1, "workflow": "fix-bug", "phase": "plan"}
    _write_checkpoint_block(path, checkpoint_payload)
    routing.set_classification(path, "TRIVIAL", 9, "one-line fix")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)

    # Mutate routing and gate state again; the checkpoint block, written first
    # and never touched by either module, must survive unchanged.
    routing.set_classification(path, "COMPLEX", 6, "reclassified after review")
    gate_state.set_state(path, "review", "ESCALATE", "missing tests", 2)
    gate_state.set_state(path, "rca", "PASS", "root cause confirmed", 0)

    assert read_snapshot(path) == checkpoint_payload
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "COMPLEX",
        "confidence": 6,
        "reason": "reclassified after review",
    }
    assert gate_state.read(path) == {
        "review": {"state": "ESCALATE", "reason": "missing tests", "count": 2},
        "rca": {"state": "PASS", "reason": "root cause confirmed", "count": 0},
    }


def test_project_state_cli_surfaces_all_three_blocks_together(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    checkpoint_payload = {
        "schema_version": 1,
        "workflow": "create-feature",
        "phase": "verify",
    }
    _write_checkpoint_block(path, checkpoint_payload)
    routing.set_classification(path, "COMPLEX", 8, "multi-phase build")
    gate_state.set_state(path, "verify", "PASS", "suite green", 0)

    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["file"] == str(path)
    assert payload["checkpoint"] == checkpoint_payload
    assert payload["routing"] == {
        "schema_version": 2,
        "complexity": "COMPLEX",
        "confidence": 8,
        "reason": "multi-phase build",
    }
    assert payload["gates"] == {
        "verify": {"state": "PASS", "reason": "suite green", "count": 0}
    }
