"""Tests for aitk.checkpoint.read_snapshot() — the non-validating v2 read."""

from pathlib import Path

import pytest

from aitk.checkpoint import CheckpointError, canonical_json, read_snapshot

BEGIN = "<!-- aitk-checkpoint:v1 -->"
END = "<!-- /aitk-checkpoint -->"


def _write_block(path: Path, body: str) -> None:
    path.write_text(f"# PROJECT\n\n{BEGIN}\n{body}\n{END}\n")


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
