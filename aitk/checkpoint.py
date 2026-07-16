"""Deterministic durable-workflow checkpoint parsing and transitions."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable

from .conformance import contract_digest, contracts_by_name
from .workflows import load_workflows


BEGIN = "<!-- aitk-checkpoint:v1 -->"
END = "<!-- /aitk-checkpoint -->"
SCHEMA_VERSION = 1
CONTRACT_SCHEMA_VERSION = 2
CHECKPOINT_KEYS = {
    "schema_version",
    "workflow",
    "contract_schema_version",
    "contract_digest",
    "phase",
    "generation",
    "effects",
}
EFFECT_KEYS = {"key", "operation_id", "status", "result_digest"}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class CheckpointError(ValueError):
    """A checkpoint is malformed, stale, or requests an illegal transition."""


@dataclass(frozen=True)
class CheckpointResult:
    workflow: str
    phase: str
    generation: int
    effects: tuple[dict[str, object], ...]
    file: str
    changed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "phase": self.phase,
            "generation": self.generation,
            "effects": [dict(item) for item in self.effects],
            "file": self.file,
        }


@contextmanager
def _checkpoint_lock(path: Path):
    lock_root = Path(tempfile.gettempdir()) / (
        f"ai-toolkit-checkpoint-locks-{os.getuid()}"
    )
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = lock_root.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or lock_root.is_symlink()
    ):
        raise CheckpointError("checkpoint lock directory is unsafe")
    os.chmod(lock_root, 0o700)
    identity = hashlib.sha256(str(path).encode()).hexdigest()
    lock_path = lock_root / f"{identity}.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        lock_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.getuid()
            or lock_metadata.st_nlink != 1
        ):
            raise CheckpointError("checkpoint lock file is unsafe")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _serialized_checkpoint(function):
    @wraps(function)
    def wrapped(root: Path, workflow: str, path: Path, *args, **kwargs):
        _reject_unsafe_path(path)
        with _checkpoint_lock(path):
            return function(root, workflow, path, *args, **kwargs)

    return wrapped


def canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_text(path: Path, content: str) -> None:
    _reject_unsafe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.is_file() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _reject_unsafe_path(path: Path) -> None:
    if not path.is_absolute() or Path(os.path.normpath(str(path))) != path:
        raise CheckpointError(f"checkpoint artifact path is not normalized: {path}")
    for candidate in (path, *path.parents[:-1]):
        if candidate.is_symlink():
            raise CheckpointError(
                f"checkpoint artifact path contains a symlink: {candidate}"
            )


def _contract(
    root: Path,
    workflow: str,
    include_pgm: bool,
) -> dict[str, object]:
    known = {item.name: item for item in load_workflows(root, include_pgm=include_pgm)}
    if workflow not in known:
        raise CheckpointError(f"unknown or inactive workflow: {workflow}")
    contract = contracts_by_name(root).get(workflow)
    if contract is None:
        raise CheckpointError(f"workflow contract is missing: {workflow}")
    if known[workflow].execution_class != "durable" or not contract["resumable"]:
        raise CheckpointError(f"workflow is not resumable: {workflow}")
    return contract


def _machine_block(payload: dict[str, object]) -> str:
    return f"{BEGIN}\n{canonical_json(payload)}\n{END}"


def _locate(content: str) -> tuple[int, int, str]:
    if content.count(BEGIN) != 1 or content.count(END) != 1:
        raise CheckpointError(
            "checkpoint document must contain exactly one marker pair"
        )
    start = content.index(BEGIN)
    end_marker = content.index(END)
    if end_marker < start:
        raise CheckpointError("checkpoint markers are out of order")
    body_start = start + len(BEGIN)
    between = content[body_start:end_marker]
    if not between.startswith("\n") or not between.endswith("\n"):
        raise CheckpointError("checkpoint JSON must occupy one line between markers")
    body = between[1:-1]
    if "\n" in body or not body:
        raise CheckpointError("checkpoint JSON must occupy one nonempty line")
    return start, end_marker + len(END), body


def _validate_payload(
    payload: object,
    workflow: str,
    contract: dict[str, object],
    *,
    require_canonical: str | None = None,
) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != CHECKPOINT_KEYS:
        raise CheckpointError("checkpoint fields do not match schema version 1")
    if (
        not isinstance(payload["schema_version"], int)
        or isinstance(payload["schema_version"], bool)
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        raise CheckpointError("checkpoint schema version is stale")
    if (
        not isinstance(payload["contract_schema_version"], int)
        or isinstance(payload["contract_schema_version"], bool)
        or payload["contract_schema_version"] != CONTRACT_SCHEMA_VERSION
    ):
        raise CheckpointError("checkpoint contract schema version is stale")
    if payload["workflow"] != workflow or workflow != contract.get("name"):
        raise CheckpointError(
            "checkpoint workflow does not match the requested workflow"
        )
    expected_digest = contract_digest(contract)
    if payload["contract_digest"] != expected_digest:
        raise CheckpointError("checkpoint contract digest is stale")
    phase = payload["phase"]
    if not isinstance(phase, str) or phase not in contract["resume_from"]:
        raise CheckpointError("checkpoint phase is not resumable under the contract")
    generation = payload["generation"]
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 0
    ):
        raise CheckpointError("checkpoint generation must be a non-negative integer")
    effects = payload["effects"]
    if not isinstance(effects, list):
        raise CheckpointError("checkpoint effects must be a list")
    declared = {item["key"]: item["strategy"] for item in contract["idempotency_keys"]}
    seen_effects: set[tuple[str, str]] = set()
    seen_operations: set[str] = set()
    for effect in effects:
        if not isinstance(effect, dict) or set(effect) != EFFECT_KEYS:
            raise CheckpointError("checkpoint effect fields are invalid")
        key = effect["key"]
        operation_id = effect["operation_id"]
        status_value = effect["status"]
        result_digest = effect["result_digest"]
        if not isinstance(key, str) or key not in declared:
            raise CheckpointError("checkpoint contains an unknown effect key")
        if (
            not isinstance(operation_id, str)
            or TOKEN.fullmatch(operation_id) is None
            or operation_id in seen_operations
        ):
            raise CheckpointError(
                "checkpoint contains an invalid or duplicate operation ID"
            )
        if not isinstance(status_value, str) or status_value not in {
            "pending",
            "applied",
        }:
            raise CheckpointError("checkpoint effect status is invalid")
        if status_value == "pending" and result_digest is not None:
            raise CheckpointError(
                "pending checkpoint effects cannot have a result digest"
            )
        if status_value == "applied" and (
            not isinstance(result_digest, str)
            or DIGEST.fullmatch(result_digest) is None
        ):
            raise CheckpointError("applied checkpoint effects require a SHA-256 digest")
        identity = (key, operation_id)
        if identity in seen_effects:
            raise CheckpointError("checkpoint contains a duplicate effect record")
        seen_effects.add(identity)
        seen_operations.add(operation_id)
    if require_canonical is not None and canonical_json(payload) != require_canonical:
        raise CheckpointError("checkpoint JSON is not canonical")
    return payload


def parse_checkpoint(
    content: str,
    workflow: str,
    contract: dict[str, object],
) -> dict[str, object]:
    _, _, body = _locate(content)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise CheckpointError(f"checkpoint JSON is malformed: {error.msg}") from error
    return _validate_payload(payload, workflow, contract, require_canonical=body)


def _replace_block(content: str, payload: dict[str, object]) -> str:
    start, finish, _ = _locate(content)
    return content[:start] + _machine_block(payload) + content[finish:]


def _result(path: Path, payload: dict[str, object], changed: bool) -> CheckpointResult:
    return CheckpointResult(
        workflow=str(payload["workflow"]),
        phase=str(payload["phase"]),
        generation=int(payload["generation"]),
        effects=tuple(dict(item) for item in payload["effects"]),
        file=str(path),
        changed=changed,
    )


def _read(
    root: Path,
    workflow: str,
    path: Path,
    include_pgm: bool,
) -> tuple[dict[str, object], dict[str, object], str]:
    contract = _contract(root, workflow, include_pgm)
    _reject_unsafe_path(path)
    if not path.is_file():
        raise CheckpointError(f"checkpoint artifact is missing or unsafe: {path}")
    content = path.read_text()
    return contract, parse_checkpoint(content, workflow, contract), content


def checkpoint_file(
    root: Path,
    workflow: str,
    selected: Path | None,
    include_pgm: bool,
) -> Path:
    contract = _contract(root, workflow, include_pgm)
    if selected is not None:
        expanded = selected.expanduser()
        return expanded if expanded.is_absolute() else Path.cwd() / expanded
    checkpoint = contract["checkpoint"]
    assert isinstance(checkpoint, dict)
    return Path.cwd() / str(checkpoint["artifact"])


@_serialized_checkpoint
def initialize(
    root: Path,
    workflow: str,
    path: Path,
    include_pgm: bool = False,
    replace_existing: bool = False,
) -> CheckpointResult:
    contract = _contract(root, workflow, include_pgm)
    _reject_unsafe_path(path)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "workflow": workflow,
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_digest": contract_digest(contract),
        "phase": contract["phases"][0],
        "generation": 0,
        "effects": [],
    }
    checkpoint = contract["checkpoint"]
    assert isinstance(checkpoint, dict)
    template = (root / str(checkpoint["template"])).read_text()
    rendered = (
        template.replace("{{workflow}}", workflow)
        .replace("{{contract_digest}}", str(payload["contract_digest"]))
        .replace("{{phase}}", str(payload["phase"]))
    )
    parse_checkpoint(rendered, workflow, contract)
    if path.exists():
        if not path.is_file():
            raise CheckpointError(f"checkpoint artifact is unsafe: {path}")
        existing = path.read_text()
        if BEGIN in existing or END in existing:
            _, _, existing_body = _locate(existing)
            try:
                existing_payload = json.loads(existing_body)
            except json.JSONDecodeError as error:
                raise CheckpointError(
                    f"existing checkpoint JSON is malformed: {error.msg}"
                ) from error
            if not isinstance(existing_payload, dict):
                raise CheckpointError("existing checkpoint payload must be an object")
            existing_workflow = existing_payload.get("workflow")
            if existing_workflow != workflow and not replace_existing:
                raise CheckpointError(
                    "another durable workflow already owns this checkpoint artifact"
                )
            if existing_workflow == workflow and not replace_existing:
                current = parse_checkpoint(existing, workflow, contract)
                return _result(path, current, False)
            effects = existing_payload.get("effects")
            if not isinstance(effects, list) or any(
                not isinstance(item, dict)
                or item.get("status") not in {"pending", "applied"}
                for item in effects
            ):
                raise CheckpointError(
                    "existing checkpoint effects must be structurally valid before replacement"
                )
            if any(item.get("status") == "pending" for item in effects):
                raise CheckpointError(
                    "cannot replace a checkpoint with pending effects"
                )
            content = _replace_block(existing, payload)
        else:
            separator = "" if not existing or existing.endswith("\n\n") else "\n"
            content = existing + separator + rendered
    else:
        content = rendered
    _atomic_text(path, content)
    return _result(path, payload, True)


@_serialized_checkpoint
def validate(
    root: Path,
    workflow: str,
    path: Path,
    include_pgm: bool = False,
) -> CheckpointResult:
    _, payload, _ = _read(root, workflow, path, include_pgm)
    return _result(path, payload, False)


def _write_transition(
    path: Path,
    content: str,
    before: dict[str, object],
    after: dict[str, object],
    contract: dict[str, object],
) -> CheckpointResult:
    validate_transition(before, after, contract)
    _atomic_text(path, _replace_block(content, after))
    return _result(path, after, True)


@_serialized_checkpoint
def advance(
    root: Path,
    workflow: str,
    path: Path,
    target_phase: str,
    include_pgm: bool = False,
) -> CheckpointResult:
    contract, before, content = _read(root, workflow, path, include_pgm)
    if target_phase not in contract["resume_from"]:
        raise CheckpointError(f"target phase is not resumable: {target_phase}")
    edges = {(item["from"], item["to"]) for item in contract["transitions"]}
    if (before["phase"], target_phase) not in edges:
        raise CheckpointError(
            f"illegal checkpoint transition: {before['phase']} -> {target_phase}"
        )
    after = dict(before)
    after["phase"] = target_phase
    after["generation"] = int(before["generation"]) + 1
    return _write_transition(path, content, before, after, contract)


@_serialized_checkpoint
def reserve(
    root: Path,
    workflow: str,
    path: Path,
    key: str,
    operation_id: str,
    include_pgm: bool = False,
) -> CheckpointResult:
    contract, before, content = _read(root, workflow, path, include_pgm)
    declared = {item["key"] for item in contract["idempotency_keys"]}
    if key not in declared:
        raise CheckpointError(f"effect key is not declared by the contract: {key}")
    if TOKEN.fullmatch(operation_id) is None:
        raise CheckpointError("operation ID is not a portable token")
    effects = [dict(item) for item in before["effects"]]
    current = next(
        (
            item
            for item in effects
            if item["key"] == key and item["operation_id"] == operation_id
        ),
        None,
    )
    if current is not None:
        return _result(path, before, False)
    if any(item["operation_id"] == operation_id for item in effects):
        raise CheckpointError("operation ID is already bound to another effect key")
    effects.append(
        {
            "key": key,
            "operation_id": operation_id,
            "status": "pending",
            "result_digest": None,
        }
    )
    after = dict(before)
    after["effects"] = effects
    after["generation"] = int(before["generation"]) + 1
    return _write_transition(path, content, before, after, contract)


@_serialized_checkpoint
def apply(
    root: Path,
    workflow: str,
    path: Path,
    key: str,
    operation_id: str,
    result_digest: str,
    include_pgm: bool = False,
) -> CheckpointResult:
    contract, before, content = _read(root, workflow, path, include_pgm)
    if DIGEST.fullmatch(result_digest) is None:
        raise CheckpointError("result digest must be lowercase sha256:<64 hex>")
    effects = [dict(item) for item in before["effects"]]
    current = next(
        (
            item
            for item in effects
            if item["key"] == key and item["operation_id"] == operation_id
        ),
        None,
    )
    if current is None:
        raise CheckpointError("effect must be reserved before it can be applied")
    if current["status"] == "applied":
        if current["result_digest"] == result_digest:
            return _result(path, before, False)
        raise CheckpointError("applied effect result cannot be changed")
    current["status"] = "applied"
    current["result_digest"] = result_digest
    after = dict(before)
    after["effects"] = effects
    after["generation"] = int(before["generation"]) + 1
    return _write_transition(path, content, before, after, contract)


def effect_strategy(contract: dict[str, object], key: str) -> str:
    for item in contract["idempotency_keys"]:
        if item["key"] == key:
            return str(item["strategy"])
    raise CheckpointError(f"effect key is not declared by the contract: {key}")


def validate_transition(
    before: dict[str, object],
    after: dict[str, object],
    contract: dict[str, object],
) -> None:
    workflow = str(before.get("workflow", ""))
    _validate_payload(before, workflow, contract)
    _validate_payload(after, workflow, contract)
    if int(after["generation"]) != int(before["generation"]) + 1:
        raise CheckpointError("checkpoint generation must increase by exactly one")
    immutable = {
        "schema_version",
        "workflow",
        "contract_schema_version",
        "contract_digest",
    }
    if any(before[key] != after[key] for key in immutable):
        raise CheckpointError("checkpoint identity fields cannot change")
    phase_changed = before["phase"] != after["phase"]
    before_effects = {
        (item["key"], item["operation_id"]): item for item in before["effects"]
    }
    after_effects = {
        (item["key"], item["operation_id"]): item for item in after["effects"]
    }
    if not set(before_effects).issubset(after_effects):
        raise CheckpointError("checkpoint effects cannot be removed")
    effect_changes = 0
    for key, old in before_effects.items():
        new = after_effects[key]
        if old == new:
            continue
        if not (
            old["status"] == "pending"
            and old["result_digest"] is None
            and new["status"] == "applied"
            and new["operation_id"] == old["operation_id"]
            and isinstance(new["result_digest"], str)
        ):
            raise CheckpointError(
                "checkpoint effect records are immutable except pending-to-applied"
            )
        effect_changes += 1
    additions = len(set(after_effects) - set(before_effects))
    if additions > 1 or effect_changes > 1:
        raise CheckpointError("a checkpoint write may change only one effect record")
    if phase_changed:
        edges = {(item["from"], item["to"]) for item in contract["transitions"]}
        if (before["phase"], after["phase"]) not in edges:
            raise CheckpointError("checkpoint phase transition is not declared")
    if sum((phase_changed, additions == 1, effect_changes == 1)) != 1:
        raise CheckpointError(
            "a checkpoint write must contain exactly one state transition"
        )


def reconcile_pending(
    contract: dict[str, object],
    effect: dict[str, object],
    lookup: Callable[[str], str | None],
) -> tuple[str, str | None]:
    if effect["status"] != "pending":
        return "already-applied", str(effect["result_digest"])
    strategy = effect_strategy(contract, str(effect["key"]))
    if strategy == "manual_stop":
        return "stop-for-user", None
    observed = lookup(str(effect["operation_id"]))
    if observed is not None:
        if DIGEST.fullmatch(observed) is None:
            raise CheckpointError("reconciled result is not a SHA-256 digest")
        return "apply-observed", observed
    if strategy == "provider_idempotency":
        return "retry-same-operation-id", None
    return "inspect-artifact", None
