"""Per-workflow token accounting from Claude Code session transcripts.

`aitk usage` (see `aitk.usage`) answers "how much did each session cost?".
This module answers the v2 spec's §14 question -- "how much does each
*workflow* cost, and what does it buy?" -- by attributing every priced
transcript line to the skill that was active when it was written.

Attribution key
---------------
Claude Code records each skill invocation as a structured `tool_use` block
named `Skill` (`{"name": "Skill", "input": {"skill": "<name>", ...}}`) inside
an `assistant` record that also carries `cwd`, `sessionId`, and `timestamp`.
That block is a deterministic marker, not a content heuristic: a session's
skill timeline is the ordered list of those blocks, and a priced line belongs
to the most recent `Skill` invocation in the same session whose timestamp is
at or before the line's own. Lines written before the first invocation (or
without a parseable timestamp) are reported under `UNATTRIBUTED` rather than
guessed at.

Subagent transcripts (`<session>/subagents/agent-*.jsonl`) carry the parent
`sessionId`, so a worker dispatched by a workflow is charged to that
workflow by the same timestamp rule. The `Skill` call's own turn -- the one
that decided to invoke the skill -- is charged to the skill too (its
timestamp equals the invocation's), which is the accounting the spec wants:
the cost of running a workflow includes the turn that routed into it.

Context size
------------
Each priced line's *prompt* size is `input_tokens + cache_creation_input_tokens
+ cache_read_input_tokens` -- the context the model actually read on that
call. The report keeps the per-workflow peak, which is the number the spec's
"context growth" hypothesis is about; a summed total would double-count the
cached prefix on every turn.

Metrics join
------------
Workflows that emit telemetry (`skills/metrics-emit`) write
`workflow-summary` events into `<cwd>/.ai-toolkit/metrics.jsonl`, keyed by
`command`. For every `cwd` the transcripts mention, those events are folded
into the matching workflow row by name: run count, summed `retries` and
`reclassifications`, and mean `reviewer_yield` over the runs that reported
one. A workflow that has summaries but no attributable transcript tokens (a
run on another machine, say) still gets a row so the two data sources can be
compared side by side.

This module is read-only, imports nothing from `aitk.cli`, and -- like
`aitk.usage` -- is filesystem-scoped to the `projects_root` it is handed, so
it is directly testable against a `tmp_path` fixture.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from .pricing import compute_cost, parse_record_time
from .usage import _is_premium, _token_total

UNATTRIBUTED = "(unattributed)"
METRICS_RELPATH = Path(".ai-toolkit") / "metrics.jsonl"


@dataclass(frozen=True)
class WorkflowUsage:
    """Aggregated spend and yield for one workflow (skill) name."""

    workflow: str
    invocations: int
    sessions: int
    total_tokens: int
    premium_tokens: int
    cost: float
    peak_context_tokens: int
    summaries: int
    retries: int
    reclassifications: int
    reviewer_yield: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "invocations": self.invocations,
            "sessions": self.sessions,
            "total_tokens": self.total_tokens,
            "premium_tokens": self.premium_tokens,
            "cost": self.cost,
            "peak_context_tokens": self.peak_context_tokens,
            "summaries": self.summaries,
            "retries": self.retries,
            "reclassifications": self.reclassifications,
            "reviewer_yield": self.reviewer_yield,
        }


@dataclass(frozen=True)
class WorkflowReport:
    workflows: tuple[WorkflowUsage, ...]
    total_tokens: int
    premium_tokens: int
    cost: float

    def as_dict(self) -> dict[str, object]:
        return {
            "workflows": [workflow.as_dict() for workflow in self.workflows],
            "total_tokens": self.total_tokens,
            "premium_tokens": self.premium_tokens,
            "cost": self.cost,
        }


@dataclass(frozen=True)
class _PricedLine:
    session_id: str
    cwd: str
    when: datetime | None
    tokens: int
    premium: bool
    context: int
    cost: float


@dataclass(frozen=True)
class _Timeline:
    """One session's Skill invocations, sorted, split for bisecting."""

    stamps: list[datetime]
    skills: list[str]


class _Tally:
    __slots__ = (
        "invocations",
        "sessions",
        "total_tokens",
        "premium_tokens",
        "cost",
        "peak_context",
        "summaries",
        "retries",
        "reclassifications",
        "yield_sum",
        "yield_count",
    )

    def __init__(self) -> None:
        self.invocations = 0
        self.sessions: set[str] = set()
        self.total_tokens = 0
        self.premium_tokens = 0
        self.cost = 0.0
        self.peak_context = 0
        self.summaries = 0
        self.retries = 0
        self.reclassifications = 0
        self.yield_sum = 0.0
        self.yield_count = 0

    def freeze(self, name: str) -> WorkflowUsage:
        return WorkflowUsage(
            workflow=name,
            invocations=self.invocations,
            sessions=len(self.sessions),
            total_tokens=self.total_tokens,
            premium_tokens=self.premium_tokens,
            cost=self.cost,
            peak_context_tokens=self.peak_context,
            summaries=self.summaries,
            retries=self.retries,
            reclassifications=self.reclassifications,
            reviewer_yield=(
                self.yield_sum / self.yield_count if self.yield_count else None
            ),
        )


