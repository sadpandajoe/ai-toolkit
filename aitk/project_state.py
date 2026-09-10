"""PROJECT.md v2 routing snapshot: deterministic classification and gate state.

The snapshot is the small machine block a goal workflow reads on every loop
iteration instead of re-deriving routing from chat history or the full
PROJECT.md. It records what was decided (complexity, size, execution shape),
where the workflow is (phase, gate, gate status), and how many reasoning
attempts each unit has consumed, so RETRY/ESCALATE budgets are enforced from
durable data rather than from memory.

Two classification axes are orthogonal on purpose:

- ``complexity`` answers "how hard or risky is the reasoning?" and chooses the
  reasoning tier (Sonnet alone, or the routed specialists: the Fable
  planner, Opus or Sol judgment, Astra or Fable on the deep routes).
- ``size`` answers "how much implementation surface is there?" and, together
  with a phaseability judgement, derives ``execution_shape``.

``derive_execution_shape`` is the deterministic part of that derivation; the
phaseability judgement itself is model work recorded in ``phaseability``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .artifact_lock import artifact_lock


BEGIN = "<!-- aitk-project-state:v2 -->"
END = "<!-- /aitk-project-state -->"
SCHEMA_VERSION = 2

COMPLEXITIES = ("TRIVIAL", "STANDARD", "COMPLEX")
LEGACY_COMPLEXITY = {"MODERATE": "STANDARD"}
SIZES = ("S", "M", "L", "XL")
EXECUTION_SHAPES = ("SINGLE_PHASE", "BATCHED", "MULTI_PHASE")
PHASEABILITY = ("none", "repetitive", "phased", "unassessed")
GATE_STATUSES = (
    "PASS",
    "RETRY",
    "ESCALATE",
    "RECLASSIFY",
    "USER_DECISION",
    "BLOCKED",
    "PENDING",
)
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")
# Each reasoning unit gets an initial attempt plus one informed retry. The
# third attempt on the same unit is never a quiet re-run; it is an escalation.
ATTEMPT_BUDGET = 2
# An escalation hands the unit to a stronger owner (more effort, a different
# model, xhigh last) and gives that owner a fresh attempt budget. The ladder is
# bounded: after this many escalations the runtime answers USER_DECISION, so a
# unit can never climb indefinitely on automation alone.
MAX_ESCALATIONS = 3
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}")
SNAPSHOT_KEYS = {
    "schema_version",
    "workflow",
    "complexity",
    "classification_confidence",
    "size",
    "execution_shape",
    "phaseability",
    "phaseability_reason",
    "modifiers",
    "current_phase",
    "current_gate",
    "gate_status",
    "attempts",
    "escalations",
    "gates",
    "phases",
}
# Snapshots written before the escalation ladder and the per-gate record
# existed lack these keys; they read as empty instead of failing validation.
# ``gates`` maps a gate name to ``{"status", "phase", "units"}``: the aggregate
# outcome, the phase it was recorded in, and the latest outcome per reasoning
# unit. The checkpoint runtime reads it before reserving an effect the contract
# gates on verification or review, which is what makes "two records, one
# truth" a machine invariant. A record is scoped to its phase: ``advance``
# clears the phase-scoped gates, and a record from another phase never
# satisfies a reservation.
OPTIONAL_SNAPSHOT_KEYS = {"escalations": dict, "gates": dict}
# Gates whose outcome belongs to the phase that recorded it. A per-unit review
# PASS on slice one must not satisfy the integrated review the next phase runs.
PHASE_SCOPED_GATES = ("verification", "review")
PHASE_KEYS = {"name", "complexity", "size", "status"}
# `tree` is the commit or tree SHA the phase ended on. It is the next phase's
# review base, so it is recorded as data, never remembered.
OPTIONAL_PHASE_KEYS = {"tree"}
TREE_SHA = re.compile(r"[0-9a-fA-F]{7,64}")
PHASE_STATUSES = ("pending", "active", "done", "blocked")
# Hard complexity signals. Any one of them forces COMPLEX regardless of size,
# because the risk lives in the reasoning, not in the diff surface.
HARD_COMPLEX_MODIFIERS = (
    "schema-migration",
    "auth-security-permissions",
    "public-contract",
    "async-concurrency",
    "caching",
    "cross-service",
    "backwards-compatibility",
    "new-architecture",
)


class ProjectStateError(ValueError):
    """The snapshot is malformed or a requested change is illegal."""


@dataclass(frozen=True)
class ProjectStateResult:
    snapshot: dict[str, object]
    file: str
    changed: bool

    def as_dict(self) -> dict[str, object]:
        return {"snapshot": dict(self.snapshot), "file": self.file}


def normalize_complexity(value: object) -> str:
    """Accept v2 and legacy complexity names; return the v2 name.

    v1 MODERATE was "real contained work", which is v2 STANDARD, so it reads as
    STANDARD. A bare "STANDARD" is ambiguous between v1 (durable planning and
    review waves, now COMPLEX) and v2, so it is accepted as v2 STANDARD; the
    `start` workflow re-runs classification on resume when the checkpoint
    predates the snapshot.
    """
    if not isinstance(value, str):
        raise ProjectStateError(f"complexity must be a string, got {value!r}")
    upper = value.strip().upper()
    if upper in COMPLEXITIES:
        return upper
    if upper in LEGACY_COMPLEXITY:
        return LEGACY_COMPLEXITY[upper]
    raise ProjectStateError(f"unknown complexity: {value}")


def derive_execution_shape(size: str, phaseability: str) -> str:
    """Derive the planning shape from size and the phaseability judgement.

    Size says how much surface there is; phaseability says whether finishing
    one unit changes how the next should be planned (``phased``), whether the
    work is the same mechanical operation repeated (``repetitive``), or neither
    (``none``). ``unassessed`` is only legal below L: S and M default to one
    phase without a check, while L and XL must be assessed.
    """
    if size not in SIZES:
        raise ProjectStateError(f"unknown size: {size}")
    if phaseability not in PHASEABILITY:
        raise ProjectStateError(f"unknown phaseability: {phaseability}")
    if size in {"S", "M"}:
        return "MULTI_PHASE" if phaseability == "phased" else "SINGLE_PHASE"
    if phaseability == "unassessed":
        raise ProjectStateError(f"size {size} requires a phaseability check")
    if phaseability == "repetitive":
        return "BATCHED"
    if phaseability == "phased":
        return "MULTI_PHASE"
    # L with no independently verifiable units stays one phase; XL without
    # them is a coordination risk and decomposes by default.
    return "SINGLE_PHASE" if size == "L" else "MULTI_PHASE"


def classify_complexity(proposed: str, modifiers: list[str]) -> str:
    """Apply hard overrides: a hard modifier lifts any classification to COMPLEX."""
    normalized = normalize_complexity(proposed)
    if any(item in HARD_COMPLEX_MODIFIERS for item in modifiers):
        return "COMPLEX"
    return normalized


def next_gate_status(attempts: int, same_failure: bool) -> str:
    """Decide RETRY versus ESCALATE after a failed gate on one reasoning unit.

    ``attempts`` is the count *including* the attempt that just failed.
    Fail once for a reason -> RETRY; fail twice for the same reason, or exhaust
    the budget -> ESCALATE. A different failure reason on the second attempt is
    still within budget and may retry.
    """
    if attempts <= 0:
        raise ProjectStateError("attempts must be positive after a failure")
    if attempts >= ATTEMPT_BUDGET or (attempts > 1 and same_failure):
        return "ESCALATE"
    return "RETRY"


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _valid_gate_record(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"status", "phase", "units"}:
        return False
    if value["status"] not in GATE_STATUSES or value["status"] == "PENDING":
        return False
    if TOKEN.fullmatch(str(value["phase"])) is None:
        return False
    units = value["units"]
    return isinstance(units, dict) and all(
        TOKEN.fullmatch(str(unit)) is not None and status in GATE_STATUSES and status != "PENDING"
        for unit, status in units.items()
    )


def gate_blockers(snapshot: dict[str, object], gates: list[str] | tuple[str, ...]) -> list[str]:
    """Name what stops each gate from counting as PASS for the current phase.

    Empty means every named gate is PASS: recorded in the current phase, with
    no reasoning unit left at a non-PASS outcome. The checkpoint runtime turns
    the list into its refusal message.
    """
    phase = snapshot["current_phase"]
    recorded = snapshot["gates"]
    blockers: list[str] = []
    for gate in gates:
        entry = recorded.get(gate)
        if entry is None:
            blockers.append(f"{gate}=unrecorded")
        elif entry["phase"] != phase:
            blockers.append(f"{gate}={entry['status']} recorded in phase {entry['phase']}, not {phase}")
        elif entry["status"] != "PASS":
            units = [unit for unit, status in entry["units"].items() if status != "PASS"]
            where = f" (unit {', '.join(sorted(units))})" if units else ""
            blockers.append(f"{gate}={entry['status']}{where}")
    return blockers


def _serialized(function):
    """Hold the artifact lock shared with the checkpoint runtime; see
    ``aitk.artifact_lock`` for why both blocks lock the same identity."""

    @wraps(function)
    def wrapped(path: Path, *args, **kwargs):
        _reject_unsafe_path(path)
        with artifact_lock(path, ProjectStateError):
            return function(path, *args, **kwargs)

    return wrapped


def _reject_unsafe_path(path: Path) -> None:
    if not path.is_absolute() or Path(os.path.normpath(str(path))) != path:
        raise ProjectStateError("state file path must be absolute and normalized")
    if path.exists() and not path.is_file():
        raise ProjectStateError("state file must be a regular file")


def _atomic_text(path: Path, content: str) -> None:
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


def canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _machine_block(payload: dict[str, object]) -> str:
    return f"{BEGIN}\n{canonical_json(payload)}\n{END}"


def _locate(content: str) -> tuple[int, int, str] | None:
    starts = [match.start() for match in re.finditer(re.escape(BEGIN), content)]
    ends = [match.end() for match in re.finditer(re.escape(END), content)]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise ProjectStateError("project state markers are malformed or duplicated")
    body = content[starts[0] + len(BEGIN) : ends[0] - len(END)].strip()
    return starts[0], ends[0], body


def _validate_token(value: object, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise ProjectStateError(f"{label} must be a portable token")
    return value


def validate_snapshot(payload: object) -> dict[str, object]:
    """Validate and normalize a snapshot, migrating legacy complexity names."""
    if not isinstance(payload, dict):
        raise ProjectStateError("project state snapshot keys do not match schema v2")
    missing = SNAPSHOT_KEYS - set(payload)
    if set(payload) - SNAPSHOT_KEYS or missing - set(OPTIONAL_SNAPSHOT_KEYS):
        raise ProjectStateError("project state snapshot keys do not match schema v2")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ProjectStateError("project state snapshot is not schema version 2")
    result: dict[str, object] = dict(payload)
    for key, factory in OPTIONAL_SNAPSHOT_KEYS.items():
        result.setdefault(key, factory())
    _validate_token(result["workflow"], "workflow")
    result["complexity"] = normalize_complexity(result["complexity"])
    if result["classification_confidence"] not in CONFIDENCE:
        raise ProjectStateError("classification_confidence must be HIGH, MEDIUM, or LOW")
    if result["size"] not in SIZES:
        raise ProjectStateError("size must be one of S, M, L, XL")
    if result["phaseability"] not in PHASEABILITY:
        raise ProjectStateError("phaseability is not a known value")
    shape = derive_execution_shape(str(result["size"]), str(result["phaseability"]))
    if result["execution_shape"] != shape:
        raise ProjectStateError(
            f"execution_shape {result['execution_shape']} does not follow from "
            f"size {result['size']} and phaseability {result['phaseability']} ({shape})"
        )
    if not isinstance(result["phaseability_reason"], str):
        raise ProjectStateError("phaseability_reason must be a string")
    # L leans MULTI_PHASE. Declaring that a broad surface has no independently
    # verifiable unit is a claim, and the claim is the recorded reason.
    if result["size"] in {"L", "XL"} and result["phaseability"] == "none" and not result["phaseability_reason"].strip():
        raise ProjectStateError(
            f"size {result['size']} with phaseability none requires a phaseability reason"
        )
    modifiers = result["modifiers"]
    if not isinstance(modifiers, list) or any(
        not isinstance(item, str) or TOKEN.fullmatch(item) is None for item in modifiers
    ):
        raise ProjectStateError("modifiers must be a list of portable tokens")
    if len(set(modifiers)) != len(modifiers):
        raise ProjectStateError("modifiers must be unique")
    _validate_token(result["current_phase"], "current_phase")
    _validate_token(result["current_gate"], "current_gate")
    if result["gate_status"] not in GATE_STATUSES:
        raise ProjectStateError("gate_status is not a known gate outcome")
    attempts = result["attempts"]
    if not isinstance(attempts, dict) or any(
        TOKEN.fullmatch(str(key)) is None
        or type(count) is not int
        or count < 0
        or count > ATTEMPT_BUDGET + 1
        for key, count in attempts.items()
    ):
        raise ProjectStateError("attempts must map units to counts within budget")
    gates = result["gates"]
    if not isinstance(gates, dict) or any(
        TOKEN.fullmatch(str(key)) is None or not _valid_gate_record(value)
        for key, value in gates.items()
    ):
        raise ProjectStateError(
            "gates must map gate names to {status, phase, units} records"
        )
    escalations = result["escalations"]
    if not isinstance(escalations, dict) or any(
        TOKEN.fullmatch(str(key)) is None
        or type(count) is not int
        or count < 0
        or count > MAX_ESCALATIONS
        for key, count in escalations.items()
    ):
        raise ProjectStateError("escalations must map units to counts within the ladder")
    phases = result["phases"]
    if not isinstance(phases, list):
        raise ProjectStateError("phases must be a list")
    names: set[str] = set()
    normalized_phases: list[dict[str, object]] = []
    for phase in phases:
        if (
            not isinstance(phase, dict)
            or not PHASE_KEYS <= set(phase)
            or set(phase) - PHASE_KEYS - OPTIONAL_PHASE_KEYS
        ):
            raise ProjectStateError("phase entries must contain name, complexity, size, status")
        name = _validate_token(phase["name"], "phase name")
        if name in names:
            raise ProjectStateError(f"duplicate phase: {name}")
        names.add(name)
        if phase["size"] not in SIZES or phase["status"] not in PHASE_STATUSES:
            raise ProjectStateError(f"phase {name} has an invalid size or status")
        entry: dict[str, object] = {
            "name": name,
            "complexity": normalize_complexity(phase["complexity"]),
            "size": phase["size"],
            "status": phase["status"],
        }
        if "tree" in phase:
            tree = phase["tree"]
            if not isinstance(tree, str) or TREE_SHA.fullmatch(tree) is None:
                raise ProjectStateError(f"phase {name} tree must be a 7-64 character hex SHA")
            entry["tree"] = tree.lower()
        normalized_phases.append(entry)
    result["phases"] = normalized_phases
    if result["execution_shape"] != "MULTI_PHASE" and normalized_phases:
        raise ProjectStateError("phases are only recorded for MULTI_PHASE work")
    return result


def parse_project_state(content: str) -> dict[str, object] | None:
    located = _locate(content)
    if located is None:
        return None
    try:
        payload = json.loads(located[2])
    except json.JSONDecodeError as error:
        raise ProjectStateError(f"project state block is not valid JSON: {error}") from error
    return validate_snapshot(payload)


def _replace_block(content: str, payload: dict[str, object]) -> str:
    located = _locate(content)
    block = _machine_block(payload)
    if located is None:
        # A project file made from the template already carries the heading;
        # place the block under it instead of appending a second heading.
        heading = re.search(r"^## Routing Snapshot[ \t]*$", content, re.MULTILINE)
        if heading is not None:
            insert_at = heading.end()
            comment = re.match(r"\n(?:<!--(?:(?!-->).)*-->\n)?", content[insert_at:], re.DOTALL)
            insert_at += comment.end() if comment else 0
            return f"{content[:insert_at]}\n{block}\n{content[insert_at:]}"
        separator = "" if not content or content.endswith("\n\n") else "\n" if content.endswith("\n") else "\n\n"
        return f"{content}{separator}## Routing Snapshot\n\n{block}\n"
    start, end, _ = located
    return content[:start] + block + content[end:]


def _read(path: Path) -> tuple[str, dict[str, object] | None]:
    _reject_unsafe_path(path)
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    return content, parse_project_state(content)


def _write(path: Path, content: str, before: dict[str, object] | None, after: dict[str, object]) -> ProjectStateResult:
    after = validate_snapshot(after)
    if before == after and _locate(content) is not None:
        return ProjectStateResult(after, str(path), False)
    _atomic_text(path, _replace_block(content, after))
    return ProjectStateResult(after, str(path), True)


@_serialized
def initialize(
    path: Path,
    workflow: str,
    complexity: str,
    size: str,
    phaseability: str = "unassessed",
    *,
    confidence: str = "HIGH",
    modifiers: list[str] | None = None,
    phaseability_reason: str = "",
    phase: str = "intake",
    replace: bool = False,
) -> ProjectStateResult:
    """Create the snapshot, or return the existing one when it already records this classification.

    A repeated init with the same classification is a no-op so a resume cannot
    erase progress. A repeated init with a *different* classification is refused:
    silently keeping the old one would let a fresh classification believe it was
    recorded. Move upward with ``set``, or restart with ``--replace``.
    """
    content, before = _read(path)
    modifiers = list(modifiers or [])
    resolved = classify_complexity(complexity, modifiers)
    if before is not None and not replace:
        if before["workflow"] != workflow:
            raise ProjectStateError(
                f"project state already belongs to workflow {before['workflow']}; pass --replace to start over"
            )
        requested = (resolved, size, phaseability, sorted(modifiers))
        recorded = (
            before["complexity"],
            before["size"],
            before["phaseability"],
            sorted(before["modifiers"]),
        )
        if requested != recorded:
            raise ProjectStateError(
                "project state already records "
                f"{before['complexity']}/{before['size']}/{before['phaseability']} for {workflow}; "
                "use `set` to move the classification upward or --replace to restart it"
            )
        return ProjectStateResult(before, str(path), False)
    snapshot: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "workflow": workflow,
        "complexity": resolved,
        "classification_confidence": confidence,
        "size": size,
        "execution_shape": derive_execution_shape(size, phaseability),
        "phaseability": phaseability,
        "phaseability_reason": phaseability_reason,
        "modifiers": modifiers,
        "current_phase": phase,
        "current_gate": "classification",
        "gate_status": "PASS",
        "attempts": {},
        "escalations": {},
        "gates": {"classification": {"status": "PASS", "phase": phase, "units": {}}},
        "phases": [],
    }
    return _write(path, content, before, snapshot)


def show(path: Path) -> ProjectStateResult:
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found")
    return ProjectStateResult(before, str(path), False)


@_serialized
def set_fields(path: Path, **changes: object) -> ProjectStateResult:
    """Apply field changes. Complexity may only move upward except via RECLASSIFY intent."""
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    after = dict(before)
    for key, value in changes.items():
        if value is None:
            continue
        if key not in SNAPSHOT_KEYS or key in {"schema_version", "attempts", "escalations", "gates", "phases"}:
            raise ProjectStateError(f"field cannot be set directly: {key}")
        if key == "complexity":
            proposed = normalize_complexity(value)
            if COMPLEXITIES.index(proposed) < COMPLEXITIES.index(str(before["complexity"])):
                raise ProjectStateError(
                    "complexity is never silently downgraded; record a RECLASSIFY gate "
                    "with evidence and use --replace to restart the classification"
                )
            value = proposed
        after[key] = value
    if "size" in changes or "phaseability" in changes:
        after["execution_shape"] = derive_execution_shape(str(after["size"]), str(after["phaseability"]))
    if any(item in HARD_COMPLEX_MODIFIERS for item in after["modifiers"]):
        after["complexity"] = "COMPLEX"
    return _write(path, content, before, after)


@_serialized
def record_gate(
    path: Path,
    gate: str,
    status: str,
    unit: str | None = None,
    *,
    same_failure: bool = False,
    editorial: bool = False,
) -> ProjectStateResult:
    """Record a gate outcome and apply the attempt budget and escalation ladder.

    Only a reasoning failure the current owner will retry (``RETRY``) charges the
    unit's attempt budget. ``editorial`` marks a retry that fixes wording, a
    missing path, or a rollback note; it is recorded but never charged. The
    recorded status is the *effective* status after the budget: a requested
    ``RETRY`` becomes ``ESCALATE`` once the unit is exhausted or the same failure
    repeats.

    ``ESCALATE`` (requested or derived) hands the unit to the next owner on the
    ladder: the escalation count rises and the attempt count resets, so the RCA
    ladder (parent retry, specialist REVISE, deep-rca, user decision) is
    recorded on one unit. Past ``MAX_ESCALATIONS`` the effective status is
    ``USER_DECISION``. ``RECLASSIFY`` resets the unit's counters (all units when
    no unit is named) because the problem itself changed. ``PASS`` clears the
    unit's counters. ``USER_DECISION`` and ``BLOCKED`` are recorded without
    charging anything: waiting on a person or an environment is not an attempt.

    ``same_failure`` matters across owners: a reason that already exhausted one
    owner and shows up again on the next owner's first attempt is escalated at
    once instead of earning that owner a retry. Within one owner the budget of
    two already escalates the second attempt.

    Every outcome is also written to ``gates[gate]`` as ``{status, phase,
    units}``: the record the checkpoint runtime reads before reserving a gated
    effect. The record is scoped to the current phase (a record from an
    earlier phase is replaced, not merged) and tracks the latest outcome per
    reasoning unit, so a ``PASS`` on slice one cannot hide a ``RETRY`` on slice
    two: the aggregate ``status`` is ``PASS`` only when the latest outcome and
    every unit's latest outcome are ``PASS``. A ``PASS`` recorded without a
    unit is gate-wide and clears the unit outcomes.
    """
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    if status not in GATE_STATUSES or status == "PENDING":
        raise ProjectStateError(f"gate outcome is not a known status: {status}")
    after = dict(before)
    attempts = dict(before["attempts"])
    escalations = dict(before["escalations"])
    key = _validate_token(unit or gate, "unit")
    effective = status
    if status == "PASS":
        attempts.pop(key, None)
        escalations.pop(key, None)
    elif status == "RECLASSIFY":
        if unit is None:
            attempts, escalations = {}, {}
        else:
            attempts.pop(key, None)
            escalations.pop(key, None)
    elif status == "RETRY" and not editorial:
        attempts[key] = int(attempts.get(key, 0)) + 1
        effective = next_gate_status(attempts[key], same_failure)
        if same_failure and attempts[key] == 1 and int(escalations.get(key, 0)) > 0:
            effective = "ESCALATE"
    if effective == "ESCALATE":
        stage = int(escalations.get(key, 0)) + 1
        attempts.pop(key, None)
        if stage > MAX_ESCALATIONS:
            effective = "USER_DECISION"
        else:
            escalations[key] = stage
    after["current_gate"] = _validate_token(gate, "gate")
    after["gate_status"] = effective
    after["attempts"] = attempts
    after["escalations"] = escalations
    after["gates"] = _record_gate_outcome(
        before["gates"], after["current_gate"], before["current_phase"], effective, unit
    )
    return _write(path, content, before, after)


def _record_gate_outcome(
    gates: dict[str, object], gate: str, phase: str, effective: str, unit: str | None
) -> dict[str, object]:
    updated = dict(gates)
    previous = updated.get(gate)
    if isinstance(previous, dict) and previous["phase"] == phase:
        units = dict(previous["units"])
    else:
        units = {}
    if unit is None and effective == "PASS":
        units = {}
    elif unit is not None:
        units[_validate_token(unit, "unit")] = effective
    else:
        units[gate] = effective
    outstanding = [status for status in units.values() if status != "PASS"]
    status = effective if effective != "PASS" else (outstanding[0] if outstanding else "PASS")
    updated[gate] = {"status": status, "phase": phase, "units": units}
    return updated


@_serialized
def advance_phase(path: Path, phase: str) -> ProjectStateResult:
    """Move to the next phase; only legal when the current gate passed.

    ``PENDING`` is not a pass: a phase whose gate was never recorded cannot be
    left behind, so every phase records at least one gate outcome.
    """
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    if before["gate_status"] != "PASS":
        raise ProjectStateError(
            f"cannot advance while gate {before['current_gate']} is {before['gate_status']}; "
            "record a PASS for the current gate first"
        )
    after = dict(before)
    after["current_phase"] = _validate_token(phase, "phase")
    after["current_gate"] = phase
    after["gate_status"] = "PENDING"
    # A gate outcome belongs to the phase that recorded it. Clearing the
    # phase-scoped gates here means the next phase's effects wait for that
    # phase's own verification and review, never a stale PASS.
    after["gates"] = {
        name: record for name, record in before["gates"].items() if name not in PHASE_SCOPED_GATES
    }
    return _write(path, content, before, after)


@_serialized
def set_phases(path: Path, phases: list[dict[str, object]]) -> ProjectStateResult:
    """Replace the MULTI_PHASE decomposition table."""
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    after = dict(before)
    after["phases"] = phases
    return _write(path, content, before, after)


@_serialized
def update_phase(
    path: Path, name: str, status: str, tree: str | None = None
) -> ProjectStateResult:
    """Move one phase; ``tree`` records the SHA it ended on (the next review base)."""
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    phases = [dict(item) for item in before["phases"]]
    match = next((item for item in phases if item["name"] == name), None)
    if match is None:
        raise ProjectStateError(f"unknown phase: {name}")
    match["status"] = status
    if tree is not None:
        match["tree"] = tree
    elif status == "done" and "tree" not in match:
        raise ProjectStateError(
            f"phase {name} cannot be marked done without --sha; the tree is the next phase's review base"
        )
    after = dict(before)
    after["phases"] = phases
    return _write(path, content, before, after)


def state_file(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (Path.cwd() / "PROJECT.md").resolve()
