"""The directory model of `shell_tokens.commands()`: `DirectoryModel`, the `cd`, `pushd` and
`git -C` targets it follows, and what a `$(...)` leaves behind (`after_substitution`).

The rules and limits it keeps are in the `shell_tokens` module docstring."""

from __future__ import annotations

import functools
import os
import re
import subprocess

from shell_lex import (
    FdWord, KEYWORDS, REDIRECTIONS, REDIRECTION_FD, SEPARATORS, SIMPLE_WRAPPERS, TOPLEVEL_SUBSTITUTIONS,
    drop_redirections, is_assignment, may_be, may_vanish, opens_substitution,
)


# A directory word whose real value this module cannot know: a variable, tilde or
# substitution the shell expands, a glob character (`*?[` pick a directory by pattern),
# or a newline or tab (the line-based callers cannot carry one: the pre-push shell
# reads the directory back with `read`, which strips a trailing tab).
UNKNOWN_PATH = re.compile(r"[$~`\n\t*?\[]")
# The same for a `cd` target, except `~`, which `advance_dir` expands the way the shell does.
UNKNOWN_CD_TARGET = re.compile(r"[$`\n\t*?\[]")

DIRECTORY_CHANGE = re.compile(r"(?<![\w-])(?:cd|pushd|popd)(?![\w-])|--chdir|(?<!\w)-C")


VARIABLE_WORD = re.compile(r"\$(?:(\w+)|\{(\w+)\})(/.*)?", re.S)


# What no variable is known to hold: HOME is unknown too, not the real home directory.
NO_VARIABLES: dict[str, str | None] = {"HOME": None}


def expand_vars(word: str, variables: dict[str, str | None] | None) -> str:
    """`$NAME`, `${NAME}` or either followed by `/rest`, with NAME a known literal path.

    `variables` is what `DirectoryModel` knows at that point; `$HOME` is the home
    directory, as `~` is. Any other `$` word is returned as it is, which stays unknown.
    """
    if "$" not in word or variables is None:
        return word
    match = VARIABLE_WORD.fullmatch(word)
    if not match:
        return word
    name = match.group(1) or match.group(2)
    if name in variables:
        value = variables[name]  # None: assigned something that is not a literal path
    elif name == "HOME":
        value = os.path.expanduser("~")
        value = None if value.startswith("~") else value
    else:
        value = None
    rest = match.group(3) or ""
    if value is None or UNKNOWN_CD_TARGET.search(rest):
        return word
    return value + rest


def literal_value(value: str) -> str | None:
    """The path a variable assignment stores, or None when the guard cannot tell it.

    `$`, a backtick, a glob character, whitespace (the shell splits the word: `cd $S` fails)
    and an empty value are not a literal path, and neither is a `~`: bash expands an unquoted one and keeps a quoted one, and the
    quotes are gone by the time the value is read here (`S='~/x'; cd $S` stays put).
    """
    if not value or UNKNOWN_CD_TARGET.search(value) or "~" in value or any(c.isspace() for c in value):
        return None
    return value


def hop_dir(
    directory: str | None, value: str, variables: dict[str, str | None] | None = None
) -> str | None:
    """One `-C VALUE` hop from `directory`: normpath, unknown (None) for a value the shell expands."""
    value = expand_vars(value, variables)
    if directory is None or UNKNOWN_PATH.search(value):
        return None
    return os.path.normpath(os.path.join(directory, value))


