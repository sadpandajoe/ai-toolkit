"""Workflow metrics: ``bin/aitk metrics emit`` appends one event, ``bin/aitk metrics`` sums them.

Metrics never gate progress. A failed emit is reported and the workflow goes
on; nothing reads metrics to allow or refuse an action (``lane-yield`` reads
them only to propose demotions).

Events go to ``.ai-toolkit/metrics.jsonl`` at the repository top (the data
directory is added to the git exclude file first). Reading falls back to the
legacy ``.claude/metrics.jsonl`` only when the canonical file does not exist;
nothing new is ever written there.

An event carries, filled from the ``PROJECT.md`` snapshot when there is one:
``timestamp``; ``command`` (the workflow, the legacy key) and ``workflow``;
``status``; ``complexity`` (``trivial | standard | complex``), ``size``,
``shape`` (``single_phase | batched | multi_phase``) and ``phases`` (a count);
``gates`` (``{gate: {"status": ..., "attempts": n}}``, the latest outcome per
gate); ``retries`` and ``escalations`` (what the snapshot still holds, which a
caller that counted more overrides with ``--extra``); ``review`` (a
``review merge --json`` file or a review object, whose ``lanes`` follow the
``review.lanes`` schema in ``aitk/review_plan.py``); ``workers`` and
``premium_calls``. ``--extra key=value`` adds anything else, and the names the
workflows used before this command are normalised (``worker_usage`` becomes
``workers``, ``gate_decisions`` becomes ``decisions``, and so on).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

from .project_state import (
    ProjectStateError,
    append_jsonl,
    ensure_excluded,
    now_iso,
    parse_project_state,
    toolkit_data_root,
)


CANONICAL = Path(".ai-toolkit") / "metrics.jsonl"
LEGACY = Path(".claude") / "metrics.jsonl"
TERMINAL = ("PASS", "ESCALATE", "USER_DECISION", "BLOCKED")
# Workflows that report `clean` mean the same as a PASS terminal status.
PASS_ALIASES = {"PASS", "CLEAN"}
PREMIUM_ROUTES = ("planning", "deep-review", "deep-rca", "rca")
FIELD_ALIASES = {
    "worker_usage": "workers",
    "worker_counts": "workers",
    "gate_decisions": "decisions",
    "retry_count": "retries",
    "retries_count": "retries",
    "escalation_count": "escalations",
    "reclassification_count": "reclassifications",
    "reclassified": "reclassifications",
    "outcome": "status",
    "observations_written": "observations",
    "execution_shape": "shape",
}
COMPLEXITY_ALIASES = {
    "trivial": "trivial",
    "standard": "standard",
    "moderate": "standard",
    "non-trivial": "standard",
    "complex": "complex",
}
PERIOD = re.compile(r"(\d+)d")
REVIEW_LANES_HELP = """\
review.lanes schema (also in the aitk/review_plan.py docstring):
  {"<lane>": {"raised": n, "accepted": n, "converged": n, "confirmed": n,
              "refuted": n, "not_fixed": n, "introduced": n}}
  lanes: independent, second-family, verify-major, delta, adversarial,
  deep-quality, architecture. Missing counts read as zero. `review merge
  --json` output fills raised and converged; add accepted after validation.

