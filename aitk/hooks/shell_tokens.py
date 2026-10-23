"""The shell tokenizer the PreToolUse hooks share.

Lifted from the review gate so the git guard and the review gate read a Bash
command the same way. `commands()` walks a command string and yields every
simple command it can see, in order, with its wrapper-stripped argv:

- separators: newlines, `;`, `&&`, `||`, `|`, `&`, `|&` and parentheses;
- here-document bodies are skipped and comments dropped;
- leading `NAME=value` assignments are collected, not executed;
  `include_assignments=True` also preserves assignment-only and outer
  nested-prefix evidence, recognizes literal `NAME+=value` (stored under the
  raw key `NAME+`, an append, never a replacement value), unwraps `builtin`,
  and drops redirections;
- function-definition heads (`f()`, `function f`) are dropped, so the body
  of `echo() { gh pr ready 12; }` is seen whatever the function is named;
- behind a head this module does not know (`setsid`, `uv run`, `flock`,
  `watch`, `find -exec`), the rest of an argv is walked again from a later
  `env`, shell or `eval` word, so a wrapper cannot hide the command it runs:
  the override scan does it for every head, the default traversal from EVERY
  later `gh`, `git`, shell, `env` or `eval` word (an argument such as
  `flock /tmp/gh gh pr merge 12` cannot hide the real one) and from the string
  after a later `-c`, and not behind `gh`, `git` or a command that only prints
  its words (`INERT_HEADS`);
- text `git` itself runs is NOT walked or resolved (block on sight): the words
  after `git rebase -x`/`--exec`, `git bisect run`, `git submodule foreach` and
  `git for-each-repo` (its options skipped),
  and any segment that carries an inline git alias (`-c alias.NAME=...`,
  `--config-env=alias.NAME=VAR`, a `GIT_CONFIG_KEY_n=alias.NAME` assignment, a
  bare `alias.NAME=...` word after `-c` or in a segment with a `git` word,
  `git config alias.NAME ...`), are only checked for a MENTION of a gated
  operation (`mentions_gated`). A mention is yielded as `unreadable`; no alias
  is looked up, so a builtin and an alias are not told apart (`git -c
  alias.st=status st` is an ordinary command, `git -c alias.rebase=status
  rebase -x "gh pr merge 12"` is not; a bare `alias.NAME` word is no alias:
  `grep alias.x`, `gh pr view alias.cleanup`, `git push origin alias.cleanup`);
- a dashed git entry point is `git` plus its subcommand (`git-push`, a path
  such as `$(git --exec-path)/git-rebase`; `submodule--helper` reads as
  `submodule`), for `git_runs_text` and the callers that look for a git
  command (`git_argv`), but only for a name git itself installs
  (`GIT_ENTRY_POINTS`). Any other `git-*` head (`./git-run`, `git-x`,
  `/opt/x/git-wrap`) is an ordinary executable: it gets the wrapper rescan like
  any unknown head, so `./git-run gh pr merge 12` is seen;
- wrappers are stripped with their own options: `env`, `timeout`, `nohup`,
  `xargs`, `nice`, `ionice`, `stdbuf`, `sudo`, `command`, `exec`, `time`;
- `sh -c`/`bash -c` payloads, `eval` arguments, `env -S` strings and the bodies
  of `$(...)` and backtick substitutions are walked as nested commands.

Known limits (this is a tripwire, not a shell sandbox): command matching is
static, so a `cd` inside a conditional or a subshell counts as taken, shell
functions and aliases are not expanded here, and a command nested deeper than
DEPTH_LIMIT or one that does not tokenize is yielded as `unresolved` for the
caller to decide. Rescanning a tail and scanning a `$(...)` or backtick body
cost the characters they read, against MAX_TAIL_CHARS for the whole
`commands()` call: a segment that would pass it is yielded as one `unreadable`
command with no known directory, and so is every later segment that would
read more. An unreadable command is also `unresolved`, but its text cannot be
trusted to show what runs (the budget is spent, or it mentions a gated
operation next to an alias or in text git runs): a caller must treat it as
unknown whatever the text says. What is charged to the budget: the characters of
each rescanned tail, of each string a later `-c` word hands to a shell, and of
each `$(...)` or backtick body. What is not: the first tokenize of the command,
and the payload of `sh -c`, `eval` and `env -S`, which is walked (tokenized) as a
part of the text it came from, at most DEPTH_LIMIT levels deep. Those nested
walks share the `Walk` of the call that started them, so the tails and bodies
they rescan come out of the same MAX_TAIL_CHARS. Not covered, by design: config values and tool
options other than aliases that make git run a shell (`core.pager`,
`credential.helper`, `difftool -x`, `sequence.editor`, ...), and
`GIT_CONFIG_*` exported by an earlier command. `git -C` is followed lexically
(`os.path.normpath`: no symlink resolution), at most
MAX_DIR_HOPS times; a value with `$`, `~`, a backtick, a glob character (`*?[`), a tab
or a newline, more hops, `--git-dir`, `--work-tree`, `GIT_DIR` and `GIT_WORK_TREE` leave
the directory unknown (None). So does a `cd` target with `$`, a backtick, a glob
character, a tab or a newline, except the one substitution read on purpose:
`cd "$(git rev-parse --show-toplevel)"` (unquoted, or in backticks) is the git top
level of the current directory.

Operator runs: shlex returns a run of operator characters (`);`, `;(`, `&&(`, `)|`,
`f()(`) as one token, so `tokenize` splits each by maximal munch into the shell
operators it holds (redirections such as `>&` and `&>>` stay whole). A quoted word made
only of operator characters (`'));'`) is split too: an accepted over-block. Heads are
compared without case (`GIT`, `Gh`): the filesystem may ignore it. `deadline()` is the
in-process time limit every hook parses under (a hook past its own timeout fails open).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import functools
import os
import re
import shlex
import signal
import subprocess
from typing import Iterator


class DeadlineExceeded(BaseException):
    """Raised from the SIGALRM handler of `deadline()`.

    A BaseException, so no `except Exception` inside a parse can swallow it.
    """


@contextlib.contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """Raise DeadlineExceeded in the calling thread once `seconds` have passed.

    A PreToolUse hook that outlives its `timeout` in hooks/hooks.json FAILS OPEN
    (the tool call runs), so every hook parses under a deadline of its own, below
    that timeout, and its caller decides what an expiry means (block). The timer is
    disarmed and the previous handler restored on the way out. A `subprocess.run`
    in flight is killed by the exception it raises through. Main thread only.
    """

    def expire(_signum: int, _frame: object) -> None:
        raise DeadlineExceeded()

    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}"}
SIMPLE_WRAPPERS = {"command", "exec", "nohup", "time"}
DEPTH_LIMIT = 3
# Characters the rescan tails of one `commands()` call may tokenize in all. A long
# run of rescan words (`true sh sh sh ...`) otherwise costs a tail per word, each
# as long as the rest of the command, and the cost is in characters (a few words
# around one 100 KB word), not words.
MAX_TAIL_CHARS = 100_000
MAX_DIR_HOPS = 16
# A directory word whose real value this module cannot know: a variable, tilde or
# substitution the shell expands, a glob character (`*?[` pick a directory by pattern),
# or a newline or tab (the line-based callers cannot carry one: the pre-push shell
# reads the directory back with `read`, which strips a trailing tab).
UNKNOWN_PATH = re.compile(r"[$~`\n\t*?\[]")
# The same for a `cd` target, except `~`, which `advance_dir` expands the way the shell does.
UNKNOWN_CD_TARGET = re.compile(r"[$`\n\t*?\[]")
# The one substitution `advance_dir` resolves instead of leaving unknown: the git top level
# of the current directory. Exactly this text, in the `$(...)` or the backtick spelling.
TOPLEVEL_SUBSTITUTIONS = ("$(git rev-parse --show-toplevel)", "`git rev-parse --show-toplevel`")

HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([^\s'\"<>;|&()\\]+)\2")
WORD_START = " \t\n;&|("
BACKTICK = re.compile(r"`([^`]*)`")

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
# The override scan only: redirection operators as the tokenizer splits them,
# each followed by its target word, and the words that restart the scan when
# they appear later in an argv (behind a wrapper this module does not know).
REDIRECTIONS = {">", ">>", "<", "<<", "<<<", "<>", ">&", "<&", ">|", "&>", "&>>"}
REDIRECTION_FD = re.compile(r"\d+|\{[A-Za-z_]\w*\}")
RESCAN_WORDS = SHELLS | {"env", "eval"}
# The default traversal rescans from a later gh or git word too: `setsid gh pr
# merge 12` (or `uv run`, `flock`, `chronic`, `watch`, `find -exec`, `builtin`)
# is a wrapper this module does not know, and the checks that read `commands()`
# must still see the command it runs. A command that only prints its words
# (INERT_HEADS) is not rescanned, and gh and git themselves take the rest of the
# line as their own arguments. A later `-c` word hands the string after it to a
# shell (`flock /tmp/x -c '...'`, `su -c '...'`), so that string is walked too.
DEFAULT_RESCAN_WORDS = RESCAN_WORDS | {"gh", "git"}
# Every git global option that takes its value as the next word (`--opt=value` is one
# word; `--exec-path` alone prints a path and takes none).
GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix", "--attr-source"}
INERT_HEADS = {
    "echo", "printf", "print", "cat", "less", "more", "head", "tail", "wc", "ls", "grep", "egrep",
    "fgrep", "rg", "ag", "ack", "man", "which", "type", "whereis", "diff", "cmp",
}
NO_RESCAN_HEADS = INERT_HEADS | {"gh", "git"}

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


PUNCTUATION = frozenset("();<>|&")
# One shell operator at a time, longest first (maximal munch). `()` stays whole: it is the
# function-definition head `f()`. Redirection operators keep their spelling (`>&`, `&>>`).
OPERATOR = re.compile(r"&>>|<<<|&&|\|\||>>|<<|<&|>&|&>|<>|>\||\|&|\(\)|.")


def split_operators(token: str) -> list[str]:
    """A token made only of operator characters, split into the operators it holds.

    shlex (`punctuation_chars`) returns a whole run as one token: `);`, `;(`, `&&(`,
    `)&&`, `)|`, `f()(`. Left fused, the command after the run reads as arguments of the
    one before it. A quoted all-operator word (`'));'`) reads the same: an accepted over-block.
    """
    if token and all(char in PUNCTUATION for char in token):
        return OPERATOR.findall(token)
    return [token]


def tokenize(text: str) -> list[str]:
    """Shell words and operators; raises ValueError on unbalanced quotes."""
    lexer = shlex.shlex(split_lines(text), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [part for token in lexer for part in split_operators(token)]


def join_toplevel(tokens: list[str]) -> list[str]:
    """Rejoin `$ ( git rev-parse --show-toplevel )` and its backtick spelling into one word.

    The lexer breaks the unquoted forms at the parentheses (or the backticks' spaces); quoted,
    they are already one word. All three read as the same word, which `advance_dir` resolves.
    """
    joined: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index : index + 6] == ["$", "(", "git", "rev-parse", "--show-toplevel", ")"]:
            joined.append(TOPLEVEL_SUBSTITUTIONS[0])
            index += 6
        elif tokens[index : index + 3] == ["`git", "rev-parse", "--show-toplevel`"]:
            joined.append(TOPLEVEL_SUBSTITUTIONS[1])
            index += 3
        else:
            joined.append(tokens[index])
            index += 1
    return joined


def is_assignment(token: str, *, include_append: bool = False) -> bool:
    name, sep, _ = token.partition("=")
    if include_append and name.endswith("+"):
        name = name[:-1]
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


def skip_options(wrapper: str, rest: list[str], effects: Effects, *, scan: bool = False) -> list[str]:
    """Skip a wrapper's own options and assignments; return what it runs."""
    valued = WRAPPER_VALUE_FLAGS.get(wrapper, set())
    while rest:
        arg = rest[0]
        option = env_option(arg, rest) if wrapper == "env" and arg.startswith("-") else None
        if is_assignment(arg, include_append=scan):
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


def drop_redirections(segment: list[str]) -> list[str]:
    """A segment's words without its redirections (operator, target and fd)."""
    words: list[str] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        if token in REDIRECTIONS:
            index += 2
        elif index + 1 < len(segment) and segment[index + 1] in REDIRECTIONS and REDIRECTION_FD.fullmatch(token):
            index += 1
        else:
            words.append(token)
            index += 1
    return words


def strip_prefixes(segment: list[str], *, scan: bool = False) -> tuple[list[str], Effects]:
    """Drop assignments, keywords and wrappers; return (argv, effects).

    A function-definition head is always dropped (the body runs when the
    function is called). `scan` is the override scan: it also recognizes
    `NAME+=value` (stored under the raw key `NAME+`), strips a `builtin`
    prefix, and ignores redirections wherever they stand.
    """
    effects = Effects()
    rest = drop_redirections(segment) if scan else list(segment)
    while rest:
        head = head_name(rest[0])
        if is_assignment(rest[0], include_append=scan):
            name, _, value = rest[0].partition("=")
            effects.assignments[name] = value
            rest = rest[1:]
        elif head in KEYWORDS:
            rest = rest[1:]
        elif head in WRAPPERS or (scan and head == "builtin"):
            rest = skip_options(head, rest[1:], effects, scan=scan)
        elif rest[1:3] == ["()", "{"]:
            rest = rest[3:]  # `f() { ...`: the body runs when f is called (a quoted `'()'` argument is no head)
        elif head == "function" and len(rest) > 1:
            rest = rest[3:] if rest[2:3] == ["()"] else rest[2:]
        else:
            break
    return rest, effects


@dataclass
class Payload:
    """A string a shell is handed, to be walked as a command in `workdir` (None: unknown)."""

    text: str
    workdir: str | None
    rescan: bool = False


QUOTING = re.compile(r"['\"\\`]")
GATED_BARE = re.compile(r"\bpush\b|\bpr\s+(?:ready|merge|create|new)\b")
WORD_GH = re.compile(r"\bgh\b", re.I)
WORD_GIT = re.compile(r"\bgit\b", re.I)
WORD_PR = re.compile(r"\bpr\b")
WORD_PUSH = re.compile(r"\bpush\b")
GIT_DASHED = re.compile(r"git-(.+)")
# `git submodule--helper foreach` runs what `git submodule foreach` runs.
GIT_SUBCOMMANDS = {"submodule--helper": "submodule"}
# The dashed entry points git itself installs (`git --list-cmds=main`, plus the old
# aliases): only these read as `git SUBCOMMAND`. Any other `git-*` word (`./git-run`,
# `git-x`, `/opt/x/git-wrap`) is an ordinary executable that gets the normal wrapper rescan.
GIT_ENTRY_POINTS = frozenset(
    """add am annotate apply archive backfill bisect blame branch bugreport bundle cat-file
    check-attr check-ignore check-mailmap check-ref-format checkout checkout--worker
    checkout-index cherry cherry-pick clean clone column commit commit-graph commit-tree config
    count-objects credential credential-cache credential-cache--daemon credential-osxkeychain
    credential-store daemon describe diagnose diff diff-files diff-index diff-pairs diff-tree
    difftool difftool--helper fast-export fast-import fetch fetch-pack filter-branch
    fmt-merge-msg for-each-ref for-each-repo format-patch fsck fsck-objects fsmonitor--daemon gc
    get-tar-commit-id grep gui gui--askpass gui--askyesno hash-object help history hook
    http-backend http-fetch http-push imap-send index-pack init init-db interpret-trailers
    last-modified log ls-files ls-remote ls-tree mailinfo mailsplit maintenance merge merge-base
    merge-file merge-index merge-octopus merge-one-file merge-ours merge-recursive
    merge-recursive-ours merge-recursive-theirs merge-resolve merge-subtree merge-tree mergetool
    mergetool--lib mktag mktree multi-pack-index mv name-rev notes p4 pack-objects pack-redundant
    pack-refs patch-id pickaxe prune prune-packed pull push quiltimport range-diff read-tree
    rebase receive-pack reflog refs remote remote-ext remote-fd remote-ftp remote-ftps
    remote-http remote-https repack replace replay repo request-pull rerere reset restore
    rev-list rev-parse revert rm send-email send-pack sh-i18n sh-i18n--envsubst sh-setup shell
    shortlog show show-branch show-index show-ref sparse-checkout stage stash status stripspace
    submodule submodule--helper subtree switch symbolic-ref tag unpack-file unpack-objects
    update-index update-ref update-server-info upload-archive upload-archive--writer
    upload-pack var verify-commit verify-pack verify-tag version web--browse whatchanged
    worktree write-tree""".split()
)


def words_in_order(text: str, *patterns: re.Pattern[str]) -> re.Match[str] | None:
    """The match of the last pattern when each one matches after the end of the previous one.

    Linear in the text: every pattern is searched once, from where the one before it
    ended (`gh`, then `pr`, then `merge`), where a single `gh.*pr.*merge` expression
    backtracks across the whole text from every start.
    """
    match = None
    position = 0
    for pattern in patterns:
        match = pattern.search(text, position)
        if match is None:
            return None
        position = match.end()
    return match


def head_name(word: str) -> str:
    """The basename of a command head, lower-cased (`GIT`, `/usr/bin/Gh` read as `git`, `gh`)."""
    return os.path.basename(word).lower()


def is_git_word(word: str) -> bool:
    """`git`, or a dashed entry point git installs (`git-push`, `/usr/lib/git-core/git-rebase`).

    Any other `git-*` word (`./git-run`, `git-x`) is an ordinary executable, not git.
    The head is compared without case: `GIT` runs git on a case-insensitive filesystem.
    """
    name = head_name(word)
    if name == "git":
        return True
    dashed = GIT_DASHED.fullmatch(name)
    return dashed is not None and dashed.group(1) in GIT_ENTRY_POINTS


def git_argv(argv: list[str]) -> list[str] | None:
    """`argv` as `git SUBCOMMAND ...` when it runs git, else None.

    A dashed entry point (`git-push origin x`, `$(git --exec-path)/git-push`) is
    `git push origin x`; the subcommand name keeps its spelling (see `GIT_SUBCOMMANDS`).
    """
    if not argv:
        return None
    name = head_name(argv[0])
    if name == "git":
        return argv
    dashed = GIT_DASHED.fullmatch(name)
    return ["git", dashed.group(1), *argv[1:]] if dashed and dashed.group(1) in GIT_ENTRY_POINTS else None


def unquoted(text: str) -> str:
    """`text` as the shell reads it once quoting is gone.

    Backslash-newline pairs are joined first, then quote characters, backslashes and
    backticks are removed, so `"gh''" pr merge`, `g\\h pr ready` and `pu\\<newline>sh` read
    as written. The one helper behind `mentions_gated` and `mentions_push`.
    """
    return QUOTING.sub("", text.replace("\\\n", ""))


def mentions_push(text: str) -> bool:
    """Whether `text`, with its quoting removed (`unquoted`), has a `push` word."""
    return WORD_PUSH.search(unquoted(text)) is not None


def mentions_gated(text: str) -> bool:
    """Whether `text` could name a gated operation (`gh pr ...`, `git push`, `pr merge`, ...).

    The quoting is removed first (`unquoted`), so `"gh''" pr merge`, `g\\h pr ready` and
    `gh p\\<newline>r create` read as written. A plain search over the text, never a
    parse: it over-matches (`make push`, a filename `push`, `gh pr view`) on purpose.
    """
    text = unquoted(text)
    return words_in_order(text, WORD_GH, WORD_PR) is not None or GATED_BARE.search(text) is not None


# A word that configures an inline git alias. These carry the key in the word and
# need no context: `-calias.x=...`, `--config-env=alias.x=VAR`, and the
# `GIT_CONFIG_KEY_n=alias.x` / `GIT_CONFIG_PARAMETERS=...` assignments.
PREFIXED_ALIAS = re.compile(r"^(?:-c|--config-env=|GIT_CONFIG_KEY_\d+=|GIT_CONFIG_PARAMETERS=.*)alias\.", re.I)
BARE_ALIAS = re.compile(r"^alias\.", re.I)
ALIAS_ASSIGNMENT = re.compile(r"^alias\.[^=]+=", re.I)


def sets_inline_alias(segment: list[str], configures: bool) -> bool:
    """Whether `segment` configures an inline git alias.

    A bare `alias.NAME` word is a name in `grep alias.x`, `grep -c alias.x docs`,
    `gh pr view alias.cleanup` or `git push origin alias.cleanup`, so it counts only
    as the value of `--config-env`, as the value of `-c` among git's own global options
    (before its subcommand: `git -C d -c alias.x x`; in `git grep -c alias.x docs` or
    `git log -c alias.x push` the `-c` is the subcommand's), as an `alias.NAME=...` word
    in a segment with a git word (`git`, a dashed entry point), or as any word of
    `git config` (`configures`). A `-c` in a segment without a git word (`g -c
    alias.x x`, `rg -c alias.x`) is no alias: an accepted limit.
    """
    has_git = any(is_git_word(word) for word in segment)
    first, last = git_global_region(segment)
    for index, word in enumerate(segment):
        if PREFIXED_ALIAS.match(word):
            return True
        if BARE_ALIAS.match(word) and (
            configures
            or (index > 0 and segment[index - 1] == "--config-env")
            or (first < index < last and segment[index - 1] == "-c")
            or (has_git and ALIAS_ASSIGNMENT.match(word))
        ):
            return True
    return False


def git_global_region(segment: list[str]) -> tuple[int, int]:
    """(first, end) indexes in `segment` of the global options after its first `git` word.

    Empty (0, 0) when there is none. A dashed entry point has no separate subcommand word
    (`git-push -c alias.x x`), so everything after it counts, as it always did. `-c` counts
    as an alias setting only inside this region.
    """
    for position, word in enumerate(segment):
        if is_git_word(word):
            start = position + 1
            if head_name(word) != "git":
                return start, len(segment)
            return start, start + git_globals(segment[start:], None)[1]
    return 0, 0


def git_runs_text(segment: list[str], rest: list[str]) -> list[str]:
    """The words of `segment` that make `git` run text, for a mention check.

    An inline alias anywhere in the segment gives the whole segment (the alias
    may be the builtin it shadows or a shell: nothing is looked up). Otherwise,
    for a `git` command (a dashed entry point too), the words `git rebase
    -x`/`--exec`, `bisect run`, `submodule foreach` and `for-each-repo` (the git
    command after its options) hand on. Empty when there is nothing to check.
    """
    argv = git_argv(rest)
    subcommand, tail = "", []
    if argv is not None:
        args = argv[1:]
        index = git_globals(args, None)[1]
        if index < len(args):
            subcommand, tail = GIT_SUBCOMMANDS.get(args[index], args[index]), args[index + 1 :]
    if sets_inline_alias(segment, subcommand == "config"):
        return segment
    if subcommand == "rebase":
        words: list[str] = []
        for position, arg in enumerate(tail):
            following = tail[position + 1] if position + 1 < len(tail) else ""
            if arg == "--":
                break
            if arg.startswith("--"):
                name, equals, value = arg.partition("=")
                if len(name) >= 4 and "--exec".startswith(name):
                    words.append(value if equals else following)
            elif arg.startswith("-") and "x" in arg[1:]:
                words.append(arg[arg.index("x", 1) + 1 :] or following)
        return words
    if subcommand == "bisect" and "run" in tail:
        return tail[tail.index("run") + 1 :]
    if subcommand == "submodule" and "foreach" in tail:
        return tail[tail.index("foreach") + 1 :]
    if subcommand == "for-each-repo":
        # `git for-each-repo --config=KEY [--keep-going] [--] GIT-COMMAND...`: git runs the
        # remaining words as a git command in each configured repository
        position = 0
        while position < len(tail):
            arg = tail[position]
            if arg == "--":
                position += 1
                break
            if not arg.startswith("-"):
                break
            name, equals, _ = arg.partition("=")
            # an abbreviation (`--conf`) takes its value as the next word without `=`
            position += 2 if not equals and len(name) >= 3 and "--config".startswith(name) else 1
        return tail[position:]
    return []


def git_globals(args: list[str], workdir: str | None, assignments: dict[str, str] | None = None) -> tuple[str | None, int]:
    """(the directory `git` works in, index of its subcommand) from its arguments after `git`.

    `-C` moves the directory lexically (`os.path.normpath`: no symlink resolution,
    no `~` expansion), at most MAX_DIR_HOPS times; more leave it unknown (None), as
    do `--git-dir`, `--work-tree`, `GIT_DIR` and `GIT_WORK_TREE`, and None stays None.
    A `-C` value the shell would expand (`$`, `~`, a backtick) or that holds a newline
    is unknown too, before any path arithmetic: `-C "$X/.."` is not the directory above
    a folder literally named `$X`.
    """
    directory = workdir
    if assignments and ("GIT_DIR" in assignments or "GIT_WORK_TREE" in assignments):
        directory = None
    hops = 0
    index = 0
    while index < len(args) and args[index].startswith("-"):
        arg = args[index]
        if arg == "-C" and index + 1 < len(args):
            hops += 1
            if hops > MAX_DIR_HOPS or UNKNOWN_PATH.search(args[index + 1]):
                directory = None
            elif directory is not None:
                directory = os.path.normpath(os.path.join(directory, args[index + 1]))
        elif arg in {"--git-dir", "--work-tree"} or arg.startswith(("--git-dir=", "--work-tree=")):
            directory = None
        index += 2 if arg in GIT_VALUE_FLAGS else 1
    return directory, index


def is_shell_command_flag(arg: str) -> bool:
    return arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]


