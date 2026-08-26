"""Tests for the PROJECT.md v2 state modules: checkpoint.read_snapshot() and
the routing-state block (aitk.routing)."""

from pathlib import Path

import pytest

from aitk import gate_state, routing
from aitk.checkpoint import CheckpointError, canonical_json, read_snapshot

BEGIN = "<!-- aitk-checkpoint:v1 -->"
END = "<!-- /aitk-checkpoint -->"


def _write_block(path: Path, body: str) -> None:
    path.write_text(f"# PROJECT\n\n{BEGIN}\n{body}\n{END}\n")


def _write_routing_block(path: Path, body: str) -> None:
    path.write_text(f"# PROJECT\n\n{routing.BEGIN}\n{body}\n{routing.END}\n")


def test_missing_file_returns_none(tmp_path: Path):
    assert read_snapshot(tmp_path / "PROJECT.md") is None


def test_file_without_checkpoint_markers_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo checkpoint block here.\n")
    assert read_snapshot(path) is None


def test_valid_marker_returns_dict(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    payload = {"schema_version": 1, "workflow": "fix-bug", "phase": "investigate"}
    _write_block(path, canonical_json(payload))
    assert read_snapshot(path) == payload


def test_malformed_json_raises_checkpoint_error(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    _write_block(path, "{not valid json")
    with pytest.raises(CheckpointError, match="malformed"):
        read_snapshot(path)


def test_non_object_json_raises_checkpoint_error(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    _write_block(path, "[1, 2, 3]")
    with pytest.raises(CheckpointError, match="must be an object"):
        read_snapshot(path)


def test_one_marker_without_its_pair_raises_checkpoint_error(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{BEGIN}\n{{}}\n")
    with pytest.raises(CheckpointError, match="exactly one marker pair"):
        read_snapshot(path)


def test_relative_path_raises_checkpoint_error():
    with pytest.raises(CheckpointError, match="not normalized"):
        read_snapshot(Path("PROJECT.md"))


# --- aitk.routing: routing-state block round-trip -------------------------


def test_routing_read_missing_file_returns_none(tmp_path: Path):
    assert routing.read(tmp_path / "PROJECT.md") is None


def test_routing_read_file_without_markers_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo routing block here.\n")
    assert routing.read(path) is None


def test_routing_set_then_read_round_trips(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    payload = routing.set_classification(path, "STANDARD", 8, "multi-file change")
    assert routing.read(path) == payload
    assert payload == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 8,
        "reason": "multi-file change",
    }


def test_routing_set_classification_updates_existing_block(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    routing.set_classification(path, "TRIVIAL", 9, "one-line fix")
    routing.set_classification(path, "COMPLEX", 6, "reclassified")
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "COMPLEX",
        "confidence": 6,
        "reason": "reclassified",
    }
    # exactly one marker pair survives the update
    content = path.read_text()
    assert content.count(routing.BEGIN) == 1
    assert content.count(routing.END) == 1


def test_routing_set_classification_rejects_invalid_complexity(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(routing.RoutingStateError, match="complexity is invalid"):
        routing.set_classification(path, "MODERATE", 5, "pre-rename tier name")
    assert routing.read(path) is None


def test_routing_read_normalizes_legacy_moderate_to_standard(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    legacy_payload = {
        "schema_version": 1,
        "complexity": "MODERATE",
        "confidence": 8,
        "reason": "written under the pre-rename schema",
    }
    _write_routing_block(path, canonical_json(legacy_payload))
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 8,
        "reason": "written under the pre-rename schema",
    }


def test_routing_read_normalizes_legacy_standard_to_complex(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    legacy_payload = {
        "schema_version": 1,
        "complexity": "STANDARD",
        "confidence": 6,
        "reason": "written under the pre-rename schema",
    }
    _write_routing_block(path, canonical_json(legacy_payload))
    assert routing.read(path)["complexity"] == "COMPLEX"
    assert routing.read(path)["schema_version"] == 2


def test_routing_read_does_not_remap_current_schema_standard(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    routing.set_classification(path, "STANDARD", 8, "current schema, not legacy")
    assert routing.read(path)["complexity"] == "STANDARD"


def test_routing_set_classification_rejects_out_of_range_confidence(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(routing.RoutingStateError, match="confidence must be"):
        routing.set_classification(path, "TRIVIAL", 11, "reason")


def test_routing_set_classification_rejects_empty_reason(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(routing.RoutingStateError, match="reason must be"):
        routing.set_classification(path, "TRIVIAL", 5, "")


def test_routing_set_classification_requires_existing_file(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    with pytest.raises(CheckpointError, match="routing-state artifact is missing"):
        routing.set_classification(path, "TRIVIAL", 5, "reason")


def test_routing_read_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{routing.BEGIN}\n{{not valid json\n{routing.END}\n")
    with pytest.raises(routing.RoutingStateError, match="malformed"):
        routing.read(path)


def test_routing_one_marker_without_its_pair_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{routing.BEGIN}\n{{}}\n")
    with pytest.raises(routing.RoutingStateError, match="exactly one marker pair"):
        routing.read(path)


# --- aitk.gate_state: gate-state block round-trip --------------------------


def test_gate_state_read_missing_file_returns_none(tmp_path: Path):
    assert gate_state.read(tmp_path / "PROJECT.md") is None


def test_gate_state_read_file_without_markers_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo gate block here.\n")
    assert gate_state.read(path) is None


def test_gate_state_set_then_read_round_trips(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    record = gate_state.set_state(path, "review", "RETRY", "missing tests", 1)
    assert record == {"state": "RETRY", "reason": "missing tests", "count": 1}
    assert gate_state.read(path, "review") == record
    assert gate_state.read(path) == {"review": record}


def test_gate_state_set_preserves_other_gates(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)
    gate_state.set_state(path, "rca", "PASS", "root cause confirmed", 0)
    assert gate_state.read(path) == {
        "review": {"state": "RETRY", "reason": "missing tests", "count": 1},
        "rca": {"state": "PASS", "reason": "root cause confirmed", "count": 0},
    }
    content = path.read_text()
    assert content.count(gate_state.BEGIN) == 1
    assert content.count(gate_state.END) == 1


def test_gate_state_set_updates_existing_gate(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)
    gate_state.set_state(path, "review", "ESCALATE", "missing tests", 2)
    assert gate_state.read(path, "review") == {
        "state": "ESCALATE",
        "reason": "missing tests",
        "count": 2,
    }


def test_gate_state_read_unknown_gate_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(path, "review", "PASS", "clean", 0)
    assert gate_state.read(path, "rca") is None


def test_gate_state_set_classification_rejects_invalid_state(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(gate_state.GateStateError, match="state is invalid"):
        gate_state.set_state(path, "review", "NOT_A_STATE", "reason", 0)


def test_gate_state_set_rejects_negative_count(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(gate_state.GateStateError, match="count must be"):
        gate_state.set_state(path, "review", "RETRY", "reason", -1)


def test_gate_state_set_requires_existing_file(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    with pytest.raises(CheckpointError, match="gate-state artifact is missing"):
        gate_state.set_state(path, "review", "PASS", "reason", 0)


def test_gate_state_read_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(
        f"# PROJECT\n\n{gate_state.BEGIN}\n{{not valid json\n{gate_state.END}\n"
    )
    with pytest.raises(gate_state.GateStateError, match="malformed"):
        gate_state.read(path)


def test_gate_state_one_marker_without_its_pair_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{gate_state.BEGIN}\n{{}}\n")
    with pytest.raises(gate_state.GateStateError, match="exactly one marker pair"):
        gate_state.read(path)
