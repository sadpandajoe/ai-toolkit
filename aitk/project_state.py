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
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from .artifact_lock import artifact_lock


# Local workflow state: written into the target repository, never committed.
# The git guard (aitk.hooks.git_guard) imports this list, so this module keeps
# to the standard library and artifact_lock.
STATE_FILES = (
    "PROJECT.md",
    "PROJECT_ARCHIVE.md",
    "PLAN.md",
    "WATCH.md",
    "CHERRY_PICK.md",
    "CI_FIX.md",
)
# Per-repository toolkit data: org config, Codex memory, observations, metrics.
TOOLKIT_DATA_DIR = ".ai-toolkit/"
EXCLUDE_HEADER = "# ai-toolkit local workflow state (bin/aitk adds these)"


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
    "operations",
}
# Snapshots written before the escalation ladder, the per-gate record and the
# operation log existed lack these keys; they read as empty instead of failing
# validation.
# ``gates`` maps a gate name to ``{"status", "phase", "units"}``: the aggregate
# outcome, the phase it was recorded in, and the latest outcome per reasoning
# unit. The checkpoint runtime reads it before reserving an effect the contract
# gates on verification or review, which is what makes "two records, one
# truth" a machine invariant. A record is scoped to its phase: ``advance``
# clears the phase-scoped gates, and a record from another phase never
# satisfies a reservation.
OPTIONAL_SNAPSHOT_KEYS = {"escalations": dict, "gates": dict, "operations": dict}
# A gate record may carry the evidence behind its latest outcome: ``run`` for a
# verification run (``bin/aitk verify --run``) and ``review`` for the reviewer
# results (``gate --gate review --result``) or a review exception. A new outcome
# replaces the evidence, and an outcome recorded without evidence clears it, so
# a PASS never inherits the run or review of an earlier attempt.
GATE_RECORD_KEYS = {"status", "phase", "units"}
GATE_EVIDENCE_KEYS = {"run", "review"}
STRENGTHS = ("STRONG", "PARTIAL", "WEAK")
REVIEW_EXCEPTIONS = ("zero-logic", "micro-fix")
RESULT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
# Provider operation ids (N14): `push:<sha>`, `rerun:<run-id>`,
# `reply:<thread-id>`, `review:<pr>:<sha>`. GitHub node ids carry `_` and `=`.
OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+/=_-]{0,255}")
OUTPUT_TAIL_LINES = 20
OUTPUT_TAIL_CHARS = 2000
OBSERVATION_KINDS = (
    "user-correction",
    "misroute",
    "reclassify",
    "gate-repeat",
    "specialist-invalidation",
    "workaround",
    "low-yield-lane",
)
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


def _valid_tree(value: object) -> bool:
    return value is None or (isinstance(value, str) and TREE_SHA.fullmatch(value) is not None)


def _valid_run(value: object) -> bool:
    """A verification run: what ran, how it ended, and on which tree."""
    if not isinstance(value, dict) or set(value) != {
        "command", "exit_code", "output_tail", "tree", "time", "strength"
    }:
        return False
    return (
        isinstance(value["command"], str)
        and bool(value["command"].strip())
        and (value["exit_code"] is None or type(value["exit_code"]) is int)
        and isinstance(value["output_tail"], str)
        and _valid_tree(value["tree"])
        and isinstance(value["time"], str)
        and value["strength"] in STRENGTHS
    )


def _valid_review(value: object) -> bool:
    """Reviewer results by digest, or a review exception, with the reviewed tree."""
    if not isinstance(value, dict) or not {"tree", "time"} <= set(value):
        return False
    if not _valid_tree(value["tree"]) or not isinstance(value["time"], str):
        return False
    extra = set(value) - {"tree", "time"}
    if extra == {"exception"}:
        return value["exception"] in REVIEW_EXCEPTIONS
    if extra != {"results"} or not isinstance(value["results"], list) or not value["results"]:
        return False
    return all(
        isinstance(item, dict)
        and set(item) == {"route", "boundary", "provider", "digest"}
        and all(isinstance(item[key], str) for key in ("route", "boundary", "provider"))
        and isinstance(item["digest"], str)
        and RESULT_DIGEST.fullmatch(item["digest"]) is not None
        for item in value["results"]
    )


