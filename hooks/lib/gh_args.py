"""How gh reads the arguments of `gh pr create|new|ready|merge|revert` and of `gh api`.

Stdlib only, a sibling of `git_guard` (hooks run `python3 -E -s`, so it imports from its
own directory). The flag tables are gh 2.103.0's (`gh pr <verb> --help`); a newer gh may
add flags, so a flag a table lacks is an unknown flag, which grants nothing (`walk`).

Two readings find the verb, and a command is gated when either yields a gated one:
`positional` (a flag is skipped, its value is not) and cobra's `Find` (`cobra_words`: at
the root and `pr` levels a flag that is not a known boolean takes the next word, so
`gh pr -t view merge 12` runs `merge`). A verb or command name that holds a shell
expansion is read as an unknown verb (`UNKNOWN`), which is gated like every verb.

`gh api` is read the same way (`api_commands`, `api_effect`): the endpoint, the method and
the GraphQL query text decide whether a call merges, readies or opens a pull request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import functools
import re
import urllib.parse

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
API_INHERITED = (("h", "help", False),)  # no -R; `gh api -h` prints help
API = (
    (None, "cache", True), ("F", "field", True), ("H", "header", True), (None, "hostname", True),
    (None, "input", True), ("q", "jq", True), ("X", "method", True), ("p", "preview", True),
    ("f", "raw-field", True), ("t", "template", True),
    (None, "allow-escape-sequences", False), ("i", "include", False), (None, "paginate", False),
    (None, "silent", False), (None, "slurp", False), (None, "verbose", False),
)


@dataclass
class Table:
    long: dict[str, bool] = field(default_factory=dict)  # name -> takes a value
    short: dict[str, tuple[str, bool]] = field(default_factory=dict)  # char -> (name, takes a value)


def build(flags: tuple, inherited: tuple = INHERITED) -> Table:
    table = Table()
    for short, name, takes in inherited + flags:
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
TABLES["api"] = build(API, API_INHERITED)
TABLES[UNKNOWN] = TABLES["create"]
TRUE = {"1", "t", "T", "TRUE", "true", "True"}


@dataclass
class Flags:
    help: bool = False
    bools: dict[str, bool] = field(default_factory=dict)  # last value of each boolean
    heads: list[str] = field(default_factory=list)
    unknown_flags: list[str] = field(default_factory=list)  # words the verb's table lacks
    expanded: bool = False  # a positional or a cut that may hide a flag at run time
    values: list[tuple[str, str]] = field(default_factory=list)  # (name, value) of value flags
    positionals: list[str] = field(default_factory=list)

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
            out.positionals.extend(args[index:])
            break
        if len(arg) < 2 or arg[0] != "-":
            out.expanded = out.expanded or has_expansion(arg)  # a positional (`-` too)
            out.positionals.append(arg)
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
        out.values.append((name, value))
        if name == "head":
            out.heads.append(value)
    elif name == "help":
        out.help = bare_help  # the last value wins: `--help=false` after `--help` clears it
    else:
        out.bools[name] = parse_bool(value)


def has_expansion(word: str) -> bool:
    """A word the shell may still rewrite: a variable, substitution, brace or glob."""
    return word != "{}" and any(char in word for char in "$`{*?[")  # `{}`: find's placeholder


def positional_indexes(args: list[str]) -> list[int]:
    found: list[int] = []
    skip = False
    for index, arg in enumerate(args):
        if skip:
            skip = False
        elif arg in GLOBAL_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            found.append(index)
    return found


def positional(args: list[str]) -> list[str]:
    """Non-option arguments, skipping the values of the global value flags."""
    return [args[index] for index in positional_indexes(args)]


def drop_first_positional(args: list[str]) -> list[str]:
    indexes = positional_indexes(args)
    return args[: indexes[0]] + args[indexes[0] + 1 :] if indexes else args


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


def api_commands(args: list[str], expands: bool = False) -> list[list[str]]:
    """The arguments after `api` for every `gh api` that `args` can run: from the guard's
    reading (`positional`) and from cobra's `Find`. `expands`: the command name is an
    expansion, so `api` is searched among the first words (as in `pr_commands`)."""
    found: list[list[str]] = []
    starts = [index for index, word in enumerate(args[:6]) if word == "api"] if expands else [0]
    for start in starts:
        sub = args[start:]
        if expands:
            found.append(sub[1:])
            continue
        if positional(sub)[:1] == ["api"]:
            found.append(drop_first_positional(sub))
        first, rest = next_command(sub, {"help", "version"})
        if first == "api":
            found.append(rest)
    return [item for index, item in enumerate(found) if item not in found[:index]]


MERGE_API, CREATE_API, UNREADABLE_API = "merge", "create", "unreadable"
FIELD_FLAGS = {"field", "raw-field", "input"}
MERGE_NAMES = (
    "mergePullRequest", "markPullRequestReadyForReview", "enablePullRequestAutoMerge",
    "enqueuePullRequest",
)
CREATE_NAMES = ("createPullRequest", "revertPullRequest")
# `https://<host>/`, GHES's `/api/v3/` and `/api/` (graphql) after it
ENDPOINT_PREFIX = re.compile(r"https?://[^/]+/(?:api/(?:v3/)?)?", re.I)
# only POST opens a PR and only PUT merges one
CREATE_TARGETS = ("repos/*/*/pulls", "repositories/*/pulls")
MERGE_TARGETS = ("repos/*/*/pulls/*/merge", "repositories/*/pulls/*/merge")
SHELL_EXPANSION = re.compile(r"\$\{[^}]*\}|\$\(.*?\)|\$\w+|`[^`]*`")
# gh's own placeholders: one non-empty path segment each
TOKEN = re.compile(
    r"(?P<one>\{(?:owner|repo|branch)\})"
    r"|(?P<any>\$\{[^}]*\}|\$\(.*?\)|\$\w+|\$|`[^`]*`|\{[^}]*\}|[*?\[])"
)


@dataclass
class Api:
    endpoints: list[str]  # normalised; several only when an unknown flag hides the endpoint
    may_post: bool
    may_put: bool
    tainted: bool  # an expansion, cut or unknown flag may add a flag or field
    queries: list[str]  # the `query=` values of -f and -F
    unreadable_query: bool  # --input, a `@file`, or a query with a shell expansion in it


def normalise_endpoint(endpoint: str) -> str:
    """The path gh requests: no `https://<host>/` prefix (nor GHES's `api/v3/`, `api/`),
    `?query` or `#fragment` (found outside any expansion: `${X:?}` is no query), no `/`."""
    endpoint = ENDPOINT_PREFIX.sub("", endpoint, count=1)
    spans = [found.span() for found in SHELL_EXPANSION.finditer(endpoint)]
    for position, char in enumerate(endpoint):
        if char in "?#" and not any(start <= position < end for start, end in spans):
            endpoint = endpoint[:position]
            break
    endpoint = urllib.parse.unquote(endpoint)  # `%6Derge` is `merge`
    endpoint = re.sub(r"/{2,}", "/", endpoint)
    endpoint = re.sub(r"/\.(?=/|$)", "", endpoint)  # `pulls/12/./merge`
    return endpoint.strip("/")


GRAPHQL_OPERATION = re.compile(r"\b(?:query|mutation|subscription)\b\s*(?:[A-Za-z_]\w*\s*)?\(")


def graphql_mask(text: str) -> bytearray:
    """1 at each character of `text` inside a GraphQL string or `#` comment, else 0."""
    skipped: list[tuple[int, int]] = []  # strings and comments
    position = 0
    while position < len(text):
        char = text[position]
        if char == "#":
            end = text.find("\n", position)
            end = len(text) if end < 0 else end
            skipped.append((position, end))
            position = end
        elif char == '"':
            if text.startswith('"""', position):
                end = text.find('"""', position + 3)
                end = len(text) if end < 0 else end + 3
            else:
                end = position + 1
                while end < len(text) and text[end] not in '"\n':
                    end += 2 if text[end] == "\\" else 1
                end += 1
            skipped.append((position, min(end, len(text))))
            position = end
        else:
            position += 1

    mask = bytearray(len(text) + 1)
    for start, end in skipped:
        mask[start:end] = b"\x01" * (end - start)
    return mask


def graphql_scan(text: str) -> tuple[set[str], list[tuple[int, int]]]:
    """The variable names declared in the operations' definition lists, and the spans (start,
    end) of those lists. A list is `query|mutation|subscription [Name] ( ... )` at the top level
    of the document; strings and `#` comments hold no definition."""
    mask = graphql_mask(text)

    def inside_skipped(at: int) -> bool:
        return bool(mask[at])

    names: set[str] = set()
    lists: list[tuple[int, int]] = []
    depth = 0
    position = 0
    while position < len(text):
        if inside_skipped(position):
            position += 1
            continue
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
        elif depth == 0 and char in "qms":
            found = GRAPHQL_OPERATION.match(text, position)
            if found and (position == 0 or not (text[position - 1].isalnum() or text[position - 1] == "_")):
                start = found.end()
                level, end = 1, start
                while end < len(text) and level:
                    if not inside_skipped(end):
                        level += (text[end] == "(") - (text[end] == ")")
                    end += 1
                lists.append((start, end))
                for name in re.finditer(r"\$(\w+)\s*:", text[start:end]):
                    if not inside_skipped(start + name.start()):
                        names.add(name.group(1))
                position = end
                continue
        position += 1
    return names, lists


def query_unreadable(text: str) -> bool:
    """A `$` in query text is a GraphQL variable only when BOTH readings agree: the name is
    declared in an operation's definition list (`query Name($a: T, $b: T)`), and the `$` stands
    where GraphQL allows a variable (inside parentheses, after `(`, `:`, `[`, `,` or `=`, spaces
    aside, or as a definition in the list). Any other `$` (an undeclared name, `$5`, `$M(` or `x:
    $M` in a selection, `$M:` outside the list) is a shell expansion the guard cannot read."""
    if "`" in text:
        return True
    if "$" not in text:
        return False
    names, lists = graphql_scan(text)
    mask = graphql_mask(text)
    parens = 0
    bare: set[int] = set()  # `$`s outside strings and outside every parenthesis
    for at, char in enumerate(text):
        if mask[at]:
            continue
        if char == "(":
            parens += 1
        elif char == ")":
            parens = max(parens - 1, 0)
        elif char == "$" and parens == 0:
            bare.add(at)
    for found in re.finditer(r"\$", text):
        at = found.start()
        if at in bare:
            return True  # a variable stands only in a value, inside `(...)`: `x: $M(input: ...)`
        name = re.match(r"\w+", text[at + 1 :])
        if name is None or name.group(0)[0].isdigit() or name.group(0) not in names:
            return True
        after = at + 1 + len(name.group(0))
        while after < len(text) and text[after].isspace():
            after += 1
        defines = text[after : after + 1] == ":"
        inside = any(start <= at < end for start, end in lists)
        if defines and not inside:
            return True  # `$name:` defines a variable only inside the list
        if not (defines or text[:at].rstrip()[-1:] in {"(", ":", "[", ",", "="}):
            return True  # a variable stands after one of those, or as a definition
    return False


def read_api(args: list[str], cut: bool = False) -> Api | None:
    """`gh api`'s arguments (after `api`) as its flag table reads them; None for help.
    `cut`: an unquoted `$(` ended the words, so what follows is unknown."""
    flags = walk(args, "api", cut)
    if flags.asks_help:
        return None
    methods = [value for name, value in flags.values if name == "method"]
    fielded = any(name in FIELD_FLAGS for name, _ in flags.values)
    # a positional after the endpoint with an expansion may be `-X PUT` split by the shell
    extra = any(has_expansion(word) for word in flags.positionals[1:])
    overridden = any(
        name == "header"
        and (value.replace(" ", "").lower().startswith("x-http-method-override:") or has_expansion(value))
        for name, value in flags.values
    )  # the server may run another method than -X says; a header that expands may say so
    unknown = cut or extra or overridden or bool(flags.unknown_flags) or (bool(methods) and has_expansion(methods[-1]))
    method = methods[-1].upper() if methods else ("POST" if fielded else "GET")
    queries: list[str] = []
    unreadable = False
    for name, value in flags.values:
        if name == "input":
            unreadable = True
        elif name in {"field", "raw-field"}:
            key, _, text = value.partition("=")
            if key == "query":  # every other field is a GraphQL variable
                queries.append(text)
                unreadable = unreadable or (name == "field" and text.startswith("@")) or query_unreadable(text)
    candidates = flags.positionals if flags.unknown_flags else flags.positionals[:1]
    return Api(
        endpoints=[normalise_endpoint(word) for word in candidates],
        may_post=unknown or method == "POST",
        may_put=unknown or method == "PUT",
        tainted=extra or cut or bool(flags.unknown_flags),
        queries=queries,
        unreadable_query=unreadable,
    )


def split_segments(endpoint: str) -> list[str]:
    """`endpoint` cut at the `/` that no expansion holds (`${X/y}` is one piece)."""
    spans = [found.span() for found in TOKEN.finditer(endpoint)]
    out: list[str] = []
    start = 0
    for position, char in enumerate(endpoint):
        if char == "/" and not any(begin <= position < end for begin, end in spans):
            out.append(endpoint[start:position])
            start = position + 1
    return out + [endpoint[start:]]


def segment_regex(segment: str) -> str:
    """A segment with expansions as a regex: a gh placeholder is one non-empty segment, a
    shell expansion is non-empty and may span `/`."""
    parts: list[str] = []
    position = 0
    for found in TOKEN.finditer(segment):
        parts.append(re.escape(segment[position : found.start()].lower()))
        parts.append("[^/]+" if found.group("one") else ".+")
        position = found.end()
    parts.append(re.escape(segment[position:].lower()))
    return "".join(parts)


def could_be(endpoint: str, target: str) -> bool:
    """Whether some value of `endpoint` is a path of `target`, whose `*` is a non-empty
    segment. An expansion is non-empty and may span `/`, and the text around it in its
    segment must still match (`$NAME.md` is never `merge`). In a path of several segments an
    expansion that is a whole segment does not stand for one literal target segment alone
    (`repos/$R/statuses/$SHA` is not `repos/o/r/pulls`): a limit, pinned in the tests."""
    wanted = target.split("/")
    segments = split_segments(endpoint)
    many = len(segments) > 1

    def literal_chunk(first: int, end: int) -> bool:
        return end - first == 1 and wanted[first] != "*"

    @functools.lru_cache(maxsize=None)
    def match(i: int, j: int) -> bool:
        if i == len(segments):
            return j == len(wanted)
        segment = segments[i]
        found = TOKEN.fullmatch(segment)
        if not found and not TOKEN.search(segment):
            return j < len(wanted) and wanted[j] in {"*", segment.lower()} and match(i + 1, j + 1)
        if found:
            limit = j + 2 if found.group("one") else len(wanted) + 1
            return any(
                not (many and literal_chunk(j, end)) and match(i + 1, end)
                for end in range(j + 1, min(limit, len(wanted) + 1))
            )
        regex = segment_regex(segment)
        for end in range(j + 1, len(wanted) + 1):
            chunk = wanted[j:end]
            if "*" in chunk:
                ok = len(chunk) == 1 or any(part for part in re.split(r"\W+", segment))
            else:
                ok = re.fullmatch(regex, "/".join(chunk), re.I) is not None
            if ok and match(i + 1, end):
                return True
        return False

    return match(0, 0)


def api_effect(args: list[str], cut: bool = False) -> str | None:
    """What a `gh api` call does to pull requests: `MERGE_API` (merges or readies),
    `CREATE_API` (opens one), `UNREADABLE_API` (a GraphQL query or endpoint the guard
    cannot read, which could be either) or None."""
    api = read_api(args, cut)
    if api is None:
        return None
    if not api.endpoints:
        return UNREADABLE_API if api.may_post or api.may_put else None
    effects: list[str] = []
    for endpoint in api.endpoints:
        if could_be(endpoint, "graphql"):
            if has_expansion(endpoint):
                if api.may_post:
                    effects.append(UNREADABLE_API)
            elif api.tainted or api.unreadable_query:
                effects.append(UNREADABLE_API)
            else:
                text = " ".join(api.queries)
                if any(name in text for name in CREATE_NAMES):
                    effects.append(CREATE_API)
                if any(name in text for name in MERGE_NAMES):
                    effects.append(MERGE_API)
        if api.may_post and any(could_be(endpoint, target) for target in CREATE_TARGETS):
            effects.append(CREATE_API)
        if api.may_put and any(could_be(endpoint, target) for target in MERGE_TARGETS):
            effects.append(MERGE_API)
    for effect in (UNREADABLE_API, CREATE_API, MERGE_API):
        if effect in effects:
            return effect
    return None
