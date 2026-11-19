"""How gh reads the arguments of `gh pr create|new|ready|merge|revert`.

Stdlib only, a sibling of `git_guard` (hooks run `python3 -E -s`, so it imports from its
own directory). The flag tables are gh 2.103.0's (`gh pr <verb> --help`); a newer gh may
add flags, so a flag a table lacks is an unknown flag, which grants nothing (`walk`).

Two readings find the verb, and a command is gated when either yields a gated one:
`positional` (a flag is skipped, its value is not) and cobra's `Find` (`cobra_words`: at
the root and `pr` levels a flag that is not a known boolean takes the next word, so
`gh pr -t view merge 12` runs `merge`). A verb or command name that holds a shell
expansion is read as an unknown verb (`UNKNOWN`), which is gated like every verb.
"""

from __future__ import annotations

from dataclasses import dataclass, field

UNKNOWN = "?"
GATED = {"ready", "merge", "create", "new", "revert"}
GLOBAL_VALUE_FLAGS = {"-R", "--repo", "--hostname"}  # the guard's reading skips their values

# (short, long, takes a value)
INHERITED = (("R", "repo", True), ("h", "help", False))
CREATE = (
    ("a", "assignee", True), (None, "attach", True), ("B", "base", True), ("b", "body", True),
    ("F", "body-file", True), ("H", "head", True), ("l", "label", True), ("m", "milestone", True),
    ("p", "project", True), (None, "recover", True), ("r", "reviewer", True),
    ("T", "template", True), ("t", "title", True),
    ("d", "draft", False), (None, "dry-run", False), ("e", "editor", False), ("f", "fill", False),
    (None, "fill-first", False), (None, "fill-verbose", False),
    (None, "no-maintainer-edit", False), ("w", "web", False),
)
MERGE = (
    ("A", "author-email", True), ("b", "body", True), ("F", "body-file", True),
    (None, "match-head-commit", True), ("t", "subject", True),
    (None, "admin", False), (None, "auto", False), ("d", "delete-branch", False),
    (None, "disable-auto", False), ("m", "merge", False), ("r", "rebase", False),
    ("s", "squash", False),
)
READY = ((None, "undo", False),)
REVERT = (("b", "body", True), ("F", "body-file", True), ("t", "title", True), ("d", "draft", False))


@dataclass
class Table:
    long: dict[str, bool] = field(default_factory=dict)  # name -> takes a value
    short: dict[str, tuple[str, bool]] = field(default_factory=dict)  # char -> (name, takes a value)


def build(flags: tuple) -> Table:
    table = Table()
    for short, name, takes in INHERITED + flags:
        table.long[name] = takes
        if short:
            table.short[short] = (name, takes)
    return table


TABLES = {
    "create": build(CREATE),
    "new": build(CREATE),
    "merge": build(MERGE),
    "ready": build(READY),
    "revert": build(REVERT),
}
TABLES[UNKNOWN] = TABLES["create"]
TRUE = {"1", "t", "T", "TRUE", "true", "True"}


@dataclass
class Flags:
    help: bool = False
    bools: dict[str, bool] = field(default_factory=dict)  # last value of each boolean
    heads: list[str] = field(default_factory=list)
    unknown_flags: list[str] = field(default_factory=list)  # words the verb's table lacks
    expanded: bool = False  # a positional or a cut that may hide a flag at run time

    @property
    def unknown(self) -> bool:
        return bool(self.unknown_flags)

    @property
    def trusted(self) -> bool:
        """Nothing in the words can change what a grant below reads."""
        return not self.unknown_flags and not self.expanded

    def on(self, name: str) -> bool:
        """A boolean flag that is set, with nothing unread in the way."""
        return self.trusted and self.bools.get(name, False)

    @property
    def asks_help(self) -> bool:
        return self.help and self.trusted


def parse_bool(value: str) -> bool:
    """strconv.ParseBool; a value it rejects makes gh exit, so it reads as not set."""
    return value in TRUE


