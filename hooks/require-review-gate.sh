#!/bin/bash
#
# require-review-gate.sh — provider-neutral PreToolUse hook
#
# Blocks `gh pr create` unless the routing snapshot in the repository's
# PROJECT.md records the `review` gate as PASS for the current phase. That is
# the same check `bin/aitk checkpoint reserve` applies before a published_pr
# effect (`gate_blockers`), so the hook and the workflow runtime cannot
# disagree. A review exception (zero-logic or micro-fix diff) is still a
# recorded review PASS (rules/gates.md), so it needs no separate path.
#
# A pending `published_pr` reservation in the checkpoint also counts: `reserve`
# already required review PASS when it was written, and a multi-phase run
# legitimately advances the phase (clearing the phase-scoped gate) between the
# reservation and the PR.
#
# A missing, unreadable, or malformed PROJECT.md or snapshot, and a missing
# gate, block: the failure this guards is a change that never entered a
# workflow, and failing open there reproduces it. Fail-open only when tooling
# is absent (jq, python3, git, the aitk package) or the directory is not a git
# repository.
#
# Known limits (this is a tripwire against skipping the workflow, not a shell
# sandbox):
#   - The snapshot carries no branch or tree binding, so a review PASS left by
#     an earlier workflow in the same PROJECT.md still satisfies the gate.
#   - Command matching is static: `cd` inside a conditional or subshell is
#     treated as taken, and `gh api` or an alias can open a PR unseen.
#
# Bypass (the user's override for work outside a workflow; the block message
# tells the agent to ask rather than bypass on its own):
#   - Prefix the command:           SKIP_PR_GATE=1 gh pr create ...
#   - Env at Claude Code start:     SKIP_PR_GATE=1
#
# Exit codes:
#   0 — allow
#   2 — block (review gate not PASS; message printed to stderr)
#

set -uo pipefail

# Fail open on any unexpected shell error
trap 'exit 0' ERR

INPUT=$(cat)

command -v jq      >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
command -v git     >/dev/null 2>&1 || exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
CWD=$(echo     "$INPUT" | jq -r '.cwd // empty'                2>/dev/null) || exit 0

[[ -z "$COMMAND" || -z "$CWD" ]] && exit 0
[[ ! -d "$CWD" ]] && exit 0

# Fast-exit unless the command mentions `gh` and `create` or its alias `new`;
# the Python guard below does the precise token match.
case "$COMMAND" in
    *gh*create* | *gh*new*) ;;
    *) exit 0 ;;
esac

case "${SKIP_PR_GATE:-}" in
    "" | 0 | false) ;;
    *) exit 0 ;;
esac

TOOLKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export HOOK_COMMAND="$COMMAND"
export HOOK_CWD="$CWD"
export HOOK_TOOLKIT_ROOT="$TOOLKIT_ROOT"

# From here on the Python guard owns fail-open vs block behavior. Keep exit 2
# intact for intentional blocks; any other Python failure should allow.
trap - ERR
set +e

python3 <<'PY'
import json
import os
import re
import shlex
import subprocess
import sys

command = os.environ.get("HOOK_COMMAND", "")
cwd = os.environ.get("HOOK_CWD", "")
toolkit_root = os.environ.get("HOOK_TOOLKIT_ROOT", "")

SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}"}
SIMPLE_WRAPPERS = {"command", "exec", "nohup", "time"}
DEPTH_LIMIT = 3
GH_VALUE_FLAGS = {"-R", "--repo", "--hostname"}
BYPASS_OFF = {"", "0", "false"}


HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def split_lines(text):
    """Turn each unquoted newline into `;`; drop here-document bodies."""
    out = []
    quote = None
    pending = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'" and index + 1 < len(text):
            out.append(text[index : index + 2])
            index += 2
            continue
        if quote is None and char == "<":
            match = HEREDOC.match(text, index) if not text.startswith("<<<", index) else None
            if match:
                pending.append((match.group(1) == "-", match.group(3)))
                out.append(match.group(0))
                index = match.end()
                continue
        if quote is None and char in "'\"":
            quote = char
        elif quote == char:
            quote = None
        if quote is None and char == "\n":
            out.append(" ; ")
            index += 1
            for strip, delimiter in pending:
                while index < len(text):
                    end = text.find("\n", index)
                    end = len(text) if end < 0 else end
                    line = text[index:end]
                    index = min(end + 1, len(text))
                    if (line.strip() if strip else line) == delimiter:
                        break
            pending = []
            continue
        out.append(char)
        index += 1
    return "".join(out)


def tokenize(text):
    lexer = shlex.shlex(split_lines(text), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def is_assignment(token):
    name, sep, _ = token.partition("=")
    return bool(sep) and name.isidentifier()


def segments(tokens):
    current = []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


WRAPPER_VALUE_FLAGS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-i", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p"},
    "stdbuf": {"-i", "-o", "-e"},
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U"},
}


def skip_options(wrapper, rest):
    valued = WRAPPER_VALUE_FLAGS.get(wrapper, set())
    bypassed = False
    while rest:
        arg = rest[0]
        if is_assignment(arg):
            name, _, value = arg.partition("=")
            bypassed = bypassed or (name == "SKIP_PR_GATE" and value not in BYPASS_OFF)
            rest = rest[1:]
        elif arg.startswith("-") and arg != "-":
            rest = rest[2:] if arg in valued else rest[1:]
        elif wrapper == "timeout" and re.fullmatch(r"\d+(\.\d+)?[smhd]?", arg):
            rest = rest[1:]
        else:
            break
    return rest, bypassed


