#!/usr/bin/env python3
"""Aggregate token usage and estimated costs from local session JSONL files."""

import json
import os
import sys
import glob
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

from aitk.pricing import compute_cost, get_pricing

# Per-model global API-equivalent pricing ($/MTok). Keep unknown models
# unpriced. Sources verified 2026-07-15:
# https://www.anthropic.com/claude/opus
# https://www.anthropic.com/news/claude-sonnet-5
# Anthropic List Prices 2026-05-27 (Sonnet 4.6 and Haiku 4.5).
# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def parse_sessions(base_dir, since=None):
    """Parse all session JSONL files, return per-session aggregated data."""
    sessions = []
    for proj_dir in os.listdir(base_dir):
        proj_path = os.path.join(base_dir, proj_dir)
        if not os.path.isdir(proj_path):
            continue
        for jsonl_path in glob.glob(os.path.join(proj_path, "*.jsonl")):
            # Skip subagent logs
            if "/subagents/" in jsonl_path:
                continue
            try:
                session = parse_one_session(jsonl_path, proj_dir, since)
                if session and session["messages"] > 0:
                    sessions.append(session)
            except Exception:
                pass
    return sessions


def parse_one_session(path, project, since):
    """Parse a single session JSONL file."""
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

    with open(path) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_str = obj.get("timestamp", "")
            if not session_id:
                session_id = obj.get("sessionId")

            msg = obj.get("message", {})
            if not isinstance(msg, dict) or "usage" not in msg:
                continue

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


def main():
    period = "7d"
    if len(sys.argv) > 1:
        period = sys.argv[1]

    base_dir = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(base_dir):
        print("No Claude Code session data found at ~/.claude/projects/")
        sys.exit(1)

    # Compute date ranges
    today = datetime.now().date()
    if period == "today":
        since = today.isoformat()
    elif period.endswith("d"):
        days = int(period[:-1])
        since = (today - timedelta(days=days)).isoformat()
    elif period == "month":
        since = today.replace(day=1).isoformat()
    elif period == "all":
        since = None
    else:
        # Try as YYYY-MM-DD
        since = period

    print(f"{DIM}Scanning session files...{RESET}")
    sessions = parse_sessions(base_dir, since)

    if not sessions:
        print(f"No session data found for period: {period}")
        sys.exit(0)

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


if __name__ == "__main__":
    main()
