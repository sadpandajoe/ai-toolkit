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
# A command the hook cannot parse, or nests deeper than it follows, counts as a
# PR creation (the fast filter already saw `gh` and `create`), and every PR
# creation in one request is checked against the repository it runs in.
#
# Known limits (this is a tripwire against skipping the workflow, not a shell
# sandbox):
#   - The snapshot carries no branch or tree binding, so a review PASS left by
#     an earlier workflow in the same PROJECT.md still satisfies the gate.
#   - Command matching is static: `cd` inside a conditional or subshell is
#     treated as taken, and `gh api` or an alias can open a PR unseen.
#   - PROJECT.md is looked up from the working directory to the git top level,
#     so a linked worktree does not see the main checkout's PROJECT.md and a PR
#     opened from one is blocked until its own workflow records the gate.
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


HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([^\s'\"<>;|&()\\]+)\2")
WORD_START = " \t\n;&|("


def split_lines(text):
    """Normalize a command for tokenizing.

    Unquoted newlines become `;`, backslash-newline joins lines, comments are
    dropped, and here-document bodies are skipped, including one opened inside
    a `$(...)` within double quotes (`--body "$(cat <<'EOF' ...)"`).
    """
    out = []
    quote = None
    pending = []
    substitutions = 0
    previous = "\n"
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'" and index + 1 < len(text):
            if text[index + 1] != "\n":
                out.append(text[index : index + 2])
                previous = "a"
            index += 2
            continue
        if quote is None and char == "#" and previous in WORD_START:
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if char == "<" and (quote is None or (quote == '"' and substitutions)):
            match = None
            if not text.startswith("<<<", index) and previous in WORD_START:
                match = HEREDOC.match(text, index)
            if match:
                pending.append((match.group(1) == "-", match.group(3)))
                out.append(match.group(0))
                previous = "a"
                index = match.end()
                continue
        if quote == '"':
            if text.startswith("$(", index):
                substitutions += 1
            elif char == ")" and substitutions:
                substitutions -= 1
        if quote is None and char in "'\"":
            quote = char
        elif quote == char:
            quote = None
            substitutions = 0
        if char == "\n" and (quote is None or pending):
            out.append(" ; " if quote is None else "\n")
            previous = "\n"
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
        previous = char
        index += 1
    return "".join(out)


def tokenize(text):
    lexer = shlex.shlex(split_lines(text), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
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
    "env": {"-u", "--unset"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-i", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p"},
    "stdbuf": {"-i", "-o", "-e"},
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U"},
}


def env_option(arg, rest):
    """`env -C dir` / `env -S string` in every spelling: (key, value, tokens used)."""
    for short, long_, key in (("-C", "--chdir", "chdir"), ("-S", "--split-string", "split")):
        if arg in (short, long_):
            return key, rest[1] if len(rest) > 1 else "", 2
        if arg.startswith(long_ + "="):
            return key, arg[len(long_) + 1 :], 1
        if arg.startswith(short) and len(arg) > 2:
            return key, arg[2:], 1
    return None


def skip_options(wrapper, rest):
    """Skip a wrapper's own options; return (rest, bypassed, env effects)."""
    valued = WRAPPER_VALUE_FLAGS.get(wrapper, set())
    bypassed = False
    effects = {"chdir": []}
    while rest:
        arg = rest[0]
        option = env_option(arg, rest) if wrapper == "env" and arg.startswith("-") else None
        if is_assignment(arg):
            name, _, value = arg.partition("=")
            bypassed = bypassed or (name == "SKIP_PR_GATE" and value not in BYPASS_OFF)
            rest = rest[1:]
        elif option:
            if option[0] == "chdir":
                effects["chdir"].append(option[1])
            else:
                effects["split"] = option[1]
            rest = rest[option[2] :]
        elif arg.startswith("-") and arg != "-":
            rest = rest[2:] if arg in valued else rest[1:]
        elif wrapper == "timeout" and re.fullmatch(r"\d+(\.\d+)?[smhd]?", arg):
            rest = rest[1:]
        else:
            break
    return rest, bypassed, effects


def strip_prefixes(segment):
    """Drop assignments, keywords, and wrappers; return (rest, bypassed, env effects)."""
    bypassed = False
    effects = {"chdir": []}
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
            rest, skipped, found = skip_options(head, rest[1:])
            bypassed = bypassed or skipped
            effects["chdir"].extend(found["chdir"])
            if "split" in found:
                effects["split"] = found["split"]
        else:
            break
    return rest, bypassed, effects


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


def inner_commands(text):
    """Bodies of `$(...)` and backtick substitutions, wherever they are quoted."""
    found = re.findall(r"`([^`]*)`", text)
    index = 0
    while True:
        start = text.find("$(", index)
        if start < 0:
            return found
        depth, position = 1, start + 2
        while position < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[position], 0)
            position += 1
        found.append(text[start + 2 : position - 1 if depth == 0 else position])
        index = start + 2


DIRECTORY_CHANGE = re.compile(r"(?<![\w-])(?:cd|pushd)(?![\w-])|--chdir|(?<!\w)-C")


def unresolved(text, workdir):
    """Where an unparseable or too-deeply nested command opens its PR.

    The starting directory when nothing in it changes directory; otherwise
    unknown (None), which blocks rather than inherit the starting repo's PASS.
    """
    return None if DIRECTORY_CHANGE.search(text) else workdir


def find_pr_create(text, workdir, depth=0):
    """Every `gh pr create` in the command as (workdir, bypassed).

    A command that cannot be parsed, or that nests deeper than DEPTH_LIMIT,
    counts as a PR creation: the fast filter already saw `gh` and `create`.
    """
    try:
        tokens = tokenize(text)
    except Exception:
        return [(unresolved(text, workdir), False)]
    matches = []
    for segment in segments(tokens):
        for inner in inner_commands(" ".join(segment)):
            if depth >= DEPTH_LIMIT:
                matches.append((unresolved(inner, workdir), False))
            else:
                matches.extend(find_pr_create(inner, workdir, depth + 1))
        rest, bypassed, effects = strip_prefixes(segment)
        target = workdir
        for value in effects["chdir"]:
            target = advance_dir(target, [value])
        nested = None
        if "split" in effects:
            split = effects["split"].replace("\\_", " ")
            nested = " ".join(["env", split] + [shlex.quote(arg) for arg in rest])
        elif rest and os.path.basename(rest[0]) in SHELLS:
            flags = [i for i, arg in enumerate(rest[1:], 1) if is_shell_command_flag(arg)]
            if flags and flags[0] + 1 < len(rest):
                nested = rest[flags[0] + 1]
        elif rest and os.path.basename(rest[0]) == "eval":
            nested = " ".join(rest[1:])
        if nested is not None:
            if depth >= DEPTH_LIMIT:
                matches.append((unresolved(nested, target), bypassed))
            else:
                matches.extend(
                    (path, bypassed or skipped)
                    for path, skipped in find_pr_create(nested, target, depth + 1)
                )
            continue
        if not rest:
            continue
        head = os.path.basename(rest[0])
        if head in {"cd", "pushd"}:
            workdir = advance_dir(workdir, rest[1:])
        elif head == "gh" and gh_creates_pr(rest[1:]):
            matches.append((target, bypassed))
    return matches


targets = []
for path, bypassed in find_pr_create(command, cwd):
    if not bypassed and path not in targets:
        targets.append(path)
if not targets:
    sys.exit(0)


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
        "Run the workflow that owns this change (create-feature or fix-bug), or "
        "`review-code` on the branch for a change outside any workflow, so the "
        "review gate is recorded by the workflow; then retry. The user asking "
        "for the PR already authorizes that review. Do not bypass this on your "
        "own: if review-code cannot run, stop and ask the user, who alone can "
        "override it.",
        file=sys.stderr,
    )
    sys.exit(2)


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