@functools.lru_cache(maxsize=32)
def git_toplevel(path: str) -> str | None:
    """`git -C path rev-parse --show-toplevel`, or None when it fails (not a repository, no git)."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", path, "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    top = result.stdout.strip()
    return top if result.returncode == 0 and top and "\n" not in top else None


def has_dir_target(args: list[str]) -> bool:
    """Whether `cd`/`pushd` arguments name a target (a bare `pushd` swaps the directory stack)."""
    return any(arg == "-" or not arg.startswith("-") for arg in args)


def advance_dir(
    workdir: str | None, args: list[str], variables: dict[str, str | None] | None = None
) -> str | None:
    """Follow `cd`/`pushd` so a check reads the repository the command runs in.

    A bare `cd` goes to HOME; `cd -` is unknown (the previous directory is not tracked).
    A target the shell would expand (`$`, a backtick), a glob (`*?[`) or a target with a newline
    or a tab leaves the directory unknown (None); `~` is expanded here the way the shell does.
    The one substitution read instead is the git top level of the current directory
    (`TOPLEVEL_SUBSTITUTIONS`), which is that repository's root, or unknown outside one.
    From an unknown directory only an absolute target (or `~`) that exists is known again;
    a relative one stays unknown. `$NAME` is read from `variables` (`expand_vars`).
    """
    target = next((arg for arg in args if arg == "-" or not arg.startswith("-")), None)  # see has_dir_target
    if target == "-":
        return None  # the previous directory is not tracked
    if target is None:
        target = "~"  # a bare `cd` goes home
    target = expand_vars(target, variables)
    if target in TOPLEVEL_SUBSTITUTIONS:
        return None if workdir is None else git_toplevel(workdir)
    if UNKNOWN_CD_TARGET.search(target):
        return None
    path = os.path.expanduser(target)
    if workdir is None and not os.path.isabs(path):
        return None
    path = path if os.path.isabs(path) else os.path.join(workdir, path)
    return os.path.normpath(path) if os.path.isdir(path) else workdir


PIPES = {"|", "|&"}
LIST_END = {";", "&"}
OPENS_BODY = {"if", "while", "until", "for", "select", "case"}
CLOSES_BODY = {"fi", "done", "esac"}
STARTS_LIST = {"then", "do", "else", "elif", "!"}
DIR_COMMANDS = {"cd", "pushd", "popd"}
ELEMENT_ASSIGNMENT = re.compile(r"(\w+)\[[^\]]*\]\+?=")
ASSIGNING = {"export", "declare", "typeset", "local", "readonly"}
FORGETTING = {"read", "unset", "mapfile", "readarray", "getopts"}
CLEARING = {"eval", "source", "."}  # may assign anything


AFTER_COMMAND, AFTER_ARGUMENT, AFTER_EITHER = "command", "argument", "either"
EITHER_DEPTH_LIMIT = 8  # readings of one segment opened inside one another (`either_reading`)
PREFIX_WORDS = KEYWORDS | SIMPLE_WRAPPERS | {"builtin", "time", "for", "select", "case"}


def after_substitution(words: list[str], continuation: str | None) -> str:
    """What the words after the `)` of a `$(...)`, `<(...)` or `>(...)` that ends the segment
    `words` would be: the command (`X=$(x) cd D`: only assignments, keywords and redirections
    come first), the arguments of a command that is there whatever the substitution prints
    (`echo $(x) cd D`), or either (`$(true) cd D`, `command $(true) cd D`: the substitution may
    print nothing, so the words may be the command)."""
    if continuation == AFTER_ARGUMENT:
        return AFTER_ARGUMENT
    operand = False  # the word is the target of a redirection
    vanished = False  # a word before may have expanded to nothing (`$X $(true) cd D`)
    prefixed = False  # a prefix word came before: its options do not end the prefix (`command -p`)
    for position, word in enumerate(words):
        last = position == len(words) - 1
        if operand:
            operand = False
        elif prefixed and not last and word[:1] in "-+" and len(word) > 1:
            pass  # `command -p $(true) cd D`, `builtin -- ...`, `time -p ...`
        elif last and word in {"<", ">"}:
            return AFTER_ARGUMENT  # `<(x)` is a word of its own: the command word
        elif word in REDIRECTIONS:
            operand = True
        elif not last and words[position + 1] in REDIRECTIONS and (
            isinstance(word, FdWord) or REDIRECTION_FD.fullmatch(word)
        ):
            pass  # `2>x $(true) cd D`: the descriptor of a redirection (a wrong guess only adds doubt)
        elif last and word.endswith("$") and (not word[:-1] or may_vanish(word[:-1])):
            return AFTER_EITHER  # the substitution stands where the command word does
        elif word in PREFIX_WORDS or is_assignment(word) or may_vanish(word):
            vanished = vanished or may_vanish(word)  # past one, a word may be the command: doubt
            prefixed = prefixed or word in PREFIX_WORDS or vanished
        else:
            return AFTER_ARGUMENT
    return AFTER_EITHER if continuation == AFTER_EITHER or vanished else AFTER_COMMAND


class Scope:
    """The and-or list being read, and the bodies and groups it sits in."""

    def __init__(self) -> None:
        self.deferred = False  # an `&&`-left cd ran: unknown once the list meets `||` or ends
        self.changed = False  # the list changed directory: unknown after a closing `&`
        self.depth = 0  # open if/while/until/for/select/case bodies
        self.cases = 0  # open `case`: its parens are pattern syntax
        self.braces: list[list] = []  # open `{` groups: [conditional, changed directory, assigned]
        self.assigned: set[str] = set()  # variables the list assigned: unknown after a closing `&`
        self.deferred_vars: set[str] = set()  # `&&`-left assignments: unknown once the list ends


class DirectoryModel:
    """The directory each command of a token list runs in (None: unknown).

    Every command is seen once, in order, by one set of rules (`commands()` here and
    `git_guard.parse_git_actions` both read `at(index)`):

    - `(` saves the state and the matching `)` restores it, so a subshell, `$(...)` and
      `<(...)` never leak a `cd`; inside `case ... esac` parens are pattern syntax;
    - known: the `cd` that starts an and-or list (`cd X || exit 1`), the rest of an `&&`
      chain after a `cd`, a `{ ...; }` group, and `builtin cd` / `command cd` / `time cd`
      (the exact word `cd`, `pushd` or `popd`: `CD` and `/usr/bin/cd` move nothing);
    - unknown: a `cd` after `||`; one after `&&` once the list meets `||` or ends; one in a
      pipeline, in a list ended by `&`, in an if/while/until/for/select/case body or in a
      group that only runs conditionally; an `eval` whose text changes directory;
    - the paren stack is not trusted when a quoted or escaped operator character, or one
      inside `${...}`, came out as a bare operator (`Tokens.quoted_operators`, also an
      unescaped `find -exec ... \\;`): parens neither save nor restore and every `cd` makes
      the directory unknown;
    - a function (`f() {`, `function f`, `f ( ) {`, in any layout) runs where it is called,
      which the model does not follow: once the text defines one, and a `cd` appears after
      the definition starts, everything from the definition on is unknown;
    - an absolute (or `~`) target that exists makes the directory known again;
    - a variable an earlier segment set to a literal path (`S=/repo; cd $S`, `export S=...`)
      is known to a `cd`/`pushd` target and a `-C` value (`variables_at`), under the same
      certainty rules as a `cd`: an assignment that may not have run, a later non-literal
      assignment, `read`, `unset`, `eval` or `source` make it unknown, a subshell scopes it,
      and a prefix assignment (`S=/x cd $S`) does not count. Everything after a function
      definition has no known variables. A quoted `'~/x'` value is expanded like an
      unquoted one.

    Not modelled: a sourced file's `cd`, `CDPATH`, `pushd +N`, `cd ~-`,
    `C=cd; $C X`, `trap 'cd X' DEBUG` and `eval "$X"`. Also not modelled, each a real
    change of directory or variable the table misses: an element or nameref assignment in
    a segment of its own words (`S[0]=x A=M`, whose `A` is only the second word's), a nameref
    (`declare -n R=S; R=M`), a subscript that holds a bracket (`S[a[0]]=M`) and a quoted
    declaration (`declare 'S[0]=M'`).

    The words after a `$(...)`, `<(...)` or `>(...)` continue the command it sits in, as
    `commands()` reads them: they are arguments (`echo $(x) cd D` moves nothing), or a command
    when every word before the substitution only assigns (`X=$(x) cd D` is a `cd`). A substitution
    that expands to nothing makes them a command all the same (`$(true) cd D`), and so does a
    backtick word in command position: where the two readings disagree the directory is unknown.
    """

    def __init__(self, tokens: list[str], workdir: str | None, untrusted: bool = False) -> None:
        self.tokens = tokens
        self.untrusted = untrusted or getattr(tokens, "quoted_operators", False)
        self.dirs: list[str | None] = [workdir] * (len(tokens) + 1)
        self.variables: dict[str, str | None] = {}
        self.tables: list[dict[str, str | None]] = [self.variables] * (len(tokens) + 1)
        self.current = workdir
        self.either_depth = 0  # `either_reading`s open inside one another
        self.scan()
        self.dirs[len(tokens)] = self.current
        head = self.function_head()
        if head is not None:
            self.tables[head:] = [NO_VARIABLES] * (len(self.tables) - head)
            if any(DIRECTORY_CHANGE.search(word) for word in tokens[head:]):
                self.dirs[head:] = [None] * (len(self.dirs) - head)

    def at(self, index: int) -> str | None:
        """The directory of the command that holds token `index`."""
        return self.dirs[index]

    def variables_at(self, index: int) -> dict[str, str | None]:
        """The variables known to be a literal path where the command at token `index` runs."""
        return self.tables[index]

    def forget(self, names: set[str]) -> None:
        if names & self.variables.keys() or "HOME" in names:
            kept = {k: v for k, v in self.variables.items() if k not in names}
            self.variables = {**kept, "HOME": None} if "HOME" in names else kept

    def may_not_run(self, scope: "Scope", previous: str | None, following: str | None) -> bool:
        return bool(
            self.untrusted
            or scope.depth
            or previous == "||"
            or previous in PIPES
            or following in PIPES
            or any(group[0] for group in scope.braces)
        )

    def assign(
        self, name: str, value: str, scope: "Scope", previous: str | None, following: str | None
    ) -> None:
        """`NAME=value` as a segment of its own, or an argument of `export`."""
        scope.assigned.add(name)
        for group in scope.braces:
            group[2].add(name)
        literal = literal_value(value)
        if literal is None or self.may_not_run(scope, previous, following):
            self.forget({name})
            return
        self.variables = {**self.variables, name: literal}
        if previous == "&&":
            scope.deferred_vars.add(name)

    def function_head(self) -> int | None:
        """Start of the segment of the first function definition (`f()`, `function f`)."""
        tokens = self.tokens
        for index, token in enumerate(tokens):
            if (
                token == "()"
                or (token == "(" and tokens[index + 1 : index + 2] == [")"])
                or (token == "function" and (index == 0 or tokens[index - 1] in SEPARATORS | {"{", "}"}))
            ):
                while index and tokens[index - 1] not in SEPARATORS:
                    index -= 1
                return index
        return None

    def scan(self) -> None:
        tokens = self.tokens
        high = len(tokens)
        scope = Scope()
        saved: list[tuple[str | None, Scope, dict[str, str | None]]] = []
        # per open `(`: None for a subshell, else what the words after its `)` are (`AFTER_*`)
        substitutions: list[tuple[str, int] | None] = []
        kind = AFTER_COMMAND  # what the words after a substitution in the last segment would be
        continuation: str | None = None  # set by a substitution's `)` for the next segment
        previous: str | None = None
        index = 0
        while index < high:
            token = tokens[index]
            self.dirs[index] = self.current
            if token in SEPARATORS:
                index += 1
                if token in {"(", ")"}:
                    previous = ";"
                    continuation = None
                    if scope.cases or self.untrusted:
                        continue
                    if token == "(":
                        substitutions.append((kind, index) if opens_substitution(tokens, index - 1) else None)
                        saved.append((self.current, scope, self.variables))
                        scope = Scope()
                    elif saved:
                        self.current, scope, self.variables = saved.pop()
                        previous = ")"
                        continuation = None
                        opened = substitutions.pop() if substitutions else None
                        if opened:
                            continuation = opened[0]  # `$(echo x >&2) cd D` prints nothing: no body is trusted
                    continue
                continuation = None
                if (token == "||" or token in LIST_END) and scope.deferred:
                    self.current = None
                if token == "&" and scope.changed:
                    self.current = None
                if (token == "||" or token in LIST_END) and scope.deferred_vars:
                    self.forget(scope.deferred_vars)
                if token == "&":
                    self.forget(scope.assigned)
                if token == "||" or token in LIST_END:
                    scope.deferred = False
                    scope.deferred_vars = set()
                if token in LIST_END and not (scope.braces or scope.depth):
                    scope.changed = False  # a `;` inside a body does not end the list around it
                    scope.assigned = set()
                previous = token
                continue
            end = index
            while end < high and tokens[end] not in SEPARATORS:
                end += 1
            self.dirs[index:end] = [self.current] * (end - index)
            self.tables[index:end] = [self.variables] * (end - index)
            words = tokens[index:end]
            kind = after_substitution(words, continuation)
            following = tokens[end] if end < high else None
            if continuation == AFTER_ARGUMENT:
                pass  # `echo $(x) cd D`: arguments of a command that is there whatever `$(x)` prints
            elif continuation == AFTER_EITHER:
                # `$(true) cd D`: arguments when the substitution prints a word, a command when it
                # prints nothing: both readings count
                self.either_reading(words, scope, previous, following)
            else:
                self.command(words, scope, previous, following)
            continuation = None
            index = end

    def either_reading(self, words: list[str], scope: Scope, previous: str | None, following: str | None) -> None:
        """Apply `words` as a command although they may also be arguments: a word before them
        expanded to nothing (`$(true) cd D`, `` `true` cd D``) or did not. The shell is where
        the command reading leaves it or where it was, so a directory or a variable the two
        readings do not agree on is unknown."""
        directory, variables = self.current, self.variables
        if self.either_depth >= EITHER_DEPTH_LIMIT:
            # `$X command $X command ... cd D`: past the limit nothing is followed
            self.current, self.variables = None, NO_VARIABLES
            return
        self.either_depth += 1
        try:
            self.command(words, scope, previous, following)
        finally:
            self.either_depth -= 1
        if self.current != directory:
            self.current = None
        self.forget(
            {name for name in variables.keys() | self.variables.keys() if variables.get(name, ()) != self.variables.get(name, ())}
        )

    def command(self, words: list[str], scope: Scope, previous: str | None, following: str | None) -> None:
        """Apply one segment."""
        if scope.cases and words[0] != "case" and (
            following == ")" or (following == "|" and words[0] in CLOSES_BODY)
        ):
            return  # a case pattern, whatever it spells
        conditional = previous in {"&&", "||"} | PIPES
        plain = drop_redirections(words)
        redirected = len(plain) != len(words)
        words = plain
        position = 0
        keyword = True  # only keywords and prefixes of keywords so far
        assignments: list[str] = []
        while position < len(words):
            word = words[position]
            if is_assignment(word):
                assignments.append(word)
                position += 1
                keyword = False
            elif "+=" in word and word.partition("+=")[0].isidentifier():
                self.forget({word.partition("+=")[0]})  # an append is not a literal
                position += 1
                keyword = False
            elif keyword and word in STARTS_LIST:
                position += 1
            elif word == "time":
                position += 1
                position += words[position : position + 1] == ["-p"]
            elif keyword and word in OPENS_BODY:
                scope.depth += 1
                scope.cases += word == "case"
                if word in {"for", "select", "case"}:
                    if word != "case":
                        self.forget(set(words[position + 1 : position + 2]))
                    return
                position += 1
            elif position == 0 and word in CLOSES_BODY:
                scope.depth = max(scope.depth - 1, 0)
                scope.cases = max(scope.cases - (word == "esac"), 0)
                return
            elif keyword and word == "{":
                scope.braces.append([conditional, False, set()])
                position += 1
            elif keyword and word == "}" and not scope.braces:
                position += 1  # the rest of an expansion the lexer cut (`${X:-$(true)} cd D`): no group closes
                keyword = False
            elif keyword and word == "}":
                if scope.braces:
                    group = scope.braces.pop()
                    if group[1] and following in {"&"} | PIPES:
                        self.current = None
                    if following in {"&"} | PIPES:
                        self.forget(group[2])
                    if scope.braces:
                        scope.braces[-1][1] |= group[1]
                        scope.braces[-1][2] |= group[2]
                return
            elif word in {"builtin", "command"}:
                position += 1
                keyword = False
                while position < len(words) and words[position].startswith("-"):
                    if words[position] in {"-v", "-V"}:
                        return  # `command -v cd` only looks the name up
                    position += 1
            else:
                break
        if position >= len(words):
            # only assignments: one that starts a bare segment is recorded, one after a
            # keyword (`then S=x`, `{ S=x`) or with a redirection is not certain
            certain = position == len(assignments) and not redirected
            for word in assignments:
                name, _, value = word.partition("=")
                if certain:
                    self.assign(name, value, scope, previous, following)
                else:
                    self.forget({name})
            return
        for word in assignments:  # a prefix assignment is the command's own, unless it is cut
            if "`" in word:
                self.forget({word.partition("=")[0]})
        name = words[position]
        if "`" in name or may_vanish(name):
            # `` `true` cd D``, `$X cd D`: a word that expands to nothing leaves the rest the
            # command; a run of them is skipped at once (`$X $Y cd D`), not one reading each
            after = position
            while after < len(words) and (
                "`" in words[after]
                or may_vanish(words[after])
                or (after > position and words[after][:1] in "-+" and len(words[after]) > 1)
            ):
                # (an option word after an empty one: `command $X -p cd D` is `command -p cd D`)
                word = words[after]
                closes = after == position and word.endswith("`") and not word.startswith("`")
                if word.count("`") % 2 and not closes:  # the span runs on to the word that closes it
                    after = next((i for i in range(after + 1, len(words)) if words[i].count("`") % 2), len(words))
                after += 1  # (`` true` cd D`` closes a span an earlier segment opened)
            rest = words[after:]
            if rest:
                self.either_reading(rest, scope, previous, following)
        for alias in sorted(may_be(name, DIR_COMMANDS)):
            # `${X}cd D`, `{c,}d D`: the word may come out as a directory command
            self.either_reading([alias] + words[position + 1 :], scope, previous, following)
        element = ELEMENT_ASSIGNMENT.match(name)
        if element:
            self.forget({element.group(1)})  # `S[0]=x`
        args = words[position + 1 :]
        if name in ASSIGNING:
            for word in args:
                if is_assignment(word):
                    self.assign(*word.partition("=")[::2], scope, previous, following)
        elif name in FORGETTING or (name == "printf" and "-v" in args):
            self.forget(set(args))
        if name in CLEARING:
            self.variables = NO_VARIABLES
        if name == "eval":
            if DIRECTORY_CHANGE.search(" ".join(args)):
                self.current = None
        elif name in DIR_COMMANDS:
            if name == "popd" or (name == "pushd" and not has_dir_target(args)):
                new = None  # the directory stack is not tracked
            else:
                new = advance_dir(self.current, args, self.variables)
            scope.changed = True
            for group in scope.braces:
                group[1] = True
            if self.may_not_run(scope, previous, following):
                self.current = None
            else:
                self.current = new
                scope.deferred = scope.deferred or previous == "&&"


def unresolved_dir(text: str, workdir: str | None) -> str | None:
    """Where an unparseable or too-deeply nested command runs.

    The starting directory when nothing in it changes directory; otherwise
    unknown (None), so a caller blocks rather than inherit the starting repo.
    """
    return None if DIRECTORY_CHANGE.search(text) else workdir