Metrics never gate progress: on a failed emit, note it and continue."""


class MetricsError(ValueError):
    """An emit or summary argument could not be used."""


def metrics_file(cwd: Path) -> Path:
    return toolkit_data_root(cwd) / CANONICAL


def read_events(cwd: Path, explicit: Path | None = None) -> tuple[Path, list[dict[str, object]]]:
    """The events file and its JSON-object lines (canonical, else legacy)."""
    if explicit is not None:
        path = explicit
    else:
        root = toolkit_data_root(cwd)
        path = root / CANONICAL
        if not path.exists() and (root / LEGACY).is_file():
            path = root / LEGACY
    events: list[dict[str, object]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    return path, events


def _value(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def pairs(items: Iterable[str], *, integers: bool = False) -> dict[str, object]:
    """``key=value`` arguments to a dict; with ``integers`` every value is a count."""
    result: dict[str, object] = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise MetricsError(f"expected key=value, got {item!r}")
        if integers:
            try:
                count = int(value)
            except ValueError as error:
                raise MetricsError(f"{key} needs a whole number, got {value!r}") from error
            if count < 0:
                raise MetricsError(f"{key} cannot be negative")
            result[key.strip()] = count
        else:
            result[key.strip()] = _value(value)
    return result


def normalise(fields: Mapping[str, object]) -> dict[str, object]:
    """Map the names workflows used to hand-write onto the event schema."""
    result: dict[str, object] = {}
    for key, value in fields.items():
        name = FIELD_ALIASES.get(key, key)
        if name == "complexity" and isinstance(value, str):
            value = COMPLEXITY_ALIASES.get(value.lower(), value.lower())
        if name == "shape" and isinstance(value, str):
            value = value.lower()
        result[name] = value
    return result


def _snapshot_fields(snapshot: Mapping[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    complexity = snapshot.get("complexity")
    if isinstance(complexity, str):
        fields["complexity"] = complexity.lower()
    if isinstance(snapshot.get("size"), str):
        fields["size"] = snapshot["size"]
    if isinstance(snapshot.get("execution_shape"), str):
        fields["shape"] = str(snapshot["execution_shape"]).lower()
    phases = snapshot.get("phases")
    if isinstance(phases, list):
        fields["phases"] = len(phases)
    attempts = snapshot.get("attempts") if isinstance(snapshot.get("attempts"), dict) else {}
    escalations = snapshot.get("escalations") if isinstance(snapshot.get("escalations"), dict) else {}
    gates = snapshot.get("gates") if isinstance(snapshot.get("gates"), dict) else {}
    summary: dict[str, object] = {}
    for gate, record in sorted(gates.items()):  # type: ignore[union-attr]
        if isinstance(record, dict) and isinstance(record.get("status"), str):
            entry: dict[str, object] = {"status": record["status"]}
            if gate in attempts:  # type: ignore[operator]
                entry["attempts"] = attempts[gate]  # type: ignore[index]
            summary[str(gate)] = entry
    if summary:
        fields["gates"] = summary
    fields["retries"] = sum(int(value) for value in attempts.values())  # type: ignore[union-attr]
    fields["escalations"] = sum(int(value) for value in escalations.values())  # type: ignore[union-attr]
    return fields


def _review(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MetricsError(f"cannot read the review file {path}: {error}") from error
    if not isinstance(payload, dict):
        raise MetricsError("the review file must hold a JSON object")
    if payload.get("command") == "review merge":
        return {"lanes": payload.get("lanes", {})}
    return payload


def build_event(
    workflow: str,
    status: str,
    *,
    snapshot: Mapping[str, object] | None = None,
    review: Mapping[str, object] | None = None,
    workers: Mapping[str, int] | None = None,
    extra: Mapping[str, object] | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    """One event: the snapshot's fields, then the caller's, names normalised."""
    if not workflow.strip() or not status.strip():
        raise MetricsError("an event needs a workflow and a status")
    event: dict[str, object] = {"timestamp": timestamp or now_iso(), "command": workflow, "workflow": workflow}
    if snapshot:
        event.update(_snapshot_fields(snapshot))
    event["status"] = status
    if review:
        event["review"] = dict(review)
    extras = normalise(extra or {})
    combined_workers: dict[str, int] = {}
    listed = extras.pop("workers", None)
    if isinstance(listed, dict):
        combined_workers.update({str(key): int(value) for key, value in listed.items() if isinstance(value, int)})
    combined_workers.update(workers or {})
    if combined_workers:
        event["workers"] = combined_workers
        event["premium_calls"] = sum(combined_workers.get(route, 0) for route in PREMIUM_ROUTES)
    for key in ("command", "workflow", "timestamp"):
        extras.pop(key, None)
    event.update(extras)
    return event


def emit(
    cwd: Path,
    workflow: str,
    status: str,
    *,
    project_file: Path | None = None,
    review_file: Path | None = None,
    workers: Iterable[str] = (),
    extra: Iterable[str] = (),
) -> tuple[Path, dict[str, object]]:
    """Append one event; the snapshot is read from ``project_file`` when it exists."""
    snapshot = None
    if project_file is not None and project_file.is_file():
        try:
            snapshot = parse_project_state(project_file.read_text(encoding="utf-8"))
        except (ProjectStateError, OSError):
            snapshot = None
    event = build_event(
        workflow,
        status,
        snapshot=snapshot,
        review=_review(review_file) if review_file else None,
        workers={key: int(value) for key, value in pairs(workers, integers=True).items()},  # type: ignore[arg-type]
        extra=pairs(extra),
    )
    root = toolkit_data_root(cwd)
    ensure_excluded(root)
    return append_jsonl(root / CANONICAL, event), event


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def select(
    events: Iterable[dict[str, object]],
    *,
    period: str | None = None,
    command: str | None = None,
    since: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Filter by ``--period`` (``7d``, ``30d``, ``Nd`` or ``all``), ``--command`` and ``--since``."""
    now = now or datetime.now(timezone.utc)
    floor = None
    if period and period != "all":
        match = PERIOD.fullmatch(period)
        if not match:
            raise MetricsError(f"period must be Nd or all, got {period!r}")
        floor = now - timedelta(days=int(match.group(1)))
    if since:
        start = _time(since)
        if start is None:
            raise MetricsError(f"--since must be an ISO date or time, got {since!r}")
        floor = max(floor, start) if floor else start
    selected = []
    for event in events:
        name = event.get("command") or event.get("workflow")
        if command and name != command:
            continue
        if floor is not None:
            when = _time(event.get("timestamp"))
            if when is None or when < floor:
                continue
        selected.append(event)
    return selected