def _valid_gate_record(value: object) -> bool:
    if not isinstance(value, dict) or not GATE_RECORD_KEYS <= set(value):
        return False
    if set(value) - GATE_RECORD_KEYS - GATE_EVIDENCE_KEYS:
        return False
    if value["status"] not in GATE_STATUSES or value["status"] == "PENDING":
        return False
    if TOKEN.fullmatch(str(value["phase"])) is None:
        return False
    if "run" in value and not _valid_run(value["run"]):
        return False
    if "review" in value and not _valid_review(value["review"]):
        return False
    units = value["units"]
    return isinstance(units, dict) and all(
        TOKEN.fullmatch(str(unit)) is not None and status in GATE_STATUSES and status != "PENDING"
        for unit, status in units.items()
    )


def gate_blockers(
    snapshot: dict[str, object],
    gates: list[str] | tuple[str, ...],
    *,
    require_records: bool = True,
) -> list[str]:
    """Name what stops each gate from counting as PASS for the current phase.

    Empty means every named gate is PASS: recorded in the current phase, with
    no reasoning unit left at a non-PASS outcome. With ``require_records`` (the
    default) a PASS also has to carry its evidence: a verification PASS needs
    the run `bin/aitk verify --run` recorded, and a review PASS needs the
    reviewer results (`--result`) or a review exception. A PASS someone typed
    by hand does not count. `bin/aitk deliver` and the review gate hook read
    the gates this way. The checkpoint runtime, which nothing reserves through
    any more and which phase 5 deletes, passes ``require_records=False``.
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
        elif require_records and gate == "verification":
            run = entry.get("run")
            if run is None:
                blockers.append(
                    "verification=PASS with no recorded run (record it with `bin/aitk verify --run`)"
                )
            elif run["exit_code"] != 0:
                blockers.append(f"verification run exited {run['exit_code']}")
        elif require_records and gate == "review" and entry.get("review") is None:
            blockers.append(
                "review=PASS with no reviewer record (record it with "
                "`--result <model-run envelope>`)"
            )
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
    operations = result["operations"]
    if not isinstance(operations, dict) or any(
        not isinstance(key, str) or OPERATION_ID.fullmatch(key) is None or not isinstance(value, str)
        for key, value in operations.items()
    ):
        raise ProjectStateError("operations must map operation ids to the time they were recorded")
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
    run: dict[str, object] | None = None,
    review: dict[str, object] | None = None,
    reason: str | None = None,
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

    ``run`` and ``review`` are the evidence for this outcome (see
    ``GATE_EVIDENCE_KEYS``); they replace whatever the gate carried before.
    A ``RECLASSIFY`` outcome, and a ``RETRY`` the caller marks as the same
    failure, also append a ``reclassify`` or ``gate-repeat`` line to the
    observation queue, with ``reason`` as its detail.
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
        before["gates"], after["current_gate"], before["current_phase"], effective, unit,
        run=run, review=review,
    )
    result = _write(path, content, before, after)
    kind = None
    if status == "RECLASSIFY":
        kind = "reclassify"
    elif status == "RETRY" and same_failure and not editorial:
        kind = "gate-repeat"
    if kind is not None:
        default = (
            f"gate {gate} recorded RECLASSIFY on unit {key}"
            if kind == "reclassify"
            else f"gate {gate} failed again for the same reason on unit {key} ({effective})"
        )
        append_observation(
            path.parent,
            {
                "kind": kind,
                "workflow": before["workflow"],
                "phase": before["current_phase"],
                "complexity": before["complexity"],
                "size": before["size"],
                "shape": before["execution_shape"],
                "gate": gate,
                "unit": key,
                "detail": (reason or "").strip() or default,
            },
        )
    return result


def _record_gate_outcome(
    gates: dict[str, object],
    gate: str,
    phase: str,
    effective: str,
    unit: str | None,
    *,
    run: dict[str, object] | None = None,
    review: dict[str, object] | None = None,
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
    record: dict[str, object] = {"status": status, "phase": phase, "units": units}
    if run is not None:
        record["run"] = dict(run)
    if review is not None:
        record["review"] = dict(review)
    updated[gate] = record
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


def exclude_entries() -> tuple[str, ...]:
    return (*STATE_FILES, TOOLKIT_DATA_DIR)


def ensure_excluded(directory: Path) -> Path | None:
    """Keep local workflow state out of `git status` for the repo at `directory`.

    Appends each STATE_FILES entry and `.ai-toolkit/` to the exclude file that
    `git rev-parse --git-path info/exclude` names, once. In a linked worktree
    `.git` is a file, so the literal `.git/info/exclude` would be wrong; git
    names the shared exclude file instead. Returns the exclude file, or None
    when `directory` is not inside a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--git-path", "info/exclude"],
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    named = result.stdout.strip()
    if result.returncode != 0 or not named:
        return None
    exclude = Path(named)
    if not exclude.is_absolute():
        exclude = Path(directory) / exclude
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    present = {line.strip() for line in existing.splitlines()}
    missing = [entry for entry in exclude_entries() if entry not in present]
    if not missing:
        return exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    lines = ([] if EXCLUDE_HEADER in present else [EXCLUDE_HEADER]) + missing
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write(separator + "\n".join(lines) + "\n")
    return exclude


