#!/usr/bin/env python3
"""Analyze local agent usage patterns and produce cost optimization insights."""

import json
import os
import sys
import glob
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

from aitk.pricing import compute_cost, get_pricing
from aitk.workflows import load_workflows

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_NAMES = tuple(
    sorted(
        (workflow.name for workflow in load_workflows(ROOT, include_pgm=True)),
        key=len,
        reverse=True,
    )
)


def format_cost(c):
    if c >= 100:
        return f"${c:,.0f}"
    if c >= 1:
        return f"${c:.2f}"
    return f"${c:.3f}"


def shorten_project(name):
    encoded_home = "-" + "-".join(Path.home().parts[1:])
    if name == encoded_home:
        name = "~"
    elif name.startswith(encoded_home + "-"):
        name = name[len(encoded_home) + 1 :]
    if len(name) > 40:
        name = name[:37] + "..."
    return name or "~"


def extract_commands(text):
    """Extract canonical or deprecated explicit workflow invocations."""
    if not isinstance(text, str):
        return []
    names = "|".join(re.escape(name) for name in WORKFLOW_NAMES)
    return re.findall(rf"(?:/|\$(?:workflows|pgm)\s+)({names})\b", text)


def parse_all_sessions(base_dir, since=None):
    """Parse all sessions with detailed per-message data."""
    sessions = []
    for proj_dir in os.listdir(base_dir):
        proj_path = os.path.join(base_dir, proj_dir)
        if not os.path.isdir(proj_path):
            continue
        for jsonl_path in glob.glob(os.path.join(proj_path, "*.jsonl")):
            if "/subagents/" in jsonl_path:
                continue
            try:
                session = parse_session_detailed(jsonl_path, proj_dir, since)
                if session and session["message_count"] > 0:
                    sessions.append(session)
            except Exception:
                pass

        # Also check for subagent costs
        for jsonl_path in glob.glob(os.path.join(proj_path, "*/subagents/*.jsonl")):
            try:
                sa = parse_session_detailed(jsonl_path, proj_dir, since)
                if sa and sa["message_count"] > 0:
                    sa["is_subagent"] = True
                    sessions.append(sa)
            except Exception:
                pass

    return sessions


def parse_session_detailed(path, project, since):
    """Parse one session JSONL with per-message detail."""
    commands_used = []
    models_used = defaultdict(
        lambda: {
            "cost": 0.0,
            "output_cost": 0.0,
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "count": 0,
            "unpriced": 0,
            "sonnet_equivalent_cost": 0.0,
        }
    )
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
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

            ts = obj.get("timestamp", "")
            date = ts[:10] if ts else None
            if date and since and date < since:
                continue

            if not session_id:
                session_id = obj.get("sessionId")

            # Track explicit workflow invocations from user messages
            if obj.get("type") == "user":
                msg = obj.get("message", {})
                content = msg.get("content", "") if isinstance(msg, dict) else ""
                if isinstance(content, str):
                    cmds = extract_commands(content)
                    commands_used.extend(cmds)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            cmds = extract_commands(block.get("text", ""))
                            commands_used.extend(cmds)

            # Track costs from assistant messages
            msg = obj.get("message", {})
            if not isinstance(msg, dict) or "usage" not in msg:
                continue

            if ts:
                if not first_ts or ts < first_ts:
                    first_ts = ts
                if not last_ts or ts > last_ts:
                    last_ts = ts

            model = msg.get("model", "unknown")
            usage = msg["usage"]
            pricing = get_pricing(model, ts, require_timestamp=True)
            cost = compute_cost(usage, model, ts)
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cr = usage.get("cache_read_input_tokens", 0)
            cc = usage.get("cache_creation_input_tokens", 0)

            total_cost += cost
            total_input += inp
            total_output += out
            total_cache_read += cr
            total_cache_create += cc
            message_count += 1

            models_used[model]["cost"] += cost
            if pricing is not None:
                models_used[model]["output_cost"] += out * pricing["output"] / 1_000_000
            models_used[model]["input"] += inp + cr + cc
            models_used[model]["output"] += out
            models_used[model]["cache_read"] += cr
            models_used[model]["count"] += 1
            models_used[model]["unpriced"] += int(pricing is None)
            models_used[model]["sonnet_equivalent_cost"] += compute_cost(
                usage, "claude-sonnet-5", ts
            )

    if message_count == 0:
        return None

    total_all_input = total_input + total_cache_read + total_cache_create
    cache_rate = (
        (total_cache_read / total_all_input * 100) if total_all_input > 0 else 0
    )

    # Estimate duration
    duration_min = 0
    if first_ts and last_ts:
        try:
            t1 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration_min = (t2 - t1).total_seconds() / 60
        except Exception:
            pass

    return {
        "session_id": session_id,
        "project": project,
        "path": path,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "date": (first_ts[:10] if first_ts else "unknown"),
        "total_cost": total_cost,
        "total_input": total_all_input,
        "total_output": total_output,
        "cache_read": total_cache_read,
        "cache_rate": cache_rate,
        "message_count": message_count,
        "duration_min": duration_min,
        "models": dict(models_used),
        "commands": commands_used,
        "is_subagent": False,
    }