@functools.lru_cache(maxsize=32)
def git_toplevel(path: str) -> str | None:
    """`git -C path rev-parse --show-toplevel`, or None when it fails (not a repository, no git)."""
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
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


def advance_dir(workdir: str | None, args: list[str]) -> str | None:
    """Follow `cd`/`pushd` so a check reads the repository the command runs in.

    A target the shell would expand (`$`, a backtick), a glob (`*?[`) or a target with a newline
    or a tab leaves the directory unknown (None); `~` is expanded here the way the shell does.
    The one substitution read instead is the git top level of the current directory
    (`TOPLEVEL_SUBSTITUTIONS`), which is that repository's root, or unknown outside one.
    """
    if workdir is None:
        return None
    target = next((arg for arg in args if not arg.startswith("-")), None)
    if target is None or target == "-":
        return workdir
    if target in TOPLEVEL_SUBSTITUTIONS:
        return git_toplevel(workdir)
    if UNKNOWN_CD_TARGET.search(target):
        return None
    path = os.path.expanduser(target)
    path = path if os.path.isabs(path) else os.path.join(workdir, path)
    return os.path.normpath(path) if os.path.isdir(path) else workdir


def inner_commands(text: str, walk: Walk) -> Iterator[str | None]:
    """Bodies of `$(...)` and backtick substitutions, wherever they are quoted.

    Every body costs the characters read to find it, charged to `walk`; None is
    yielded (once, and the generator ends) when the budget runs out.
    """
    for match in BACKTICK.finditer(text):
        if not walk.charge(len(match.group(0))):
            yield None
            return
        yield match.group(1)
    index = 0
    while True:
        start = text.find("$(", index)
        if start < 0:
            return
        depth, position = 1, start + 2
        while position < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[position], 0)
            position += 1
        if not walk.charge(position - start):
            yield None
            return
        yield text[start + 2 : position - 1 if depth == 0 else position]
        index = start + 2