def strip_prefixes(segment):
    """Drop assignments, keywords, and wrappers; return (rest, bypassed)."""
    bypassed = False
    rest = list(segment)
    while rest:
        head = os.path.basename(rest[0])
        if is_assignment(rest[0]):
            name, _, value = rest[0].partition("=")
            bypassed = bypassed or (name == "SKIP_PR_GATE" and value not in BYPASS_OFF)
            rest = rest[1:]
        elif head in KEYWORDS:
            rest = rest[1:]
        elif head in SIMPLE_WRAPPERS or head in WRAPPER_VALUE_FLAGS:
            rest, skipped = skip_options(head, rest[1:])
            bypassed = bypassed or skipped
        else:
            break
    return rest, bypassed


def is_shell_command_flag(arg):
    return arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]


def gh_creates_pr(args):
    if {"-h", "--help"} & set(args):
        return False
    positional = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in GH_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            positional.append(arg)
    return positional[:2] in (["pr", "create"], ["pr", "new"])


def advance_dir(workdir, args):
    """Follow `cd`/`pushd` so the gate is read from the repo the PR opens in."""
    target = next((arg for arg in args if not arg.startswith("-")), None)
    if target is None or target == "-":
        return workdir
    path = os.path.expanduser(target)
    path = path if os.path.isabs(path) else os.path.join(workdir, path)
    return os.path.normpath(path) if os.path.isdir(path) else workdir


def find_pr_create(text, workdir, depth=0):
    """Return (workdir, bypassed) for the first `gh pr create`, else None."""
    try:
        tokens = tokenize(text)
    except Exception:
        return None
    for segment in segments(tokens):
        rest, bypassed = strip_prefixes(segment)
        if not rest:
            continue
        head = os.path.basename(rest[0])
        if head in {"cd", "pushd"}:
            workdir = advance_dir(workdir, rest[1:])
        elif head == "gh" and gh_creates_pr(rest[1:]):
            return workdir, bypassed
        elif depth < DEPTH_LIMIT and head in SHELLS:
            flags = [i for i, arg in enumerate(rest[1:], 1) if is_shell_command_flag(arg)]
            if flags and flags[0] + 1 < len(rest):
                found = find_pr_create(rest[flags[0] + 1], workdir, depth + 1)
                if found:
                    return found[0], bypassed or found[1]
        elif depth < DEPTH_LIMIT and head == "eval":
            found = find_pr_create(" ".join(rest[1:]), workdir, depth + 1)
            if found:
                return found[0], bypassed or found[1]
    return None


found = find_pr_create(command, cwd)
if found is None or found[1]:
    sys.exit(0)
workdir = found[0]


def git_toplevel(path):
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def block(reason):
    print(
        "BLOCKED: `gh pr create` needs a recorded review gate (rules/gates.md), "
        f"and {reason}.\n"
        "Run the workflow that owns this change (create-feature or fix-bug) or "
        "`review-code` on the branch so the review gate is recorded by the "
        "workflow. Do not bypass this on your own: stop and ask the user, "
        "who alone can override it for a change outside any workflow.",
        file=sys.stderr,
    )
    sys.exit(2)


root = git_toplevel(workdir)
if root is None:
    sys.exit(0)

sys.path.insert(0, toolkit_root)
try:
    from aitk.project_state import gate_blockers, parse_project_state
except Exception:
    sys.exit(0)


def find_project_file(start, stop):
    """Nearest PROJECT.md from the working directory up to the repo root."""
    current = os.path.realpath(start)
    stop = os.path.realpath(stop)
    while True:
        candidate = os.path.join(current, "PROJECT.md")
        if os.path.isfile(candidate):
            return candidate
        if current == stop or os.path.dirname(current) == current:
            return None
        current = os.path.dirname(current)


def pending_publish(content):
    """A pending `published_pr` reservation: `reserve` already required review PASS."""
    match = re.search(
        r"<!-- aitk-checkpoint:v1 -->\n(.*?)\n<!-- /aitk-checkpoint -->", content, re.S
    )
    if match is None:
        return False
    try:
        effects = json.loads(match.group(1)).get("effects", [])
    except Exception:
        return False
    return any(
        isinstance(effect, dict)
        and effect.get("key") == "published_pr"
        and effect.get("status") == "pending"
        for effect in effects
    )


project_file = find_project_file(workdir, root)
if project_file is None:
    block("no PROJECT.md exists in the repository, so no workflow ran")

try:
    with open(project_file, encoding="utf-8") as handle:
        content = handle.read()
except OSError as error:
    block(f"PROJECT.md could not be read ({error.strerror or error})")

try:
    snapshot = parse_project_state(content)
except Exception as error:
    block(f"the routing snapshot in PROJECT.md is unreadable ({error})")

if snapshot is None:
    block("PROJECT.md has no routing snapshot, so no workflow classified this change")

try:
    blockers = gate_blockers(snapshot, ["review"])
except Exception as error:
    block(f"the review gate record in PROJECT.md is unreadable ({error})")

if blockers:
    # A reservation stands in for a review PASS that `advance` cleared. It never
    # overrides a gate recorded non-PASS in the current phase (e.g. a later RETRY).
    recorded = snapshot["gates"].get("review")
    explicit_non_pass = (
        recorded is not None
        and recorded["phase"] == snapshot["current_phase"]
        and recorded["status"] != "PASS"
    )
    if explicit_non_pass or not pending_publish(content):
        block("the snapshot does not show it passing: " + "; ".join(blockers))

sys.exit(0)
PY
