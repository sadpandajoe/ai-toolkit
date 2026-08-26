"""Gate-state block for PROJECT.md: per-gate PASS/RETRY/ESCALATE/... history.

Deliberately separate from both the `aitk-checkpoint:v1` block (crash-safe
resumable-effect state) and the `aitk-routing:v1` block (complexity
classification snapshot). Gate state is the small amount of persisted
history rules/gates.md's repeat-failure counting rule needs to survive a
context reset: the last decided state, reason, and repeat count, per gate
name. Decision logic stays in aitk.gates (`decide_failure`) — this module
only reads and writes the snapshot the caller decided.
"""

from __future__ import annotations

import json
from pathlib import Path

from .checkpoint import (
    CheckpointError,
    _atomic_text,
    _checkpoint_lock,
    _reject_unsafe_path,
    canonical_json,
)
from .gates import GATE_STATES

BEGIN = "<!-- aitk-gate:v1 -->"
END = "<!-- /aitk-gate -->"
SCHEMA_VERSION = 1


class GateStateError(ValueError):
    """The gate-state block is malformed or a requested value is invalid."""


def _locate(content: str) -> tuple[int, int, str] | None:
    if BEGIN not in content and END not in content:
        return None
    if content.count(BEGIN) != 1 or content.count(END) != 1:
        raise GateStateError(
            "gate-state document must contain exactly one marker pair"
        )
    start = content.index(BEGIN)
    end_marker = content.index(END)
    if end_marker < start:
        raise GateStateError("gate-state markers are out of order")
    body_start = start + len(BEGIN)
    between = content[body_start:end_marker]
    if not between.startswith("\n") or not between.endswith("\n"):
        raise GateStateError("gate-state JSON must occupy one line between markers")
    body = between[1:-1]
    if "\n" in body or not body:
        raise GateStateError("gate-state JSON must occupy one nonempty line")
    return start, end_marker + len(END), body


def _validate_record(gate: str, state: str, reason: str, count: int) -> dict[str, object]:
    if not isinstance(gate, str) or not gate:
        raise GateStateError("gate name must be a nonempty string")
    if state not in GATE_STATES:
        raise GateStateError("gate-state state is invalid")
    if not isinstance(reason, str) or not reason:
        raise GateStateError("gate-state reason must be a nonempty string")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise GateStateError("gate-state count must be a non-negative integer")
    return {"state": state, "reason": reason, "count": count}


def _parse_gates(body: str) -> dict[str, object]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise GateStateError(f"gate-state JSON is malformed: {error.msg}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise GateStateError("gate-state payload must be a schema_version 1 object")
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        raise GateStateError("gate-state payload must contain a gates object")
    return gates


def read(path: Path, gate: str | None = None) -> dict[str, object] | None:
    """Non-validating snapshot read: no lock, safe on a stale file.

    Returns the full `{gate_name: record}` mapping, or a single gate's record
    when `gate` is given (`None` if that gate has no recorded history), or
    `None` when the block itself is absent.
    """
    _reject_unsafe_path(path)
    if not path.is_file():
        return None
    located = _locate(path.read_text())
    if located is None:
        return None
    _, _, body = located
    gates = _parse_gates(body)
    return gates.get(gate) if gate is not None else gates


def set_state(path: Path, gate: str, state: str, reason: str, count: int) -> dict[str, object]:
    record = _validate_record(gate, state, reason, count)
    with _checkpoint_lock(path):
        _reject_unsafe_path(path)
        if not path.is_file():
            raise CheckpointError(f"gate-state artifact is missing: {path}")
        content = path.read_text()
        located = _locate(content)
        gates = _parse_gates(located[2]) if located is not None else {}
        gates[gate] = record
        block = f"{BEGIN}\n{canonical_json({'schema_version': SCHEMA_VERSION, 'gates': gates})}\n{END}"
        if located is None:
            separator = "" if not content or content.endswith("\n\n") else "\n"
            updated = content + separator + block + "\n"
        else:
            start, finish, _ = located
            updated = content[:start] + block + content[finish:]
        _atomic_text(path, updated)
    return record
