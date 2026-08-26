"""Routing-state block for PROJECT.md: complexity-gate classification snapshot.

Deliberately separate from the `aitk-checkpoint:v1` block in checkpoint.py.
That block is a crash-safe effect-idempotency state machine for durable
workflow resumption (contract digest, generation counter, transition
validation). Routing state carries no resumable effects and no per-workflow
contract binding, so it gets its own marker pair and a plain writer instead
of forcing classification updates through transition validation designed for
a different purpose.
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

BEGIN = "<!-- aitk-routing:v1 -->"
END = "<!-- /aitk-routing -->"
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
ROUTING_KEYS = {"schema_version", "complexity", "confidence", "reason"}
COMPLEXITY_VALUES = {"TRIVIAL", "STANDARD", "COMPLEX"}
# The pre-rename vocabulary's "STANDARD" and the current vocabulary's
# "STANDARD" are the same string with different meanings, so the legacy
# value alone can't disambiguate a read. Gate the remap on schema_version
# instead: only a document literally written under schema version 1 gets
# its complexity value remapped through this table.
_LEGACY_COMPLEXITY_MAP = {"TRIVIAL": "TRIVIAL", "MODERATE": "STANDARD", "STANDARD": "COMPLEX"}


class RoutingStateError(ValueError):
    """The routing-state block is malformed or a requested value is invalid."""


def _locate(content: str) -> tuple[int, int, str] | None:
    if BEGIN not in content and END not in content:
        return None
    if content.count(BEGIN) != 1 or content.count(END) != 1:
        raise RoutingStateError(
            "routing-state document must contain exactly one marker pair"
        )
    start = content.index(BEGIN)
    end_marker = content.index(END)
    if end_marker < start:
        raise RoutingStateError("routing-state markers are out of order")
    body_start = start + len(BEGIN)
    between = content[body_start:end_marker]
    if not between.startswith("\n") or not between.endswith("\n"):
        raise RoutingStateError(
            "routing-state JSON must occupy one line between markers"
        )
    body = between[1:-1]
    if "\n" in body or not body:
        raise RoutingStateError("routing-state JSON must occupy one nonempty line")
    return start, end_marker + len(END), body


def _validate_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != ROUTING_KEYS:
        raise RoutingStateError(f"routing-state fields do not match schema version {SCHEMA_VERSION}")
    if (
        not isinstance(payload["schema_version"], int)
        or isinstance(payload["schema_version"], bool)
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        raise RoutingStateError("routing-state schema version is stale")
    complexity = payload["complexity"]
    if complexity not in COMPLEXITY_VALUES:
        raise RoutingStateError("routing-state complexity is invalid")
    confidence = payload["confidence"]
    if (
        not isinstance(confidence, int)
        or isinstance(confidence, bool)
        or not 1 <= confidence <= 10
    ):
        raise RoutingStateError("routing-state confidence must be an integer 1-10")
    if not isinstance(payload["reason"], str) or not payload["reason"]:
        raise RoutingStateError("routing-state reason must be a nonempty string")
    return payload


def read(path: Path) -> dict[str, object] | None:
    """Non-validating snapshot read: no contract, no lock, safe on a stale file."""
    _reject_unsafe_path(path)
    if not path.is_file():
        return None
    located = _locate(path.read_text())
    if located is None:
        return None
    _, _, body = located
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise RoutingStateError(
            f"routing-state JSON is malformed: {error.msg}"
        ) from error
    if not isinstance(payload, dict):
        raise RoutingStateError("routing-state payload must be an object")
    return _normalize_legacy(payload)


def _normalize_legacy(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("schema_version") != LEGACY_SCHEMA_VERSION:
        return payload
    mapped = _LEGACY_COMPLEXITY_MAP.get(payload.get("complexity"))
    if mapped is None:
        return payload
    return {**payload, "schema_version": SCHEMA_VERSION, "complexity": mapped}


def set_classification(
    path: Path,
    complexity: str,
    confidence: int,
    reason: str,
) -> dict[str, object]:
    payload = _validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "complexity": complexity,
            "confidence": confidence,
            "reason": reason,
        }
    )
    block = f"{BEGIN}\n{canonical_json(payload)}\n{END}"
    with _checkpoint_lock(path):
        _reject_unsafe_path(path)
        if not path.is_file():
            raise CheckpointError(f"routing-state artifact is missing: {path}")
        content = path.read_text()
        located = _locate(content)
        if located is None:
            separator = "" if not content or content.endswith("\n\n") else "\n"
            updated = content + separator + block + "\n"
        else:
            start, finish, _ = located
            updated = content[:start] + block + content[finish:]
        _atomic_text(path, updated)
    return payload