def walk(args: list[str], verb: str, cut: bool = False) -> Flags:
    """`args` (all of gh's arguments after its name) as pflag reads them for `verb`.

    A boolean takes `--name` or `--name=<v>`, never the next word; a value flag takes the
    rest of a short word or else the next word whatever it looks like (`--title -h`).
    Help is a bare `-h` or `--help` that no flag took as its value: `--help=false` and an
    `h` in a cluster are read as not help, the safe side. A positional that holds an
    expansion (`$X` may be `--draft=false`), or `cut` (an unquoted `$(` ended the command's
    words), marks the flags `expanded`.
    """
    table = TABLES[verb]
    out = Flags(expanded=cut)
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            break
        if len(arg) < 2 or arg[0] != "-":
            out.expanded = out.expanded or has_expansion(arg)  # a positional (`-` too)
            continue
        if arg[1] == "-":
            name, equals, value = arg[2:].partition("=")
            if not name or name[0] == "-" or name not in table.long:
                out.unknown_flags.append(arg)
                continue
            takes = table.long[name]
            if not equals:
                if takes:
                    value = args[index] if index < len(args) else ""
                    index += 1
                else:
                    value = "true"
            record(out, name, takes, value, arg in {"--help"})
            continue
        rest = arg[1:]
        while rest:
            spec = table.short.get(rest[0])
            if spec is None:
                out.unknown_flags.append(arg)
                break
            name, takes = spec
            if len(rest) > 2 and rest[1] == "=":
                value, rest = rest[2:], ""
            elif not takes:
                value, rest = "true", rest[1:]
            elif len(rest) > 1:
                value, rest = rest[1:], ""
            else:
                value, rest = (args[index] if index < len(args) else ""), ""
                index += 1
            record(out, name, takes, value, arg == "-h")
    return out


def record(out: Flags, name: str, takes: bool, value: str, bare_help: bool) -> None:
    if takes:
        if name == "head":
            out.heads.append(value)
    elif name == "help":
        out.help = out.help or bare_help
    else:
        out.bools[name] = parse_bool(value)


def has_expansion(word: str) -> bool:
    """A word the shell may still rewrite: a variable, substitution, brace or glob."""
    return word != "{}" and any(char in word for char in "$`{*?[")  # `{}`: find's placeholder


def positional(args: list[str]) -> list[str]:
    """Non-option arguments, skipping the values of the global value flags."""
    found: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in GLOBAL_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            found.append(arg)
    return found


def next_command(args: list[str], booleans: set[str]) -> tuple[str | None, list[str]]:
    """cobra's `stripFlags`: the first command word, and the arguments without it. A flag
    that is not a known boolean takes the next word (`-t view`); `--flag=v` and `-ab` do not."""
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            break
        long = arg.startswith("--") and "=" not in arg
        if (long and arg[2:] not in booleans) or (
            not long and arg.startswith("-") and "=" not in arg and len(arg) == 2 and arg[1:] not in booleans
        ):
            if len(args) - index <= 1:
                break
            index += 1
        elif arg and not arg.startswith("-"):
            return arg, args[: index - 1] + args[index:]
    return None, []


def cobra_words(args: list[str]) -> list[str]:
    """The command words gh's root and `pr` levels find: `["pr", verb]` at most. gh gives
    `--help` (and `--version` at the root) no shorthand there, so `-h` takes the next word."""
    first, rest = next_command(args, {"help", "version"})
    if first != "pr":
        return [first] if first else []
    second, _ = next_command(rest, {"help"})
    return [first, second] if second else [first]


def pr_commands(args: list[str], expands: bool = False) -> list[tuple[str, list[str]]]:
    """The gated `gh pr` verbs `args` can run, each with the arguments to walk for it.

    A known verb comes from either reading (the guard's `positional`, cobra's `Find`); an
    unknown one (`UNKNOWN`: a word a shell expansion hides) from cobra's alone, which is how
    gh resolves it. `expands`: the command name is itself an expansion (`$g pr merge`), so
    `pr` is searched among the first words instead of being the first.
    """
    found: list[tuple[str, list[str]]] = []
    starts = [index for index, word in enumerate(args[:6]) if word == "pr"] if expands else [0]
    for start in starts:
        sub = args[start:]
        words = positional(sub)
        if words[:1] == ["pr"] and len(words) > 1 and words[1] in GATED:
            found.append((words[1], sub))
        cobra = cobra_words(sub)
        if cobra and cobra[0] != "pr":
            if has_expansion(cobra[0]) and not expands:
                found.append((UNKNOWN, sub))
        elif len(cobra) > 1:
            if has_expansion(cobra[1]):
                found.append((UNKNOWN, sub))
            elif cobra[1] in GATED:
                found.append((cobra[1], sub))
    return [item for index, item in enumerate(found) if item not in found[:index]]
