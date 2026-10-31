#!/usr/bin/env python3
"""Token usage and estimated cost from local Claude Code sessions.

Usage: python3 scripts/show-cost.py [today|<N>d|month|all|YYYY-MM-DD]   (default 7d)

Reads Claude Code transcripts under `~/.claude/projects/`, subagent
transcripts included and repeated usage records counted once. Codex keeps no
equivalent usage records, so the report is Claude-only. A model without a
known price, or a promotional model without a valid record timestamp, stays
unpriced rather than guessed. Costs are API-equivalent estimates.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as calendar_date, datetime, timedelta, timezone
import glob
import json
import os
from pathlib import Path
import re
import sys

# Pricing, per million tokens. Claude rates are from
# platform.claude.com/docs/en/about-claude/pricing and OpenAI rates from
# developers.openai.com/api/docs/pricing, both checked 2026-10-10.

PRICING = {
    # OpenAI selectors as Codex CLI names them. The usage records carry
    # Anthropic-style cache keys, so the same four fields apply; OpenAI lists
    # cache writes at 1.25x input.
    "gpt-6.1-sol": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.10,
        "cache_create": 2.50,
    },
    "gpt-6-astra": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 1.00,
        "cache_create": 12.50,
    },
    "gpt-6-luna": {
        "input": 0.10,
        "output": 0.50,
        "cache_read": 0.01,
        "cache_create": 0.125,
    },
    # Superseded by gpt-6.1-sol; kept so older session records still price.
    # Published rates, developers.openai.com/api/docs/models/gpt-6-sol (2026-09-25).
    "gpt-6-sol": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.20,
        "cache_create": 2.50,
    },
    # Superseded by gpt-6-sol; kept so older session records still price.
    # Promotional through 2026-11-21 (see SOL_STANDARD_FROM below); the standard
    # rate returns after that date.
    "gpt-5.6-sol": {
        "input": 4.00,
        "output": 20.00,
        "cache_read": 0.40,
        "cache_create": 5.00,
    },
    # Fable 5.1 cache reads bill at 0.025x input.
    "claude-fable-5-1": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 0.25,
        "cache_create": 12.50,
    },
    "claude-fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 1.00,
        "cache_create": 12.50,
    },
    # Opus 5.5 and Sonnet 5.5 cache reads bill at 0.05x input, not the usual 0.1x.
    "claude-opus-5-5": {
        "input": 4.00,
        "output": 20.00,
        "cache_read": 0.20,
        "cache_create": 5.00,
    },
    "claude-sonnet-5-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.10,
        "cache_create": 2.50,
    },
    # Haiku 5.5 rates for prompts up to 100K tokens; HAIKU_5_5_LONG_PROMPT
    # below applies above that.
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_read": 0.01,
        "cache_create": 0.125,
    },
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "claude-opus-4-8": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.20,
        "cache_create": 2.50,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_create": 1.25,
    },
    "claude-opus-4-6": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
}
# Anthropic announced $3/$15 for Sonnet 5 from 2026-09-01, then kept $2/$10 as
# the standard price; records on either side of that date bill the same.
SONNET_5_STANDARD_PRICING = dict(PRICING["claude-sonnet-5"])
SONNET_5_STANDARD_FROM = datetime(2026, 9, 1, tzinfo=timezone.utc)
# The Sol promotional rate (20% off input, 33% off output) was announced as
# lasting at least through 2026-11-21; records after that date bill at the
# pre-promotion standard rate. Cached input is the usual 10% of input.
SOL_STANDARD_PRICING = {
    "input": 5.00,
    "output": 30.00,
    "cache_read": 0.50,
    "cache_create": 6.25,
}
SOL_STANDARD_FROM = datetime(2026, 11, 22, tzinfo=timezone.utc)
PROMOTIONS = (
    ("claude-sonnet-5", SONNET_5_STANDARD_FROM, SONNET_5_STANDARD_PRICING),
    ("gpt-5.6-sol", SOL_STANDARD_FROM, SOL_STANDARD_PRICING),
)

# Haiku 5.5 bills a request whose prompt (input plus cache reads and writes)
# is over 100K tokens at these rates, for the whole request.
HAIKU_5_5_PROMPT_LIMIT = 100_000
HAIKU_5_5_LONG_PROMPT = {
    "input": 0.50,
    "output": 2.50,
    "cache_read": 0.05,
    "cache_create": 0.625,
}
# GPT-6 family: a prompt over 272K input tokens bills 2x input and cache and
# 1.5x output for the full request.
GPT_6_PROMPT_LIMIT = 272_000
GPT_6_LONG_INPUT_FACTOR = 2.0
GPT_6_LONG_OUTPUT_FACTOR = 1.5
_GPT_6_FAMILY = re.compile(r"gpt-6(?:\.\d+)?-")


def parse_record_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_selector(model: str, selector: str) -> bool:
    """The selector itself or its dated `-YYYYMMDD` form, never a longer name."""
    return model == selector or re.fullmatch(re.escape(selector) + r"-\d{8}", model) is not None


def _long_prompt(model: str, base: dict[str, float], prompt_tokens: int | None) -> dict[str, float]:
    if prompt_tokens is None:
        return base
    if _is_selector(model, "claude-haiku-5-5") and prompt_tokens > HAIKU_5_5_PROMPT_LIMIT:
        return dict(HAIKU_5_5_LONG_PROMPT)
    if _GPT_6_FAMILY.match(model) and prompt_tokens > GPT_6_PROMPT_LIMIT:
        return {
            "input": base["input"] * GPT_6_LONG_INPUT_FACTOR,
            "output": base["output"] * GPT_6_LONG_OUTPUT_FACTOR,
            "cache_read": base["cache_read"] * GPT_6_LONG_INPUT_FACTOR,
            "cache_create": base["cache_create"] * GPT_6_LONG_INPUT_FACTOR,
        }
    return base


def get_pricing(
    model: str,
    timestamp: object = None,
    *,
    require_timestamp: bool = False,
    prompt_tokens: int | None = None,
) -> dict[str, float] | None:
    """Return pricing; promotional models use the record's absolute time.

    A promotion applies only to its exact selector (or the dated form), so a
    newer model whose name extends an older one never inherits its schedule.
    `prompt_tokens` selects the long-prompt tier where a model has one.
    """
    for selector, standard_from, standard in PROMOTIONS:
        if _is_selector(model, selector):
            when = parse_record_time(timestamp)
            if when is None:
                if require_timestamp:
                    return None
                when = datetime.now(timezone.utc)
            if when >= standard_from:
                return dict(standard)
            return dict(PRICING[selector])
    base = PRICING.get(model)
    if base is None:
        for key in sorted(PRICING, key=len, reverse=True):
            if model.startswith(key):
                base = PRICING[key]
                break
    if base is None:
        return None
    return _long_prompt(model, dict(base), prompt_tokens)


def compute_cost(
    usage: dict[str, object],
    model: str,
    timestamp: object = None,
) -> float:
    input_tokens = int(usage.get("input_tokens", 0))
    cache_read = int(usage.get("cache_read_input_tokens", 0))
    cache_create = int(usage.get("cache_creation_input_tokens", 0))
    pricing = get_pricing(
        model,
        timestamp,
        require_timestamp=True,
        prompt_tokens=input_tokens + cache_read + cache_create,
    )
    if pricing is None:
        return 0.0
    return (
        input_tokens * pricing["input"] / 1_000_000
        + int(usage.get("output_tokens", 0)) * pricing["output"] / 1_000_000
        + cache_read * pricing["cache_read"] / 1_000_000
        + cache_create * pricing["cache_create"] / 1_000_000
    )


# Session parsing and the report
# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def session_files(proj_path):
    """Group a project's transcripts by session: the session file first, then
    its subagent transcripts (`<session-id>/subagents/*.jsonl`)."""
    groups = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(proj_path, "*.jsonl"))):
        groups[Path(path).stem].append(path)
    for path in sorted(glob.glob(os.path.join(proj_path, "*", "subagents", "*.jsonl"))):
        groups[Path(path).parent.parent.name].append(path)
    return groups


def parse_sessions(base_dir, since=None):
    """Parse all session JSONL files, return per-session aggregated data.

    Subagent transcripts count toward their parent session. A usage record
    repeated under the same `(message.id, requestId)`, in one file or across
    files, is counted once.
    """
    sessions = []
    seen = set()
    for proj_dir in sorted(os.listdir(base_dir)):
        proj_path = os.path.join(base_dir, proj_dir)
        if not os.path.isdir(proj_path):
            continue
        for paths in session_files(proj_path).values():
            try:
                session = parse_one_session(
                    paths[0], proj_dir, since, seen=seen, extra_paths=paths[1:]
                )
                if session and session["messages"] > 0:
                    sessions.append(session)
            except Exception:
                pass
    return sessions


def usage_key(obj, msg):
    """Identity of one API response: `(message.id, requestId)`, or None."""
    key = (msg.get("id"), obj.get("requestId"))
    return None if key == (None, None) else key


def iter_records(paths):
    for path in paths:
        with open(path) as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def parse_one_session(path, project, since, seen=None, extra_paths=()):
    """Parse one session JSONL file plus any extra (subagent) files.

    `seen` holds the usage keys already counted; pass one set across calls to
    deduplicate across sessions.
    """
    if seen is None:
        seen = set()
    totals = defaultdict(
        lambda: {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_create": 0,
            "cost": 0.0,
            "messages": 0,
            "unpriced": 0,
        }
    )
    dates = set()
    first_ts = None
    last_ts = None
    session_id = None
    message_count = 0

    for obj in iter_records([path, *extra_paths]):
        if not isinstance(obj, dict):
            continue
        ts_str = obj.get("timestamp", "")
        if not session_id:
            session_id = obj.get("sessionId")

        msg = obj.get("message", {})
        if not isinstance(msg, dict) or "usage" not in msg:
            continue

        # One API response can be written as several records (one per content
        # block), each repeating the same usage; count it once.
        key = usage_key(obj, msg)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)

        # Parse timestamp
        date = ts_str[:10] if ts_str else None
        if date and since and date < since:
            continue

        if date:
            dates.add(date)
        if ts_str:
            if not first_ts or ts_str < first_ts:
                first_ts = ts_str
            if not last_ts or ts_str > last_ts:
                last_ts = ts_str

        model = msg.get("model", "unknown")
        usage = msg["usage"]
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cr = usage.get("cache_read_input_tokens", 0)
        cc = usage.get("cache_creation_input_tokens", 0)
        pricing = get_pricing(model, ts_str, require_timestamp=True)
        cost = compute_cost(usage, model, ts_str)

        totals[model]["input"] += inp
        totals[model]["output"] += out
        totals[model]["cache_read"] += cr
        totals[model]["cache_create"] += cc
        totals[model]["cost"] += cost
        totals[model]["messages"] += 1
        totals[model]["unpriced"] += int(pricing is None)
        message_count += 1

    if message_count == 0:
        return None

    total_cost = sum(t["cost"] for t in totals.values())
    total_input = sum(
        t["input"] + t["cache_read"] + t["cache_create"] for t in totals.values()
    )
    total_output = sum(t["output"] for t in totals.values())
    cache_read_total = sum(t["cache_read"] for t in totals.values())
    cache_create_total = sum(t["cache_create"] for t in totals.values())

    return {
        "session_id": session_id,
        "project": project,
        "path": path,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "dates": sorted(dates),
        "models": dict(totals),
        "total_cost": total_cost,
        "total_input": total_input,
        "total_output": total_output,
        "cache_read": cache_read_total,
        "cache_create": cache_create_total,
        "messages": message_count,
    }


def format_tokens(n):
    """Format token count with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def format_cost(c):
    """Format cost in dollars."""
    if c >= 100:
        return f"${c:,.0f}"
    if c >= 1:
        return f"${c:.2f}"
    return f"${c:.3f}"


