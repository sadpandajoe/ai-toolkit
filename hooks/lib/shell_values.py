"""What the variables a command assigns may hold: `assigned_values`.

A variable the command never touches comes from the session environment, which the user set:
Claude Code's Bash tool (and, as assumed for Codex, its shell) runs each command in a fresh shell,
so nothing an earlier command assigned carries over. Such a name is absent from the table and the
callers keep their readings of it.

A name the command touches gets a `Value`: every literal value assigned to it anywhere in the
command (a union, so last-write order, subshells, conditionals and prefix assignments cannot hide
one: `P=push; P=status true; git $P` may be `push`), and `unknown` when it may also hold something
else: a value that is not literal, an append, an array, a write the table does not read (`read P`,
`printf -v P`, `unset P`, `${P:=x}`, `declare -n`), an assignment inside nested text, a `source`,
`.` or `eval` in command position, or any mention of `IFS`. `for NAME in words` gives the words.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from shell_lex import KEYWORDS, SEPARATORS

NAME = r"[A-Za-z_][A-Za-z0-9_]*"
NAME_WORD = re.compile(NAME)
ASSIGNMENT = re.compile(rf"^({NAME})(\+?)=(.*)$", re.S)
PLAIN_VARIABLE = re.compile(rf"^\$(?:({NAME})|\{{({NAME})\}})$")
POSITIONAL_WORD = re.compile(r"^\$(?:[@*#]|[1-9])$|^\$\{(?:[@*#]|[1-9][0-9]*)\}$")
UNREADABLE_VALUE = re.compile(r"[$`;&|<>()*?\[\\\n'\"]")
VARIABLE_USE = re.compile(rf"\$\{{?({NAME})")
IDENTIFIER = re.compile(rf"(?<![A-Za-z0-9_]){NAME}")
ASSIGNMENT_START = set(" \t\n;&|(`'\"")  # what may stand before `NAME=` that starts a word
READABLE_HEADS = {"export", "readonly"}  # a bare `export NAME` keeps the value
CLEARING_HEADS = {"source", ".", "eval"}  # may assign anything
POSITIONAL = "@"  # the table's key for the positional parameters (`set -- ...`)


@dataclass(frozen=True)
class Value:
    candidates: frozenset
    unknown: bool


def plain_variable(word: str) -> str | None:
    """N for a word that is exactly `$N` or `${N}`, else None."""
    match = PLAIN_VARIABLE.match(word)
    return (match.group(1) or match.group(2)) if match else None


def is_positional_word(word: str) -> bool:
    return bool(POSITIONAL_WORD.match(word))


def command_position(tokens: list[str], index: int) -> bool:
    """Whether token `index` starts a command (after a separator, a keyword or assignments)."""
    back = index - 1
    while back >= 0 and ASSIGNMENT.match(tokens[back]) and tokens[back] not in SEPARATORS:
        back -= 1
    return back < 0 or tokens[back] in SEPARATORS or tokens[back] in KEYWORDS or tokens[back] in {"then", "do", "else"}


def segment_heads(tokens: list[str]) -> list[str | None]:
    """For each token, the first non-assignment word of its segment (so far), in one pass."""
    heads: list[str | None] = []
    head: str | None = None
    for token in tokens:
        if token in SEPARATORS:
            head = None
        elif head is None and not ASSIGNMENT.match(token):
            head = token
        heads.append(head)
    return heads


def sets_positional(tokens: list[str]) -> bool:
    """Whether a `set` in command position has `--` or an operand (`set -- a b`, `set a b`;
    `set -euo pipefail` does not)."""
    for index, token in enumerate(tokens):
        if token != "set" or not command_position(tokens, index):
            continue
        position = index + 1
        while position < len(tokens) and tokens[position] not in SEPARATORS:
            word = tokens[position]
            if word == "--":
                return True
            if word[:1] in "-+" and len(word) > 1:
                position += 2 if word[-1] == "o" else 1  # `-o pipefail`, `-euo pipefail`
                continue
            return True
        continue
    return False


def assigned_values(tokens: list[str], text: str, inherited: dict | None = None) -> dict[str, Value]:
    """Every name the command touches, with what it may hold (see the module docstring).
    `inherited` is an enclosing command's table (a function body, an `eval`), merged in."""
    candidates: dict[str, set] = {}
    unknown: set[str] = set()
    token_assignments: dict[str, int] = {}

    def touch(name: str) -> None:
        candidates.setdefault(name, set())

    for index, token in enumerate(tokens):
        match = ASSIGNMENT.match(token)
        if match:
            name, plus, value = match.groups()
            touch(name)
            token_assignments[name] = token_assignments.get(name, 0) + 1
            if plus or value.startswith("(") or UNREADABLE_VALUE.search(value):
                unknown.add(name)
            else:
                candidates[name].add(value)
        if token == "for" and index + 2 < len(tokens) and NAME_WORD.fullmatch(tokens[index + 1]):
            name = tokens[index + 1]
            touch(name)
            if tokens[index + 2] != "in":
                unknown.add(name)  # `for NAME; do`: the positional parameters
                continue
            position = index + 3
            while position < len(tokens) and tokens[position] not in SEPARATORS and tokens[position] != "do":
                word = tokens[position]
                if UNREADABLE_VALUE.search(word):
                    unknown.add(name)
                else:
                    candidates[name].add(word)
                position += 1

    used = set(VARIABLE_USE.findall(text)) | set(candidates)
    heads = segment_heads(tokens)
    readable_bare = {
        token
        for index, token in enumerate(tokens)
        if (heads[index] in READABLE_HEADS or (index and tokens[index - 1] == "for")) and NAME_WORD.fullmatch(token)
    }
    text_assignments: dict[str, int] = {}
    written: set[str] = set()
    for match in IDENTIFIER.finditer(text):  # one pass over every name in the text
        name = match.group(0)
        if name not in used:
            continue
        start, end = match.span()
        before = text[start - 1] if start else ""
        if before == "$":
            continue  # `$N`
        if text[start - 2 : start] == "${":
            if text[end : end + 2] == ":=" or text[end : end + 1] == "=":
                written.add(name)  # `${N:=x}`
            continue  # `${N}`, `${N:-x}`, `${N#x}`
        if (text[end : end + 1] == "=" or text[end : end + 2] == "+=") and (not before or before in ASSIGNMENT_START):
            text_assignments[name] = text_assignments.get(name, 0) + 1
            continue
        if name in readable_bare:
            continue
        written.add(name)  # `read N`, `unset N`, `printf -v N`, `((N=1))`, `declare -n N`
    for name in used:
        if name not in candidates and name not in written:
            continue  # only ever expanded: the environment's (the user's)
        touch(name)
        if name in written or text_assignments.get(name, 0) != token_assignments.get(name, 0):
            unknown.add(name)

    clearing = not CLEARING_HEADS.isdisjoint(tokens) and any(
        token in CLEARING_HEADS and command_position(tokens, index) for index, token in enumerate(tokens)
    )
    if clearing or re.search(r"(?<![A-Za-z0-9_])IFS(?![A-Za-z0-9_])", text):
        for name in used:
            touch(name)
            unknown.add(name)
    table = {name: Value(frozenset(values), name in unknown) for name, values in candidates.items()}
    if sets_positional(tokens):
        table[POSITIONAL] = Value(frozenset(), True)
    for name, value in (inherited or {}).items():
        if name in table:
            mine = table[name]
            table[name] = Value(mine.candidates | value.candidates, mine.unknown or value.unknown)
        else:
            table[name] = value
    return table


def split_readings(value: str) -> list[list[str]]:
    """A value read where a word with a space could not run anything (a command word, git's
    subcommand): as one word, and split on whitespace."""
    words = value.split()
    readings = [[value]]
    if words != [value]:
        readings.append(words)
    return readings