def _git_output(directory: Path, *arguments: str, env: dict[str, str] | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *arguments],
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
            env=env,
        )
    except OSError:
        return None
    output = result.stdout.strip()
    return output if result.returncode == 0 and output else None


def git_toplevel(directory: Path) -> Path | None:
    named = _git_output(directory, "rev-parse", "--show-toplevel")
    return Path(named).resolve() if named else None


def state_file(explicit: str | None, cwd: Path | None = None) -> Path:
    """The PROJECT.md to read or write.

    An explicit path wins. Otherwise the nearest one: the working directory,
    then the top of its git repository, with symlinks resolved; when neither
    exists, the working directory is where `init` creates it.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    working = (cwd or Path.cwd()).resolve()
    candidate = working / "PROJECT.md"
    if candidate.is_file():
        return candidate.resolve()
    top = git_toplevel(working)
    if top is not None and (top / "PROJECT.md").is_file():
        return (top / "PROJECT.md").resolve()
    return candidate


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_pathspecs() -> list[str]:
    """Pathspecs that leave local workflow state out of a tree or a commit."""
    return [f":(exclude,glob)**/{name}" for name in STATE_FILES] + [
        f":(exclude,glob)**/{TOOLKIT_DATA_DIR}**"
    ]


def working_tree_sha(directory: Path) -> str | None:
    """The tree the working tree would commit as, with the state files left out.

    Everything `git add -A` would stage (ignored files and the exclude file
    honored) is staged into a throwaway copy of the index, so the real index
    is never touched, and `git write-tree` names the result. The same content
    gives the same SHA whether or not it is committed, which is what lets
    `deliver` compare the tree a verification run or a review saw with the
    tree it is about to push. None outside a git repository.
    """
    top = git_toplevel(directory)
    if top is None:
        return None
    index = _git_output(top, "rev-parse", "--git-path", "index")
    if index is None:
        return None
    real_index = Path(index) if Path(index).is_absolute() else top / index
    with tempfile.TemporaryDirectory(prefix="aitk-tree-") as scratch:
        temporary_index = Path(scratch) / "index"
        if real_index.is_file():
            shutil.copyfile(real_index, temporary_index)
        environment = {**os.environ, "GIT_INDEX_FILE": str(temporary_index)}
        try:
            added = subprocess.run(
                ["git", "-C", str(top), "add", "-A", "--", ".", *state_pathspecs()],
                text=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=False,
                env=environment,
            )
        except OSError:
            return None
        if added.returncode != 0:
            return None
        return _git_output(top, "write-tree", env=environment)


def toolkit_data_root(directory: Path) -> Path:
    """Where `.ai-toolkit/` lives for work in `directory`: its repository top, else itself."""
    return git_toplevel(directory) or Path(directory).resolve()


def append_jsonl(path: Path, entry: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    return path


def append_observation(directory: Path, entry: dict[str, object]) -> Path:
    """Append one line to `.ai-toolkit/observations.jsonl` (the reflection queue).

    `kind` must be one of the queue's triggers (`OBSERVATION_KINDS`, owned by
    skills/reflection/references/observations.md); `detail` is one sentence.
    The data directory is added to the exclude file first.
    """
    kind = entry.get("kind")
    if kind not in OBSERVATION_KINDS:
        raise ProjectStateError(
            f"observation kind must be one of {', '.join(OBSERVATION_KINDS)}, got {kind!r}"
        )
    detail = entry.get("detail")
    if not isinstance(detail, str) or not detail.strip():
        raise ProjectStateError("an observation needs a one-sentence detail")
    workflow = entry.get("workflow")
    if not isinstance(workflow, str) or not workflow.strip():
        raise ProjectStateError("an observation names its workflow")
    root = toolkit_data_root(directory)
    ensure_excluded(root)
    line = {"timestamp": now_iso(), **{key: value for key, value in entry.items() if value is not None}}
    return append_jsonl(root / TOOLKIT_DATA_DIR / "observations.jsonl", line)


ACCEPTANCE_LINE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?(?:Acceptance(?: command)?|Regression check)(?:\*\*)?[ \t]*:[ \t]*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def _normalized_command(command: str) -> str:
    return " ".join(command.split())


def acceptance_commands(path: Path) -> set[str]:
    """Acceptance commands named in PLAN.md and PROJECT.md next to `path`.

    A plan slice's `Acceptance:` line, a phase handoff's `Acceptance:` and an
    RCA record's `Regression check:` name the command that proves the work;
    a backticked span is the command, otherwise the whole value is.
    """
    commands: set[str] = set()
    for name in ("PLAN.md", path.name):
        candidate = path.parent / name
        try:
            text = candidate.read_text(encoding="utf-8") if candidate.is_file() else ""
        except (OSError, UnicodeDecodeError):
            continue
        for match in ACCEPTANCE_LINE.finditer(text):
            value = match.group(1).strip()
            spans = re.findall(r"`([^`]+)`", value)
            for command in spans or [value]:
                if command.strip():
                    commands.add(_normalized_command(command))
    return commands


def _tail(output: str) -> str:
    lines = output.splitlines()[-OUTPUT_TAIL_LINES:]
    return "\n".join(lines)[-OUTPUT_TAIL_CHARS:]


def run_command(command: str, cwd: Path, timeout_seconds: int) -> tuple[int | None, str]:
    """Run `command` through bash (sh when bash is missing); exit code and combined output."""
    shell = shutil.which("bash") or "/bin/sh"
    try:
        completed = subprocess.run(
            [shell, "-c", command],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
            errors="replace",
        )
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return None, f"{partial}\n[aitk verify] timed out after {timeout_seconds}s"
    except OSError as error:
        return None, f"[aitk verify] could not start: {error}"
    return completed.returncode, completed.stdout or ""


@dataclass(frozen=True)
class VerificationRun:
    result: ProjectStateResult
    run: dict[str, object]
    status: str
    tree_changed: bool


def verify_run(
    path: Path,
    command: str,
    *,
    cwd: Path,
    strength: str | None = None,
    unit: str | None = None,
    same_failure: bool = False,
    timeout_seconds: int = 1800,
    reason: str | None = None,
) -> VerificationRun:
    """Run a check and record it on the verification gate.

    PASS only on exit 0; any other exit, a timeout or a command that cannot
    start is a RETRY on `unit` (the attempt budget applies). The record keeps
    the command, the exit code, the output tail, the tree the command ran on
    and the time. `STRONG` is the default strength only when the command is
    the acceptance command named in PLAN.md or the RCA record; otherwise the
    default is `PARTIAL`. An explicit strength is the caller's claim.
    """
    if not command.strip():
        raise ProjectStateError("verify --run needs a command")
    if strength is not None and strength not in STRENGTHS:
        raise ProjectStateError(f"strength must be one of {', '.join(STRENGTHS)}")
    _content, snapshot = _read(path)
    if snapshot is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    tree = working_tree_sha(cwd)
    exit_code, output = run_command(command, cwd, timeout_seconds)
    after_tree = working_tree_sha(cwd)
    if strength is None:
        strength = (
            "STRONG" if _normalized_command(command) in acceptance_commands(path) else "PARTIAL"
        )
    run = {
        "command": command,
        "exit_code": exit_code,
        "output_tail": _tail(output),
        "tree": tree,
        "time": now_iso(),
        "strength": strength,
    }
    status = "PASS" if exit_code == 0 else "RETRY"
    result = record_gate(
        path, "verification", status, unit, same_failure=same_failure, run=run, reason=reason
    )
    return VerificationRun(result, run, str(result.snapshot["gate_status"]), tree != after_tree)


def result_digest(result: object) -> str:
    """The digest `model-run` records for a worker result (canonical JSON, sha256)."""
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def review_from_envelopes(envelopes: list[object]) -> dict[str, object]:
    """Turn `model-run` envelopes into the review gate's evidence.

    Each envelope must be a completed, non-dry run whose result still matches
    its recorded digest, and every envelope must have reviewed the same tree.
    """
    if not envelopes:
        raise ProjectStateError("a review record needs at least one model-run envelope")
    results: list[dict[str, object]] = []
    trees: set[object] = set()
    for envelope in envelopes:
        if not isinstance(envelope, dict) or envelope.get("command") != "model-run":
            raise ProjectStateError("--result must be the JSON envelope `bin/aitk model-run` printed")
        if envelope.get("dry_run"):
            raise ProjectStateError("a dry-run envelope reviewed nothing")
        if envelope.get("error") is not None:
            raise ProjectStateError("the model-run envelope records an error, not a review")
        result = envelope.get("result")
        if not isinstance(result, dict) or result.get("status") != "completed":
            raise ProjectStateError("the reviewer did not complete; its envelope cannot back a review PASS")
        digest = envelope.get("result_digest")
        if not isinstance(digest, str) or RESULT_DIGEST.fullmatch(digest) is None:
            raise ProjectStateError("the model-run envelope has no result digest")
        if result_digest(result) != digest:
            raise ProjectStateError("the reviewer result does not match its recorded digest")
        tree = envelope.get("reviewed_tree")
        if not isinstance(tree, str) or TREE_SHA.fullmatch(tree) is None:
            raise ProjectStateError("the model-run envelope does not name the tree it reviewed")
        trees.add(tree.lower())
        results.append(
            {
                "route": str(envelope.get("route", "")),
                "boundary": str(envelope.get("boundary", "")),
                "provider": str(envelope.get("provider", "")),
                "digest": digest,
            }
        )
    if len(trees) != 1:
        raise ProjectStateError("the review envelopes reviewed different trees")
    return {"results": results, "tree": trees.pop(), "time": now_iso()}


def review_exception(path: Path, kind: str, cwd: Path) -> dict[str, object]:
    """Evidence for a review exception (rules/gates.md, Review Exceptions).

    A zero-logic or micro-fix diff may pass review without a reviewer only on
    a passing verification run recorded in this phase on the current tree.
    """
    if kind not in REVIEW_EXCEPTIONS:
        raise ProjectStateError(f"review exception must be one of {', '.join(REVIEW_EXCEPTIONS)}")
    _content, snapshot = _read(path)
    if snapshot is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    blockers = gate_blockers(snapshot, ["verification"])
    if blockers:
        raise ProjectStateError(
            "a review exception needs a passing verification run in this phase: " + "; ".join(blockers)
        )
    tree = working_tree_sha(cwd)
    run_tree = snapshot["gates"]["verification"]["run"]["tree"]
    if tree is None or tree != run_tree:
        raise ProjectStateError(
            "the working tree changed after the verification run; run `bin/aitk verify --run` again"
        )
    return {"exception": kind, "tree": tree, "time": now_iso()}


@_serialized
def record_operation(path: Path, operation: str) -> ProjectStateResult:
    """Record that a provider operation ran (N14); a repeat is a no-op."""
    if OPERATION_ID.fullmatch(operation) is None:
        raise ProjectStateError(f"operation id is not a portable id: {operation!r}")
    content, before = _read(path)
    if before is None:
        raise ProjectStateError("no project state snapshot found; run init first")
    if operation in before["operations"]:
        return ProjectStateResult(before, str(path), False)
    after = dict(before)
    after["operations"] = {**before["operations"], operation: now_iso()}
    return _write(path, content, before, after)


def operation_recorded(path: Path, operation: str) -> str | None:
    """When the operation was recorded, or None when it has not run."""
    if OPERATION_ID.fullmatch(operation) is None:
        raise ProjectStateError(f"operation id is not a portable id: {operation!r}")
    return show(path).snapshot["operations"].get(operation)


def _shape_note(snapshot: dict[str, object]) -> str:
    reason = str(snapshot["phaseability_reason"]).strip()
    if reason:
        return reason
    if snapshot["size"] in {"S", "M"} and snapshot["phaseability"] in {"unassessed", "none"}:
        return "S/M default"
    return str(snapshot["phaseability"])


def complexity_block(snapshot: dict[str, object], reason: str | None = None) -> str:
    """The `## Complexity Gate` block rules/complexity-gate.md asks for."""
    modifiers = ", ".join(snapshot["modifiers"]) or "none"
    return "\n".join(
        [
            "## Complexity Gate",
            f"Complexity: {snapshot['complexity']}",
            f"Size: {snapshot['size']}",
            f"Shape: {snapshot['execution_shape']} — {_shape_note(snapshot)}",
            f"Confidence: {snapshot['classification_confidence']}",
            f"Modifiers: {modifiers}",
            f"Reason: {(reason or '').strip() or 'not given'}",
        ]
    )


DEFAULT_NEXT = {
    "PASS": "continue to the workflow's next step",
    "RETRY": "the same owner fixes {unit} and re-runs the same checks",
    "ESCALATE": "stop fixing {unit}; hand it to the next owner on the ladder with an adjudication package",
    "RECLASSIFY": "move the classification upward with `bin/aitk project-state set`, then re-enter the loop",
    "USER_DECISION": "ask the user, with the options, their costs, the evidence and a recommendation",
    "BLOCKED": "record what is missing and stop this path",
}


def gate_block(
    before: dict[str, object] | None,
    after: dict[str, object],
    gate: str,
    unit: str | None = None,
    *,
    strength: str | None = None,
    evidence: str | None = None,
    next_step: str | None = None,
    reason: str | None = None,
    editorial: bool = False,
) -> str:
    """The `## Gate:` block rules/gates.md describes, from the recorded outcome."""
    key = unit or gate
    status = str(after["gate_status"])
    previous = int(before["attempts"].get(key, 0)) if before else 0
    charged = status not in {"USER_DECISION", "BLOCKED"} and not editorial
    attempt = max(int(after["attempts"].get(key, 0)), previous + 1 if charged else previous, 1)
    escalation = int(after["escalations"].get(key, 0))
    attempt_line = f"Attempt: {min(attempt, ATTEMPT_BUDGET)}/{ATTEMPT_BUDGET} on {key}"
    if escalation:
        attempt_line += f" (escalation {escalation}/{MAX_ESCALATIONS})"
    record = after["gates"].get(gate, {})
    run = record.get("run") if isinstance(record, dict) else None
    review = record.get("review") if isinstance(record, dict) else None
    if evidence is None and run is not None:
        code = "timed out or did not start" if run["exit_code"] is None else f"exit {run['exit_code']}"
        evidence = f"`{run['command']}` {code} on tree {str(run['tree'] or 'none')[:12]}"
    if evidence is None and review is not None:
        if "exception" in review:
            evidence = f"review exception: {review['exception']} on tree {str(review['tree'])[:12]}"
        else:
            lanes = ", ".join(f"{item['boundary']} ({item['provider']})" for item in review["results"])
            evidence = f"{lanes} on tree {str(review['tree'])[:12]}"
    lines = [f"## Gate: {gate}", f"Status: {status}", attempt_line]
    if gate == "verification" or strength is not None:
        lines.append(f"Strength: {strength or (run['strength'] if run else 'not recorded')}")
    lines.append(f"Evidence: {(evidence or 'not given').strip()}")
    if reason:
        lines.append(f"Reason: {reason.strip()}")
    lines.append(f"Next: {(next_step or DEFAULT_NEXT[status].format(unit=key)).strip()}")
    return "\n".join(lines)