def shorten_project(name):
    """Shorten project dir name for display."""
    encoded_home = "-" + "-".join(Path.home().parts[1:])
    if name == encoded_home:
        name = "~"
    elif name.startswith(encoded_home + "-"):
        name = name[len(encoded_home) + 1 :]
    # Collapse common path separators
    name = (
        name.replace("--", "/").replace("-", "/", 2) if name.startswith("opt") else name
    )
    if len(name) > 35:
        name = name[:32] + "..."
    return name or "~"


def aggregate_by_date(sessions):
    """Roll up sessions into per-date aggregates."""
    by_date = defaultdict(
        lambda: {
            "cost": 0.0,
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "messages": 0,
            "sessions": 0,
            "models": defaultdict(lambda: {"cost": 0.0, "messages": 0, "unpriced": 0}),
            "projects": defaultdict(lambda: {"cost": 0.0, "messages": 0}),
        }
    )
    for s in sessions:
        for date in s["dates"]:
            # Approximate: attribute full session to each active date equally
            n_dates = len(s["dates"]) or 1
            frac = 1.0 / n_dates
            d = by_date[date]
            d["cost"] += s["total_cost"] * frac
            d["input"] += int(s["total_input"] * frac)
            d["output"] += int(s["total_output"] * frac)
            d["cache_read"] += int(s["cache_read"] * frac)
            d["messages"] += int(s["messages"] * frac)
            d["sessions"] += 1
            for model, mdata in s["models"].items():
                d["models"][model]["cost"] += mdata["cost"] * frac
                d["models"][model]["messages"] += int(mdata["messages"] * frac)
                d["models"][model]["unpriced"] += int(mdata["unpriced"] * frac)
            proj = shorten_project(s["project"])
            d["projects"][proj]["cost"] += s["total_cost"] * frac
            d["projects"][proj]["messages"] += int(s["messages"] * frac)
    return by_date