def unresolved_dir(text: str, workdir: str | None) -> str | None:
    """Where an unparseable or too-deeply nested command runs.

    The starting directory when nothing in it changes directory; otherwise
    unknown (None), so a caller blocks rather than inherit the starting repo.
    """
    return None if DIRECTORY_CHANGE.search(text) else workdir


class Walk:
    """The characters one `commands()` call, nested walks included, may still read again."""

    def __init__(self) -> None:
        self.chars = MAX_TAIL_CHARS

    def charge(self, cost: int) -> bool:
        """Spend `cost` characters; False (and nothing left) when there are not enough."""
        if cost > self.chars:
            self.chars = 0
            return False
        self.chars -= cost
        return True


@dataclass
class Command:
    """One simple command as the shell would run it.

    `unresolved` is a command that did not tokenize or nests too deep, with its
    raw `text`. `unreadable` (also unresolved) is one whose text cannot show what
    runs: the work budget was spent, or git is handed text (next to an inline
    alias, or after `rebase -x`, `bisect run`, `submodule foreach`) that mentions
    a gated operation.
    """

    argv: list[str]
    assignments: dict[str, str]
    workdir: str | None
    unresolved: bool = False
    text: str = ""
    unreadable: bool = False

    @property
    def name(self) -> str:
        return os.path.basename(self.argv[0]) if self.argv else ""

    @property
    def is_gh(self) -> bool:
        """Whether the command is `gh`, whatever the case of its name (`GH` on a case-insensitive filesystem)."""
        return self.name.lower() == "gh"


