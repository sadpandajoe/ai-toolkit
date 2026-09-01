"""Token usage aggregation over Claude Code session JSONL transcripts.

Reads `~/.claude/projects/**/*.jsonl` (one JSON object per line, per Claude
Code's on-disk session log format) and sums token usage per `(cwd,
sessionId)` -- i.e. one row per recorded session. That pairing is the
closest real proxy this data offers for "per workflow": raw session JSONL
carries no explicit workflow tag, so a session run from the same working
directory for `fix-bug` versus `create-feature` versus an ad hoc chat is
indistinguishable here. True per-workflow-name correlation would need
`PROJECT.md`'s `workflow` field cross-referenced against session timing,
which is out of scope for this module -- deliberately not attempted, since
any content-based heuristic to guess a workflow name would be fragile.

The glob is recursive (`**/*.jsonl`) so it also picks up
`<project>/<session>/subagents/agent-*.jsonl` files -- subagent transcripts
carry their own top-level `cwd`/`sessionId` fields (verified against real
data), so they group into the same session key as their parent and are not
silently dropped.

Premium classification is only as current as `interfaces/model-routing.json`
and `aitk.pricing.PRICING`: a model that has shipped but isn't yet listed
there (e.g. a newer opus point release, or a fable selector without pricing
data) will report as non-premium and/or cost $0.00 rather than erroring.
That's a manifest-currency problem for the caller to notice, not something
this module can infer.

This module is read-only and does not import `aitk.cli` or any workflow/
metrics-emit machinery; it is a standalone data source for callers (e.g. the
`aitk usage` subcommand) to print or, later, feed elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from .pricing import compute_cost, parse_record_time
from .routing_manifest import load_model_routing


@dataclass(frozen=True)
class SessionUsage:
    """Aggregated token usage for one `(cwd, session_id)` pair."""

    cwd: str
    session_id: str
    total_tokens: int
    premium_tokens: int
    cost: float

    def as_dict(self) -> dict[str, object]:
        return {
            "cwd": self.cwd,
            "session_id": self.session_id,
            "total_tokens": self.total_tokens,
            "premium_tokens": self.premium_tokens,
            "cost": self.cost,
        }


@dataclass(frozen=True)
class UsageReport:
    """Per-session usage rows plus grand totals across every session."""

    sessions: tuple[SessionUsage, ...]
    total_tokens: int
    premium_tokens: int
    cost: float

    def as_dict(self) -> dict[str, object]:
        return {
            "sessions": [session.as_dict() for session in self.sessions],
            "total_tokens": self.total_tokens,
            "premium_tokens": self.premium_tokens,
            "cost": self.cost,
        }


def premium_selectors(root: Path) -> tuple[str, ...]:
    """Return the model selectors that count as "premium" spend.

    Read dynamically from `interfaces/model-routing.json` -- the Claude
    `opus` role selector and the Codex `sol` role selector -- rather than
    hardcoded, so this stays in sync with that file instead of silently
    drifting from it.
    """
    payload = load_model_routing(root)
    providers = payload["providers"]
    opus = providers["claude"]["models"]["opus"]["selector"]
    sol = providers["codex"]["models"]["sol"]["selector"]
    return (opus, sol)


def _is_premium(model: str, selectors: tuple[str, ...]) -> bool:
    return any(
        model == selector or model.startswith(selector) for selector in selectors
    )


def _token_total(usage: dict[str, object]) -> int:
    return (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("output_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
        + int(usage.get("cache_read_input_tokens", 0) or 0)
    )


def default_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def collect_usage(
    projects_root: Path | None = None,
    selectors: tuple[str, ...] = (),
    *,
    since: datetime | None = None,
) -> UsageReport:
    """Aggregate token usage per `(cwd, sessionId)` under `projects_root`.

    Pure and filesystem-scoped to `projects_root` (default
    `~/.claude/projects`, see `default_projects_root`): no dependency on a
    toolkit repository root, so it is directly testable against a `tmp_path`
    fixture. `selectors` is the tuple of model-selector prefixes that count
    as premium (see `premium_selectors`); callers resolve it once from
    `interfaces/model-routing.json` and pass it in here. `since`, when given,
    drops lines whose `timestamp` parses to earlier than it (an unparseable
    or missing timestamp is kept, not dropped, since exclusion should be a
    positive match against the cutoff, not a side effect of missing data).

    A line that fails to parse as JSON, or that lacks `message.usage` /
    `message.model` / top-level `cwd` / `sessionId`, is skipped rather than
    treated as fatal -- JSONL files can carry partial/corrupt trailing lines
    from an interrupted session, and not every line type (e.g. `system`,
    `user`) carries usage at all.
    """
    if projects_root is None:
        projects_root = default_projects_root()
    totals: dict[tuple[str, str], list[float]] = {}
    if projects_root.is_dir():
        for path in sorted(projects_root.glob("**/*.jsonl")):
            _accumulate_file(path, selectors, totals, since)

    sessions = tuple(
        SessionUsage(
            cwd=cwd,
            session_id=session_id,
            total_tokens=int(total_tokens),
            premium_tokens=int(premium_tokens),
            cost=cost,
        )
        for (cwd, session_id), (
            total_tokens,
            premium_tokens,
            cost,
        ) in sorted(totals.items())
    )
    return UsageReport(
        sessions=sessions,
        total_tokens=sum(session.total_tokens for session in sessions),
        premium_tokens=sum(session.premium_tokens for session in sessions),
        cost=sum(session.cost for session in sessions),
    )


def _accumulate_file(
    path: Path,
    selectors: tuple[str, ...],
    totals: dict[tuple[str, str], list[float]],
    since: datetime | None,
) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
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
        usage = message.get("usage")
        model = message.get("model")
        if not isinstance(usage, dict) or not isinstance(model, str):
            continue
        if since is not None:
            when = parse_record_time(record.get("timestamp"))
            if when is not None and when < since:
                continue
        key = (cwd, session_id)
        entry = totals.setdefault(key, [0, 0, 0.0])
        tokens = _token_total(usage)
        entry[0] += tokens
        if _is_premium(model, selectors):
            entry[1] += tokens
        entry[2] += compute_cost(usage, model, record.get("timestamp"))
