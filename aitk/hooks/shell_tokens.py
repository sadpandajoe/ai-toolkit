"""The shell tokenizer the PreToolUse hooks share.

Lifted from the review gate so the git guard and the review gate read a Bash
command the same way. `commands()` walks a command string and yields every
simple command it can see, in order, with its wrapper-stripped argv:

- separators: newlines, `;`, `&&`, `||`, `|`, `&`, `|&` and parentheses;
- here-document bodies are skipped and comments dropped;
- leading `NAME=value` assignments are collected, not executed;
- wrappers are stripped with their own options: `env`, `timeout`, `nohup`,
  `xargs`, `nice`, `ionice`, `stdbuf`, `sudo`, `command`, `exec`, `time`;
- `sh -c`/`bash -c` payloads, `eval` arguments, `env -S` strings and the bodies
  of `$(...)` and backtick substitutions are walked as nested commands.

Known limits (this is a tripwire, not a shell sandbox): command matching is
static, so a `cd` inside a conditional or a subshell counts as taken, shell
functions and aliases are not expanded here, and a command nested deeper than
DEPTH_LIMIT or one that does not tokenize is yielded as `unresolved` for the
caller to decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import shlex
from typing import Iterator


SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}"}
SIMPLE_WRAPPERS = {"command", "exec", "nohup", "time"}
DEPTH_LIMIT = 3

HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([^\s'\"<>;|&()\\]+)\2")
WORD_START = " \t\n;&|("

WRAPPER_VALUE_FLAGS = {
    "env": {"-u", "--unset"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-i", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p"},
    "stdbuf": {"-i", "-o", "-e"},
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U"},
}
WRAPPERS = SIMPLE_WRAPPERS | set(WRAPPER_VALUE_FLAGS)

DIRECTORY_CHANGE = re.compile(r"(?<![\w-])(?:cd|pushd)(?![\w-])|--chdir|(?<!\w)-C")


def split_lines(text: str) -> str:
    """Normalize a command for tokenizing.

    Unquoted newlines become `;`, backslash-newline joins lines, comments are
    dropped, and here-document bodies are skipped, including one opened inside
    a `$(...)` within double quotes (`--body "$(cat <<'EOF' ...)"`).
    """
    out: list[str] = []
    quote: str | None = None
    pending: list[tuple[bool, str]] = []
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


def tokenize(text: str) -> list[str]:
    """Shell words and operators; raises ValueError on unbalanced quotes."""
    lexer = shlex.shlex(split_lines(text), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def is_assignment(token: str) -> bool:
    name, sep, _ = token.partition("=")
    return bool(sep) and name.isidentifier()


def segments(tokens: list[str]) -> Iterator[list[str]]:
    current: list[str] = []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def env_option(arg: str, rest: list[str]) -> tuple[str, str, int] | None:
    """`env -C dir` / `env -S string` in every spelling: (key, value, tokens used)."""
    for short, long_, key in (("-C", "--chdir", "chdir"), ("-S", "--split-string", "split")):
        if arg in (short, long_):
            return key, rest[1] if len(rest) > 1 else "", 2
        if arg.startswith(long_ + "="):
            return key, arg[len(long_) + 1 :], 1
        if arg.startswith(short) and len(arg) > 2:
            return key, arg[2:], 1
    return None


@dataclass
class Effects:
    """What the prefixes of one command set up for it."""

    assignments: dict[str, str] = field(default_factory=dict)
    chdir: list[str] = field(default_factory=list)
    split: str | None = None


def skip_options(wrapper: str, rest: list[str], effects: Effects) -> list[str]:
    """Skip a wrapper's own options and assignments; return what it runs."""
    valued = WRAPPER_VALUE_FLAGS.get(wrapper, set())
    while rest:
        arg = rest[0]
        option = env_option(arg, rest) if wrapper == "env" and arg.startswith("-") else None
        if is_assignment(arg):
            name, _, value = arg.partition("=")
            effects.assignments[name] = value
            rest = rest[1:]
        elif option:
            if option[0] == "chdir":
                effects.chdir.append(option[1])
            else:
                effects.split = option[1]
            rest = rest[option[2] :]
        elif arg.startswith("-") and arg != "-":
            rest = rest[2:] if arg in valued else rest[1:]
        elif wrapper == "timeout" and re.fullmatch(r"\d+(\.\d+)?[smhd]?", arg):
            rest = rest[1:]
        else:
            break
    return rest