def _number(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else 0


def aggregate(events: Iterable[dict[str, object]]) -> dict[str, object]:
    """Pass rates, retries and escalations, worker usage, complexity, lane yield."""
    events = list(events)
    workflows: dict[str, dict[str, object]] = {}
    workers: Counter[str] = Counter()
    complexity: Counter[str] = Counter()
    lanes: dict[str, dict[str, int]] = {}
    trivial_clean = 0
    for event in events:
        name = str(event.get("command") or event.get("workflow") or "unknown")
        row = workflows.setdefault(
            name,
            {"runs": 0, "statuses": Counter(), "retries": [], "escalations": 0, "reclassifications": 0, "exceptions": 0},
        )
        row["runs"] = int(row["runs"]) + 1  # type: ignore[call-overload]
        status = str(event.get("status", "")).upper()
        bucket = "PASS" if status in PASS_ALIASES else status if status in TERMINAL else "OTHER"
        row["statuses"][bucket] += 1  # type: ignore[index]
        row["retries"].append(_number(event.get("retries")))  # type: ignore[union-attr]
        row["escalations"] = int(row["escalations"]) + _number(event.get("escalations"))  # type: ignore[call-overload]
        row["reclassifications"] = int(row["reclassifications"]) + _number(event.get("reclassifications"))  # type: ignore[call-overload]
        review = event.get("review")
        if isinstance(review, dict) and review.get("exception"):
            row["exceptions"] = int(row["exceptions"]) + 1  # type: ignore[call-overload]
        if isinstance(event.get("workers"), dict):
            for key, value in event["workers"].items():  # type: ignore[union-attr]
                workers[str(key)] += _number(value)
        level = COMPLEXITY_ALIASES.get(str(event.get("complexity", "")).lower())
        if level:
            complexity[level] += 1
            if level == "trivial" and bucket == "PASS" and not _number(event.get("reclassifications")):
                trivial_clean += 1
        if isinstance(review, dict) and isinstance(review.get("lanes"), dict):
            for lane, stats in review["lanes"].items():  # type: ignore[union-attr]
                if isinstance(stats, dict):
                    total = lanes.setdefault(str(lane), {"raised": 0, "accepted": 0})
                    total["raised"] += _number(stats.get("raised"))
                    total["accepted"] += _number(stats.get("accepted"))
    table = {}
    for name, row in sorted(workflows.items()):
        retries = row["retries"]
        table[name] = {
            "runs": row["runs"],
            "statuses": {key: row["statuses"].get(key, 0) for key in (*TERMINAL, "OTHER")},  # type: ignore[union-attr]
            "avg_retries": round(sum(retries) / len(retries), 1) if retries else 0.0,  # type: ignore[arg-type]
            "max_retries": max(retries) if retries else 0,  # type: ignore[type-var]
            "retries": sum(retries),  # type: ignore[arg-type]
            "escalations": row["escalations"],
            "reclassifications": row["reclassifications"],
            "exceptions": row["exceptions"],
        }
    total_workers = sum(workers.values())
    statuses = Counter()
    for row in table.values():
        statuses.update(row["statuses"])  # type: ignore[arg-type]
    return {
        "events": len(events),
        "workflows": table,
        "statuses": {key: statuses.get(key, 0) for key in (*TERMINAL, "OTHER")},
        "workers": {
            key: {"invocations": value, "share": round(100 * value / total_workers) if total_workers else 0}
            for key, value in workers.most_common()
        },
        "complexity": {level: complexity.get(level, 0) for level in ("trivial", "standard", "complex")},
        "trivial_pass_without_reclassification": trivial_clean,
        "lanes": dict(sorted(lanes.items())),
    }


def render_summary(summary: Mapping[str, object], period: str) -> str:
    if not summary["events"]:
        return (
            "No metrics recorded yet. Metrics are emitted automatically when workflows complete.\n"
            "Run a workflow (e.g., `create-feature`, `fix-bug`) to start collecting data."
        )
    lines = ["## Metrics Summary", "", f"Period: {period}", f"Events: {summary['events']}", "", "### Workflow Usage"]
    lines += ["| Workflow | Runs | PASS | ESCALATE | USER_DECISION | BLOCKED |", "|---|---|---|---|---|---|"]
    for name, row in summary["workflows"].items():  # type: ignore[union-attr]
        counts = row["statuses"]
        lines.append(
            f"| {name} | {row['runs']} | {counts['PASS']} | {counts['ESCALATE']} | {counts['USER_DECISION']} | {counts['BLOCKED']} |"
        )
    lines += ["", "### Retries and Escalations", "| Workflow | Avg Retries | Max Retries | Escalations | Reclassifications |", "|---|---|---|---|---|"]
    for name, row in summary["workflows"].items():  # type: ignore[union-attr]
        lines.append(f"| {name} | {row['avg_retries']} | {row['max_retries']} | {row['escalations']} | {row['reclassifications']} |")
    lines += ["", "### Worker Usage", "| Worker / Tier | Invocations | % |", "|---|---|---|"]
    for name, row in summary["workers"].items():  # type: ignore[union-attr]
        lines.append(f"| {name} | {row['invocations']} | {row['share']}% |")
    if not summary["workers"]:
        lines.append("| none recorded | 0 | 0% |")
    complexity = summary["complexity"]
    trivial = complexity["trivial"]  # type: ignore[index]
    accuracy = round(100 * int(summary["trivial_pass_without_reclassification"]) / trivial) if trivial else 0  # type: ignore[call-overload]
    lines += [
        "",
        "### Complexity Gate",
        f"- Trivial workflows: {trivial} ({round(100 * trivial / int(summary['events']))}% of total)",  # type: ignore[call-overload]
        f"- Trivial → PASS without reclassification: {summary['trivial_pass_without_reclassification']} ({accuracy}%)",
    ]
    if int(summary["events"]) < 10:  # type: ignore[call-overload]
        lines += ["", "### Trends", "- Not enough data for trend analysis (need 10+ events)"]
    return "\n".join(lines)


def render_project(summary: Mapping[str, object]) -> str:
    if not summary["events"]:
        return "No metrics recorded for this project"
    statuses = summary["statuses"]
    events = int(summary["events"])  # type: ignore[call-overload]
    retries = sum(int(row["retries"]) for row in summary["workflows"].values())  # type: ignore[union-attr]
    escalations = sum(int(row["escalations"]) for row in summary["workflows"].values())  # type: ignore[union-attr]
    complexity = summary["complexity"]
    lanes = summary["lanes"]
    yield_line = ", ".join(f"{lane} {stats['accepted']}/{stats['raised']}" for lane, stats in lanes.items()) or "none recorded"  # type: ignore[union-attr]
    workers = ", ".join(f"{name}: {row['invocations']}" for name, row in summary["workers"].items()) or "none recorded"  # type: ignore[union-attr]
    lines = [
        "## Project Metrics Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total commands run | {events} |",
        f"| Pass rate (`PASS`) | {round(100 * statuses['PASS'] / events)}% |",  # type: ignore[index]
        f"| Escalated / user decisions / blocked | {statuses['ESCALATE']} / {statuses['USER_DECISION']} / {statuses['BLOCKED']} |",  # type: ignore[index]
        f"| Gate retries / escalations | {retries} / {escalations} |",
        f"| Complexity distribution | {complexity['trivial']} trivial / {complexity['standard']} standard / {complexity['complex']} complex |",  # type: ignore[index]
        f"| Review yield (accepted / raised per lane) | {yield_line} |",
        f"| Worker usage | {workers} |",
        "",
        "### Command Breakdown",
        "| Command | Runs | PASS | ESCALATE | BLOCKED |",
        "|---------|------|------|----------|---------|",
    ]
    for name, row in summary["workflows"].items():  # type: ignore[union-attr]
        counts = row["statuses"]
        lines.append(f"| {name} | {row['runs']} | {counts['PASS']} | {counts['ESCALATE']} | {counts['BLOCKED']} |")
    return "\n".join(lines)