def analyze(sessions):
    """Run all analysis passes and return findings."""
    findings = []

    if not sessions:
        return ["No session data found."]

    main_sessions = [s for s in sessions if not s.get("is_subagent")]
    total_cost = sum(s["total_cost"] for s in main_sessions)
    # 1. Model concentration
    model_costs = defaultdict(float)
    for s in main_sessions:
        for model, data in s["models"].items():
            model_costs[model] += data["cost"]

    opus_cost = sum(v for k, v in model_costs.items() if "opus" in k)
    opus_sonnet_equivalent = sum(
        data["sonnet_equivalent_cost"]
        for session in main_sessions
        for model, data in session["models"].items()
        if "opus" in model
    )
    opus_pct = (opus_cost / total_cost * 100) if total_cost > 0 else 0
    if opus_pct > 90:
        savings = max(0.0, opus_cost - opus_sonnet_equivalent)
        findings.append(
            {
                "severity": "high",
                "title": "100% Opus usage — no model tiering",
                "detail": (
                    f"All {format_cost(total_cost)} is on Opus. If 60% of subagent work "
                    f"moved to Sonnet, estimated savings: ~{format_cost(savings * 0.6)}/period."
                ),
                "action": "Apply model tiering per rules/orchestration.md — Sonnet for triage/review, Opus for hard planning only.",
            }
        )

    # 2. Expensive sessions (cost > $8 without checkpoint)
    expensive = [s for s in main_sessions if s["total_cost"] > 8]
    if expensive:
        avg_expensive = sum(s["total_cost"] for s in expensive) / len(expensive)
        total_expensive = sum(s["total_cost"] for s in expensive)
        pct_of_total = (total_expensive / total_cost * 100) if total_cost > 0 else 0
        findings.append(
            {
                "severity": "high",
                "title": f"{len(expensive)} sessions exceeded $8 checkpoint threshold",
                "detail": (
                    f"These {len(expensive)} sessions account for {format_cost(total_expensive)} "
                    f"({pct_of_total:.0f}% of total). Average: {format_cost(avg_expensive)}/session. "
                    f"Top offender: {format_cost(max(s['total_cost'] for s in expensive))}."
                ),
                "action": "Auto-checkpoint at $8 per context-management.md. Each continuation saves ~30-50% vs continuing in a bloated session.",
            }
        )

    # 3. Long sessions (>150 messages)
    long_sessions = [s for s in main_sessions if s["message_count"] > 150]
    if long_sessions:
        avg_msgs = sum(s["message_count"] for s in long_sessions) / len(long_sessions)
        findings.append(
            {
                "severity": "medium",
                "title": f"{len(long_sessions)} sessions with >150 messages",
                "detail": (
                    f"Average {avg_msgs:.0f} messages. Long sessions pay quadratic cost — "
                    f"each API call replays the full history."
                ),
                "action": "Checkpoint earlier. Cost-based trigger ($8) catches this automatically.",
            }
        )

    # 4. Cache efficiency
    overall_cache_read = sum(s["cache_read"] for s in main_sessions)
    overall_input = sum(s["total_input"] for s in main_sessions)
    overall_cache_rate = (
        (overall_cache_read / overall_input * 100) if overall_input > 0 else 0
    )

    low_cache = [
        s for s in main_sessions if s["cache_rate"] < 70 and s["message_count"] > 10
    ]
    if low_cache:
        findings.append(
            {
                "severity": "medium",
                "title": f"{len(low_cache)} sessions with <70% cache hit rate",
                "detail": (
                    f"Overall cache rate: {overall_cache_rate:.0f}%. "
                    f"Low-cache sessions waste tokens re-sending context that could be cached."
                ),
                "action": "Short sessions or sessions with rapidly changing context have lower cache rates. "
                "This is partly structural — checkpointing more frequently can help.",
            }
        )
    elif overall_cache_rate > 85:
        findings.append(
            {
                "severity": "good",
                "title": f"Cache hit rate is strong at {overall_cache_rate:.0f}%",
                "detail": "Most input tokens are served from cache, which is 10x cheaper than fresh input.",
                "action": "No action needed. Keep sessions focused to maintain this.",
            }
        )

    # 5. Explicit workflow cost attribution
    cmd_costs = defaultdict(lambda: {"cost": 0.0, "count": 0, "sessions": 0})
    for s in main_sessions:
        seen_cmds = set(s["commands"])
        for cmd in seen_cmds:
            cmd_costs[cmd]["sessions"] += 1
        # Attribute session cost proportionally to commands used
        n_cmds = len(seen_cmds) or 1
        for cmd in seen_cmds:
            cmd_costs[cmd]["cost"] += s["total_cost"] / n_cmds
        for cmd in s["commands"]:
            cmd_costs[cmd]["count"] += 1

    if cmd_costs:
        sorted_cmds = sorted(
            cmd_costs.items(), key=lambda x: x[1]["cost"], reverse=True
        )
        top_cmd = sorted_cmds[0]
        if top_cmd[1]["cost"] > total_cost * 0.3:
            findings.append(
                {
                    "severity": "medium",
                    "title": f"Workflow {top_cmd[0]} accounts for ~{format_cost(top_cmd[1]['cost'])} ({top_cmd[1]['cost']/total_cost*100:.0f}%)",
                    "detail": (
                        f"Used {top_cmd[1]['count']} times across {top_cmd[1]['sessions']} sessions. "
                        f"This is the biggest optimization target."
                    ),
                    "action": f"Review {top_cmd[0]} for model tiering and checkpoint opportunities.",
                }
            )

    # 6. Project hotspots
    proj_costs = defaultdict(lambda: {"cost": 0.0, "sessions": 0})
    for s in main_sessions:
        proj = shorten_project(s["project"])
        proj_costs[proj]["cost"] += s["total_cost"]
        proj_costs[proj]["sessions"] += 1

    sorted_projs = sorted(proj_costs.items(), key=lambda x: x[1]["cost"], reverse=True)
    if sorted_projs and sorted_projs[0][1]["cost"] > total_cost * 0.4:
        top_proj = sorted_projs[0]
        findings.append(
            {
                "severity": "info",
                "title": f"Project '{top_proj[0]}' accounts for {top_proj[1]['cost']/total_cost*100:.0f}% of cost",
                "detail": f"{format_cost(top_proj[1]['cost'])} across {top_proj[1]['sessions']} sessions.",
                "action": "Focus model tiering and checkpoint discipline on this project first for maximum impact.",
            }
        )

    # 7. Output token ratio
    total_output_tokens = sum(s["total_output"] for s in main_sessions)
    output_cost = sum(
        model["output_cost"]
        for session in main_sessions
        for model in session["models"].values()
    )
    output_pct = (output_cost / total_cost * 100) if total_cost > 0 else 0
    if output_pct > 40:
        findings.append(
            {
                "severity": "medium",
                "title": f"Output tokens account for {output_pct:.0f}% of cost",
                "detail": (
                    f"{total_output_tokens/1_000_000:.1f}M output tokens account for "
                    f"{format_cost(output_cost)} at each record's model and timestamp price."
                ),
                "action": "Verbose subagent responses and long explanations drive output cost. "
                "Instruct subagents to return structured data, not prose.",
            }
        )

    # 8. Potential savings summary
    if total_cost > 0:
        # Estimate only the measured Opus-to-Sonnet delta at each record's timestamp.
        tiering_savings = max(0.0, opus_cost - opus_sonnet_equivalent) * 0.6
        # Estimate savings from checkpointing (expensive sessions could save 30%)
        checkpoint_savings = (
            sum(s["total_cost"] * 0.3 for s in expensive) if expensive else 0
        )
        total_savings = tiering_savings + checkpoint_savings

        findings.append(
            {
                "severity": "summary",
                "title": "Estimated savings potential",
                "detail": (
                    f"Model tiering: ~{format_cost(tiering_savings)} "
                    f"({tiering_savings/total_cost*100:.0f}% reduction)\n"
                    f"             Cost-based checkpointing: ~{format_cost(checkpoint_savings)}\n"
                    f"             Combined: ~{format_cost(total_savings)} "
                    f"({total_savings/total_cost*100:.0f}% reduction)"
                ),
                "action": "",
            }
        )

    return findings


def print_findings(findings):
    """Pretty-print analysis findings."""
    severity_icons = {
        "high": f"{RED}!!{RESET}",
        "medium": f"{YELLOW} !{RESET}",
        "good": f"{GREEN} +{RESET}",
        "info": f"{CYAN} i{RESET}",
        "summary": f"{BOLD}=={RESET}",
    }

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}Cost Optimization Analysis{RESET}")
    print(f"{'=' * 60}\n")

    for f in findings:
        icon = severity_icons.get(f["severity"], "  ")
        print(f"  {icon} {BOLD}{f['title']}{RESET}")
        for line in f["detail"].split("\n"):
            print(f"     {line}")
        if f["action"]:
            print(f"     {DIM}Action: {f['action']}{RESET}")
        print()


def main():
    period = "7d"
    if len(sys.argv) > 1:
        period = sys.argv[1]

    base_dir = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(base_dir):
        print("No Claude Code session data found.")
        sys.exit(1)

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
        since = period

    print(f"{DIM}Analyzing usage patterns...{RESET}")
    sessions = parse_all_sessions(base_dir, since)
    findings = analyze(sessions)
    print_findings(findings)


if __name__ == "__main__":
    main()