def strip_prefixes(segment: list[str]) -> tuple[list[str], Effects]:
    """Drop assignments, keywords and wrappers; return (argv, effects)."""
    effects = Effects()
    rest = list(segment)
    while rest:
        head = os.path.basename(rest[0])
        if is_assignment(rest[0]):
            name, _, value = rest[0].partition("=")
            effects.assignments[name] = value
            rest = rest[1:]
        elif head in KEYWORDS:
            rest = rest[1:]
        elif head in WRAPPERS:
            rest = skip_options(head, rest[1:], effects)
        else:
            break
    return rest, effects


def is_shell_command_flag(arg: str) -> bool:
    return arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]


def advance_dir(workdir: str | None, args: list[str]) -> str | None:
    """Follow `cd`/`pushd` so a check reads the repository the command runs in."""
    if workdir is None:
        return None
    target = next((arg for arg in args if not arg.startswith("-")), None)
    if target is None or target == "-":
        return workdir
    path = os.path.expanduser(target)
    path = path if os.path.isabs(path) else os.path.join(workdir, path)
    return os.path.normpath(path) if os.path.isdir(path) else workdir


def inner_commands(text: str) -> list[str]:
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


def unresolved_dir(text: str, workdir: str | None) -> str | None:
    """Where an unparseable or too-deeply nested command runs.

    The starting directory when nothing in it changes directory; otherwise
    unknown (None), so a caller blocks rather than inherit the starting repo.
    """
    return None if DIRECTORY_CHANGE.search(text) else workdir


@dataclass
class Command:
    """One simple command as the shell would run it."""

    argv: list[str]
    assignments: dict[str, str]
    workdir: str | None
    unresolved: bool = False
    text: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.argv[0]) if self.argv else ""


def commands(
    text: str,
    workdir: str | None,
    depth: int = 0,
    inherited: dict[str, str] | None = None,
) -> Iterator[Command]:
    """Yield every command in `text`, in order, nested ones included.

    A command that does not tokenize, or nests deeper than DEPTH_LIMIT, is
    yielded once with `unresolved=True` and its raw text.
    """
    inherited = dict(inherited or {})
    try:
        tokens = tokenize(text)
    except ValueError:
        yield Command([], inherited, unresolved_dir(text, workdir), True, text)
        return
    for segment in segments(tokens):
        for inner in inner_commands(" ".join(segment)):
            if depth >= DEPTH_LIMIT:
                yield Command([], {}, unresolved_dir(inner, workdir), True, inner)
            else:
                yield from commands(inner, workdir, depth + 1)
        rest, effects = strip_prefixes(segment)
        assignments = {**inherited, **effects.assignments}
        target = workdir
        for value in effects.chdir:
            target = advance_dir(target, [value])
        nested = None
        if effects.split is not None:
            split = effects.split.replace("\\_", " ")
            nested = " ".join(["env", split] + [shlex.quote(arg) for arg in rest])
        elif rest and os.path.basename(rest[0]) in SHELLS:
            flags = [i for i, arg in enumerate(rest[1:], 1) if is_shell_command_flag(arg)]
            if flags and flags[0] + 1 < len(rest):
                nested = rest[flags[0] + 1]
        elif rest and os.path.basename(rest[0]) == "eval":
            nested = " ".join(rest[1:])
        if nested is not None:
            if depth >= DEPTH_LIMIT:
                yield Command([], assignments, unresolved_dir(nested, target), True, nested)
            else:
                yield from commands(nested, target, depth + 1, assignments)
            continue
        if not rest:
            continue
        if os.path.basename(rest[0]) in {"cd", "pushd"}:
            workdir = advance_dir(workdir, rest[1:])
        yield Command(rest, assignments, target)


def positional(args: list[str], value_flags: set[str]) -> list[str]:
    """Non-option arguments, skipping the values of `value_flags`."""
    found: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in value_flags:
            skip = True
        elif not arg.startswith("-"):
            found.append(arg)
    return found


def truthy(value: str | None) -> bool:
    """An override is on unless unset, empty, `0` or `false`."""
    return value is not None and value.strip().lower() not in {"", "0", "false"}