def commands(
    text: str,
    workdir: str | None,
    depth: int = 0,
    inherited: dict[str, str] | None = None,
    *,
    include_assignments: bool = False,
    _walk: Walk | None = None,
    _rescanned: bool = False,
) -> Iterator[Command]:
    """Yield every command in `text`, in order, nested ones included.

    A command that does not tokenize, or nests deeper than DEPTH_LIMIT, is
    yielded once with `unresolved=True` and its raw text.

    `include_assignments=True` is the override scan, off for every other
    caller: an assignment-only segment is yielded as a `Command` with an empty
    argv and its assignments (also ahead of a nested payload, so an empty one
    cannot erase them), `NAME+=value` is recognized under the raw key `NAME+`,
    a `builtin` prefix and redirections are stripped, and the argv from a later
    `env`, shell or `eval` word is walked again as a nested command (so `echo
    env NAME=1` reads as an assignment: an over-match the override scan
    accepts). The default traversal instead rescans from every later `gh`,
    `git`, shell, `env` or `eval` word, and yields an unreadable command for a
    segment where git is handed text that mentions a gated operation.
    A tail the rescan itself produced (`_rescanned`) does not rescan again unless
    it changed directory: every later position is already a tail of its parent.
    """
    walk = _walk if _walk is not None else Walk()
    start = workdir
    inherited = dict(inherited or {})
    try:
        tokens = join_toplevel(tokenize(text))
    except ValueError:
        yield Command([], inherited, unresolved_dir(text, workdir), True, text)
        return
    for segment in segments(tokens):
        spent = False
        for inner in inner_commands(" ".join(segment), walk):
            if inner is None:
                spent = True
            elif depth >= DEPTH_LIMIT:
                yield Command([], {}, unresolved_dir(inner, workdir), True, inner)
            else:
                yield from commands(
                    inner, workdir, depth + 1, include_assignments=include_assignments, _walk=walk
                )
        rest, effects = strip_prefixes(segment, scan=include_assignments)
        if spent or (not include_assignments and mentions_gated(" ".join(git_runs_text(segment, rest)))):
            # Block on sight: the work budget is spent, or git is handed text (an inline
            # alias, `rebase -x`, `bisect run`, `submodule foreach`) that names a gated
            # operation. No directory is known and the text is not trusted.
            yield Command([], {}, None, True, " ".join(segment), True)
            continue
        assignments = {**inherited, **effects.assignments}
        target = workdir
        for value in effects.chdir:
            target = advance_dir(target, [value])
        nested = None
        if effects.split is not None:
            split = effects.split.replace("\\_", " ")
            nested = " ".join(["env", split] + [shlex.quote(arg) for arg in rest])
        elif rest and head_name(rest[0]) in SHELLS:
            flags = [i for i, arg in enumerate(rest[1:], 1) if is_shell_command_flag(arg)]
            if flags:
                payload = rest[flags[0] + 1 :]
                payload = payload[1:] if payload[:1] == ["--"] else payload  # `bash -c -- 'cmd'`
                if payload:
                    nested = payload[0]
        elif rest and head_name(rest[0]) == "eval":
            payload = rest[1:]
            nested = " ".join(payload[1:] if payload[:1] == ["--"] else payload)
        if nested is not None:
            if include_assignments and effects.assignments:
                yield Command([], dict(effects.assignments), target)
            if depth >= DEPTH_LIMIT:
                yield Command([], assignments, unresolved_dir(nested, target), True, nested)
            else:
                yield from commands(
                    nested, target, depth + 1, assignments, include_assignments=include_assignments, _walk=walk
                )
            continue
        positions: list[int] = []
        extra: list[Payload] = []
        if rest and (
            include_assignments or (head_name(rest[0]) not in NO_RESCAN_HEADS and not is_git_word(rest[0]))
        ):
            words = RESCAN_WORDS if include_assignments else DEFAULT_RESCAN_WORDS
            later = [
                i
                for i, word in enumerate(rest[1:], 1)
                if head_name(word) in words or (not include_assignments and is_git_word(word))
            ]
            # The override scan walks the first and lets the tail find the rest; the
            # default traversal exempts a gh or git head from rescanning, so a
            # matching word that is only an argument (`flock /tmp/gh gh pr merge`)
            # must not stand in for the later one that is the command.
            positions = later[:1] if include_assignments else later
            if _rescanned and target == start:
                positions = []  # every later position is already a tail of the parent
            if not include_assignments:
                # `flock /tmp/x -c 'gh pr merge 12'`, `su -c ...`: a later -c word hands
                # its string to a shell, whatever the wrapper is
                flag = next((i for i, arg in enumerate(rest[1:], 1) if is_shell_command_flag(arg)), None)
                payload = rest[flag + 1 :] if flag is not None else []
                payload = payload[1:] if payload[:1] == ["--"] else payload
                if payload:
                    extra.append(Payload(payload[0], target))
        if positions or extra:
            quoted = [shlex.quote(word) for word in rest]
            suffix = [0] * (len(rest) + 1)  # characters of the tail that starts at each word
            for number in range(len(rest) - 1, -1, -1):
                suffix[number] = suffix[number + 1] + len(quoted[number]) + 1
            cost = sum(suffix[position] for position in positions)
            cost += sum(len(payload.text) or 1 for payload in extra)
            if not walk.charge(cost):
                # past the work budget the segment is one unreadable command whose
                # directory is unknown, so a check fails safe instead of walking on
                yield Command([], {}, None, True, " ".join(quoted), True)
            else:
                scheduled = [Payload(" ".join(quoted[p:]), target, rescan=True) for p in positions]
                scheduled += extra
                visited: set[tuple[str, str | None]] = set()
                for payload in scheduled:
                    if (payload.text, payload.workdir) in visited:
                        continue
                    visited.add((payload.text, payload.workdir))
                    if depth >= DEPTH_LIMIT:
                        yield Command([], {}, unresolved_dir(payload.text, payload.workdir), True, payload.text)
                    else:
                        yield from commands(
                            payload.text,
                            payload.workdir,
                            depth + 1,
                            include_assignments=include_assignments,
                            _walk=walk,
                            _rescanned=payload.rescan and not include_assignments,
                        )
        if not rest:
            if include_assignments and effects.assignments:
                yield Command([], assignments, target)
            continue
        if head_name(rest[0]) in {"cd", "pushd"}:
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
    """An override is on unless unset, empty, `0`, `false`, `no` or `off`.

    The one truthy rule: hooks/pre-push-validate.sh spells the same set in bash.
    """
    return value is not None and value.strip().lower() not in {"", "0", "false", "no", "off"}