def print_period(label, dates_data, show_details=True):
    """Print a period summary."""
    total_cost = sum(d["cost"] for d in dates_data.values())
    total_msgs = sum(d["messages"] for d in dates_data.values())
    total_input = sum(d["input"] for d in dates_data.values())
    total_output = sum(d["output"] for d in dates_data.values())
    total_cache = sum(d["cache_read"] for d in dates_data.values())

    cache_pct = (total_cache / total_input * 100) if total_input > 0 else 0

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}{label}{RESET}")
    print(f"{'=' * 60}")
    print(
        f"  Cost: {CYAN}{format_cost(total_cost)}{RESET}  |  "
        f"Messages: {total_msgs:,}  |  "
        f"In: {format_tokens(total_input)}  Out: {format_tokens(total_output)}"
    )
    print(f"  Cache hit rate: {GREEN}{cache_pct:.0f}%{RESET}")

    if not show_details:
        return

    # Daily breakdown
    print(f"\n  {BOLD}Daily{RESET}")
    print(f"  {'Date':<12} {'Cost':>8} {'Msgs':>6} {'Input':>8} {'Output':>8}")
    print(f"  {'-' * 46}")
    for date in sorted(dates_data.keys()):
        d = dates_data[date]
        cost_color = RED if d["cost"] > 5 else YELLOW if d["cost"] > 2 else ""
        print(
            f"  {date:<12} {cost_color}{format_cost(d['cost']):>8}{RESET} "
            f"{d['messages']:>6} {format_tokens(d['input']):>8} {format_tokens(d['output']):>8}"
        )

    # Model breakdown
    model_totals = defaultdict(lambda: {"cost": 0.0, "messages": 0, "unpriced": 0})
    for d in dates_data.values():
        for model, mdata in d["models"].items():
            model_totals[model]["cost"] += mdata["cost"]
            model_totals[model]["messages"] += mdata["messages"]
            model_totals[model]["unpriced"] += mdata["unpriced"]

    if model_totals:
        print(f"\n  {BOLD}By Model{RESET}")
        print(f"  {'Model':<25} {'Cost':>8} {'Msgs':>6} {'% Cost':>8}")
        print(f"  {'-' * 50}")
        for model in sorted(
            model_totals,
            key=lambda m: (model_totals[m]["cost"], model_totals[m]["messages"]),
            reverse=True,
        ):
            mt = model_totals[model]
            pct = (mt["cost"] / total_cost * 100) if total_cost > 0 else 0
            if mt["unpriced"] == mt["messages"]:
                cost_label = "n/a"
            elif mt["unpriced"]:
                cost_label = format_cost(mt["cost"]) + "*"
            else:
                cost_label = format_cost(mt["cost"])
            print(f"  {model:<25} {cost_label:>8} {mt['messages']:>6} {pct:>7.0f}%")

        if any(value["unpriced"] for value in model_totals.values()):
            print(
                f"  {DIM}n/a or * records lack known pricing or a valid record timestamp; those costs are excluded.{RESET}"
            )

    # Project breakdown (top 5)
    proj_totals = defaultdict(lambda: {"cost": 0.0, "messages": 0})
    for d in dates_data.values():
        for proj, pdata in d["projects"].items():
            proj_totals[proj]["cost"] += pdata["cost"]
            proj_totals[proj]["messages"] += pdata["messages"]

    if proj_totals:
        print(f"\n  {BOLD}By Project (top 5){RESET}")
        print(f"  {'Project':<35} {'Cost':>8} {'Msgs':>6}")
        print(f"  {'-' * 52}")
        sorted_projs = sorted(
            proj_totals, key=lambda p: proj_totals[p]["cost"], reverse=True
        )[:5]
        for proj in sorted_projs:
            pt = proj_totals[proj]
            print(f"  {proj:<35} {format_cost(pt['cost']):>8} {pt['messages']:>6}")