def collect_workflow_usage(
    projects_root: Path,
    selectors: tuple[str, ...] = (),
    *,
    since: datetime | None = None,
    metrics_relpath: Path = METRICS_RELPATH,
) -> WorkflowReport:
    """Attribute priced transcript lines under `projects_root` to workflows.

    `selectors` and `since` mean what they mean for `aitk.usage.collect_usage`.
    `metrics_relpath` is where each session `cwd` keeps its telemetry file;
    the default is the path `skills/metrics-emit` writes to.
    """
    starts: dict[str, list[tuple[datetime, str]]] = {}
    lines: list[_PricedLine] = []
    if projects_root.is_dir():
        for path in sorted(projects_root.glob("**/*.jsonl")):
            _scan_file(path, selectors, since, starts, lines)

    timelines: dict[str, _Timeline] = {}
    tallies: dict[str, _Tally] = {}
    for session_id, entries in starts.items():
        entries.sort()
        timelines[session_id] = _Timeline(
            stamps=[when for when, _ in entries], skills=[skill for _, skill in entries]
        )
        for _, skill in entries:
            tally = tallies.setdefault(skill, _Tally())
            tally.invocations += 1
            tally.sessions.add(session_id)

    cwds: set[str] = set()
    for line in lines:
        cwds.add(line.cwd)
        name = _attribute(line, timelines.get(line.session_id))
        tally = tallies.setdefault(name, _Tally())
        tally.sessions.add(line.session_id)
        tally.total_tokens += line.tokens
        if line.premium:
            tally.premium_tokens += line.tokens
        tally.cost += line.cost
        tally.peak_context = max(tally.peak_context, line.context)

    for cwd in sorted(cwds):
        _join_metrics(Path(cwd) / metrics_relpath, since, tallies)

    workflows = tuple(
        tally.freeze(name)
        for name, tally in sorted(
            tallies.items(), key=lambda item: (-item[1].total_tokens, item[0])
        )
    )
    return WorkflowReport(
        workflows=workflows,
        total_tokens=sum(workflow.total_tokens for workflow in workflows),
        premium_tokens=sum(workflow.premium_tokens for workflow in workflows),
        cost=sum(workflow.cost for workflow in workflows),
    )


def _attribute(line: _PricedLine, timeline: _Timeline | None) -> str:
    if line.when is None or timeline is None:
        return UNATTRIBUTED
    # bisect_right: a priced line stamped exactly at an invocation belongs to
    # that invocation, not to its predecessor.
    index = bisect_right(timeline.stamps, line.when)
    if index == 0:
        return UNATTRIBUTED
    return timeline.skills[index - 1]


def _scan_file(
    path: Path,
    selectors: tuple[str, ...],
    since: datetime | None,
    starts: dict[str, list[tuple[datetime, str]]],
    lines: list[_PricedLine],
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        cwd = record.get("cwd")
        session_id = record.get("sessionId")
        message = record.get("message")
        if not isinstance(cwd, str) or not isinstance(session_id, str):
            continue
        if not isinstance(message, dict):
            continue
        when = parse_record_time(record.get("timestamp"))
        if since is not None and when is not None and when < since:
            continue
        if when is not None:
            for skill in _skill_invocations(message.get("content")):
                starts.setdefault(session_id, []).append((when, skill))
        usage = message.get("usage")
        model = message.get("model")
        if not isinstance(usage, dict) or not isinstance(model, str):
            continue
        lines.append(
            _PricedLine(
                session_id=session_id,
                cwd=cwd,
                when=when,
                tokens=_token_total(usage),
                premium=_is_premium(model, selectors),
                context=_context_size(usage),
                cost=compute_cost(usage, model, record.get("timestamp")),
            )
        )


def _skill_invocations(content: object) -> list[str]:
    if not isinstance(content, list):
        return []
    names: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != "Skill":
            continue
        payload = block.get("input")
        if not isinstance(payload, dict):
            continue
        skill = payload.get("skill")
        if isinstance(skill, str) and skill.strip():
            names.append(skill.strip().lstrip("/"))
    return names


def _context_size(usage: dict[str, object]) -> int:
    return (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
        + int(usage.get("cache_read_input_tokens", 0) or 0)
    )


def _join_metrics(
    path: Path, since: datetime | None, tallies: dict[str, _Tally]
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("event") != "workflow-summary":
            continue
        command = event.get("command")
        if not isinstance(command, str) or not command:
            continue
        if since is not None:
            when = parse_record_time(event.get("timestamp"))
            if when is not None and when < since:
                continue
        tally = tallies.setdefault(command, _Tally())
        tally.summaries += 1
        tally.retries += _as_int(event.get("retries"))
        tally.reclassifications += _as_int(event.get("reclassifications"))
        reviewer_yield = event.get("reviewer_yield")
        if isinstance(reviewer_yield, (int, float)) and not isinstance(
            reviewer_yield, bool
        ):
            tally.yield_sum += float(reviewer_yield)
            tally.yield_count += 1


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)