def pending_publish(content, workflow):
    """A pending `published_pr` reservation from this workflow: `reserve` already required review PASS."""
    match = re.search(
        r"<!-- aitk-checkpoint:v1 -->\n(.*?)\n<!-- /aitk-checkpoint -->", content, re.S
    )
    if match is None:
        return False
    try:
        checkpoint = json.loads(match.group(1))
        effects = checkpoint.get("effects", [])
        same_workflow = checkpoint.get("workflow") == workflow
    except Exception:
        return False
    return same_workflow and any(
        isinstance(effect, dict)
        and effect.get("key") == "published_pr"
        and effect.get("status") == "pending"
        for effect in effects
    )


def check(workdir):
    if workdir is None:
        block(
            "the command changes directory in a way this hook cannot follow, so the "
            "repository it opens the PR in is unknown (run `gh pr create` as its own "
            "simple command)"
        )
    root = git_toplevel(workdir)
    if root is None:
        return
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
        # overrides a gate recorded non-PASS in the current phase (e.g. a later RETRY),
        # and only the workflow that made it counts.
        recorded = snapshot["gates"].get("review")
        explicit_non_pass = (
            recorded is not None
            and recorded["phase"] == snapshot["current_phase"]
            and recorded["status"] != "PASS"
        )
        if explicit_non_pass or not pending_publish(content, snapshot.get("workflow")):
            block("the snapshot does not show it passing: " + "; ".join(blockers))


for target in targets:
    check(target)

sys.exit(0)
PY
