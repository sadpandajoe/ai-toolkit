#!/usr/bin/env python3
"""Ask the other model family for an independent, read-only review.

From Claude Code (CLAUDECODE is set) it runs Codex; from anywhere else it runs
Claude. `--via` picks the provider explicitly. The reviewer agent's body
(agents/claude/reviewer.md, without its frontmatter) travels as
system/developer instructions and the diff on stdin, so the worker needs no
file pointers; it may still read the repository, read-only.

Usage:
  skills/review/scripts/second-opinion.py [--base REF] [--via codex|claude]
                                          [--deep] [--brief TEXT] [--dry-run]
                                          [--file FILE | PATH ...]

  --base REF   compare the working tree with the merge base of REF
               (default: origin/HEAD, then main, then master)
  --deep       the deep tier: a larger model at xhigh effort, for security,
               architecture or adversarial passes
  --brief      what the change is for and what to look at hardest
  --dry-run    print the command instead of running it
  --file FILE  review this file instead of a diff, e.g. a PLAN.md, which is
               git-excluded and so never appears in one
  PATH ...     limit the diff to these paths

Exit codes: the provider CLI's own, or 2 for a usage or setup error.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "agents" / "claude" / "reviewer.md"

# Promoting a model is a one-line change here.
MODELS = {
    "codex": {"standard": "gpt-6.1-sol", "deep": "gpt-6-astra"},
    "claude": {"standard": "claude-opus-5-5", "deep": "claude-fable-5-1"},
}
EFFORT = {"standard": "high", "deep": "xhigh"}
CLAUDE_BUDGET_USD = {"standard": "5", "deep": "15"}
GIT_READ_RULES = ("Bash(git log *)", "Bash(git show *)", "Bash(git diff *)", "Bash(git blame *)")


def contract_body(text: str) -> str:
    """The agent file without its frontmatter: the instructions alone."""
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


def default_provider(environ: dict[str, str]) -> str:
    return "codex" if environ.get("CLAUDECODE") else "claude"


def default_base(repo: Path) -> str:
    for ref in ("origin/HEAD", "main", "master"):
        found = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
            capture_output=True,
            text=True,
        )
        if found.returncode == 0:
            return ref
    raise SystemExit("second-opinion: no origin/HEAD, main or master; pass --base REF")


def collect_diff(repo: Path, base: str, paths: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--merge-base", base, "--", *paths],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"second-opinion: git diff failed: {result.stderr.strip()}")
    return result.stdout


def build_prompt(diff: str, base: str, brief: str) -> str:
    parts = [f"Review this change against {base}. It is read-only work: report, do not edit."]
    if brief:
        parts.append(f"Context from the author:\n{brief}")
    parts.append(f"The diff:\n```diff\n{diff}```")
    return "\n\n".join(parts) + "\n"


def build_file_prompt(name: str, text: str, brief: str) -> str:
    parts = [
        f"Review {name} before any code is written: what is wrong, missing or risky in it. "
        "It is read-only work: report, do not edit."
    ]
    if brief:
        parts.append(f"Context from the author:\n{brief}")
    parts.append(f"{name}:\n```\n{text}```")
    return "\n\n".join(parts) + "\n"


def build_command(provider: str, tier: str, repo: Path, contract: str) -> list[str]:
    model = MODELS[provider][tier]
    effort = EFFORT[tier]
    if provider == "codex":
        return [
            "codex",
            "exec",
            "--ephemeral",
            "--strict-config",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable",
            "hooks",
            "--model",
            model,
            "--config",
            f'model_reasoning_effort="{effort}"',
            "--config",
            "mcp_servers={}",
            "--config",
            "project_doc_max_bytes=0",
            # The developer channel adds to Codex's base prompt; `instructions`
            # would replace it. JSON escaping is a valid TOML basic string.
            "--config",
            f"developer_instructions={json.dumps(contract)}",
            "--sandbox",
            "read-only",
            "--cd",
            str(repo),
            "-",
        ]
    return [
        "claude",
        "--print",
        "--no-session-persistence",
        "--safe-mode",
        "--restricted",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers": {}}',
        "--model",
        model,
        "--effort",
        effort,
        "--permission-mode",
        "plan",
        "--permission-prompts",
        "none",
        "--max-budget-usd",
        CLAUDE_BUDGET_USD[tier],
        "--append-system-prompt",
        contract,
        "--disallowedTools",
        "Write",
        "Edit",
        "NotebookEdit",
        "--tools",
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "--allowedTools",
        *GIT_READ_RULES,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent read-only review by the other model family.")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--base")
    parser.add_argument("--via", choices=sorted(MODELS))
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--brief", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file", type=Path)
    args = parser.parse_args(argv)
    if args.file and (args.paths or args.base):
        parser.error("--file reviews one file; it takes no --base or PATH")

    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        print("second-opinion: run it inside a git repository", file=sys.stderr)
        return 2
    repo = Path(top.stdout.strip())
    provider = args.via or default_provider(dict(os.environ))
    tier = "deep" if args.deep else "standard"
    if args.file:
        if not args.file.is_file():
            print(f"second-opinion: {args.file} is not a file", file=sys.stderr)
            return 2
        subject = args.file.name
        prompt = build_file_prompt(subject, args.file.read_text(), args.brief)
    else:
        base = args.base or default_base(repo)
        diff = collect_diff(repo, base, args.paths)
        if not diff.strip():
            print(f"second-opinion: no changes against {base}", file=sys.stderr)
            return 2
        subject = f"diff against {base}"
        prompt = build_prompt(diff, base, args.brief)

    if args.dry_run:
        print(" ".join(build_command(provider, tier, repo, "<reviewer contract>")))
        print(f"# prompt: {len(prompt)} characters on stdin, {subject}")
        return 0
    command = build_command(provider, tier, repo, contract_body(CONTRACT.read_text()))
    if shutil.which(command[0]) is None:
        print(f"second-opinion: the {command[0]} CLI is not on PATH; install it or pass --via", file=sys.stderr)
        return 2
    return subprocess.run(command, input=prompt, text=True, cwd=repo).returncode


if __name__ == "__main__":
    raise SystemExit(main())