def since_for(period: str, today: calendar_date | None = None) -> str | None:
    """Return the first ISO date a period covers, or None for all time.

    Periods: `today`, `<N>d`, `month`, `all`, or a `YYYY-MM-DD` start date.
    Raises ValueError for anything else.
    """
    today = today or datetime.now().date()
    if period == "today":
        return today.isoformat()
    if period == "month":
        return today.replace(day=1).isoformat()
    if period == "all":
        return None
    if period.endswith("d") and period[:-1].isdigit():
        return (today - timedelta(days=int(period[:-1]))).isoformat()
    return calendar_date.fromisoformat(period).isoformat()


def main(period: str = "7d", base_dir: Path | None = None) -> int:
    base = base_dir or Path.home() / ".claude" / "projects"
    if not base.is_dir():
        print("No Claude Code session data found at ~/.claude/projects/")
        return 1
    try:
        since = since_for(period)
    except ValueError:
        print(f"cost: unknown period {period!r} (today, <N>d, month, all, or YYYY-MM-DD)")
        return 2

    print(f"{DIM}Scanning session files...{RESET}")
    sessions = parse_sessions(str(base), since)

    if not sessions:
        print(f"No session data found for period: {period}")
        return 0

    by_date = aggregate_by_date(sessions)

    # Determine period boundaries
    all_dates = sorted(by_date.keys())
    first = all_dates[0] if all_dates else "?"
    last = all_dates[-1] if all_dates else "?"

    print_period(
        f"Usage: {first} to {last}  ({len(sessions)} sessions, {len(all_dates)} days)",
        by_date,
        show_details=True,
    )

    # Weekly rollup if more than 7 days
    if len(all_dates) > 7:
        print(f"\n{BOLD}Weekly Totals{RESET}")
        print(f"  {'Week':<20} {'Cost':>8} {'Msgs':>6}")
        print(f"  {'-' * 36}")
        week_data = defaultdict(lambda: {"cost": 0.0, "messages": 0})
        for date, d in by_date.items():
            dt = datetime.strptime(date, "%Y-%m-%d").date()
            week_start = (dt - timedelta(days=dt.weekday())).isoformat()
            week_data[week_start]["cost"] += d["cost"]
            week_data[week_start]["messages"] += d["messages"]
        for week in sorted(week_data.keys()):
            w = week_data[week]
            print(f"  {week:<20} {format_cost(w['cost']):>8} {w['messages']:>6}")

    print(
        f"\n{DIM}Note: Costs are API-equivalent estimates, not actual billing.{RESET}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "7d"))
