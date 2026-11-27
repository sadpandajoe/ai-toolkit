"""The shell tokenizer the PreToolUse hooks share.

The git guard and the pre-push check read a Bash command through it.
`commands()` walks a command string and yields every
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
static, so shell functions and aliases are not expanded here, and a command
nested deeper than DEPTH_LIMIT or one that does not tokenize is yielded as
`unresolved` for the caller to decide. `DirectoryModel` decides the directory of
every command (it is what `commands()` and `git_guard.parse_git_actions` both
read): a subshell, `$(...)` and `<(...)` restore it, and a `cd` the model cannot
be sure ran leaves it unknown (None) until a subshell restores it or an absolute
`cd` re-anchors it: after `||`, after `&&` once the list ends, in a pipeline, in
a list ended by `&`, in an if/while/until/for/select/case body, an `eval` that
changes directory, and every `cd` in text where a quoted or escaped operator
character (or one in `${...}`) came out as a bare token, which includes an
unescaped `find -exec ... \\;`: an accepted over-block. A function runs where it is
called, which is not followed: once the text defines one and a `cd` appears after
the definition starts, everything from the definition on is unknown. So do `cd -`,
`popd` and a bare `pushd`: the previous directory and the directory stack are not
tracked. Only the exact words `cd`, `pushd` and `popd` move the shell (`CD` and
`/usr/bin/cd` do not). Callers block the decisions that need the directory. Not
modelled: a sourced file's `cd`, `CDPATH`, `pushd +N`, `cd ~-`,
`C=cd; $C X`, `trap 'cd X' DEBUG`, `eval "$X"`. Rescanning a tail and
scanning a `$(...)` or backtick body cost the characters they read, against MAX_TAIL_CHARS for the whole
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
level of the current directory. The other `$` read is a variable an earlier segment
set to a literal path (`S=/repo; cd $S`, `git -C $S`): `$NAME`, `${NAME}` or either
followed by `/rest`, and `$HOME` as `~`; `DirectoryModel.variables_at` holds the table,
under the certainty rules of a `cd`. Any other `$` (an unassigned variable, `$PWD`,
`${S:-x}`, `$S$T`) stays unknown. `git_globals` does not read the table: the pre-push
hook's `git -C $S` stays unknown.

A substitution is one word of the command it sits in: `commands()` reads `$(...)`, `<(...)`
and `>(...)` (`command_spans`) as the word `SUBSTITUTION_WORD` (glued to the text before its `$`)
and goes on with the words after its `)` in the same command, while the commands inside it are
yielded on their own. `Command.cut` marks a command with an unquoted substitution among its words, an
unclosed `$(`, or a backtick span (read folded and as it is: `readings`). With a quoted operator about
(`Tokens.quoted_operators`, also a `;`, `&` or `|` inside double quotes of their own within a
double-quoted `$(...)`) the paren stack and the merge are not trusted and callers read the text as well.

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
import os
import re
import shlex
import signal
from typing import Iterator

from shell_lex import (
    FdWord, KEYWORDS, SEPARATORS, SIMPLE_WRAPPERS, SUBSTITUTION_WORD, WORD_API, WORD_GH, WORD_GRAPHQL,
    WORD_PR, WORD_PUSH, command_spans, drop_redirections, is_assignment, join_toplevel, may_vanish,
    opens_substitution, tokenize, unquoted, words_in_order,
)
from shell_dirs import DirectoryModel, PIPES, hop_dir, unresolved_dir

# Re-exported: the git guard's modules, hooks/pre-push-validate.sh and the tests read these names through this module.
from shell_lex import (  # noqa: F401
    CURRENT_BRANCH_SUBSTITUTIONS, REDIRECTIONS, REDIRECTION_FD, Tokens, WORD_GIT, command_words,
    expand_ansi_c, may_be, quoted_substitution_separator,
)
from shell_dirs import UNKNOWN_CD_TARGET, advance_dir  # noqa: F401


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


SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
DEPTH_LIMIT = 3
# Characters the rescan tails of one `commands()` call may tokenize in all. A long
# run of rescan words (`true sh sh sh ...`) otherwise costs a tail per word, each
# as long as the rest of the command, and the cost is in characters (a few words
# around one 100 KB word), not words.
MAX_TAIL_CHARS = 100_000
MAX_DIR_HOPS = 16

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


def printed_heads(tokens: list[str], first: int, segment: list[str], rest: list[str]) -> list[tuple[str | None, list[str]]]:
    """What the shell may run when a substitution stands where the command word of `rest` does:
    (the substitution's text, the words after it): `` `echo gh pr` merge 12`` runs `gh pr merge
    12`. One pair per substitution that may be the command word: past a word that may
    expand to nothing (`$X $(echo gh pr merge 12)`, `$(true) $(echo ...)`) the next one may be.
    `rest` is `segment` past its prefixes, and `first` the index in `tokens` where `segment`
    starts."""
    texts: list[tuple[str | None, list[str]]] = []
    before = sum(word.count(SUBSTITUTION_WORD) for word in segment[: len(segment) - len(rest)])
    index = 0
    while index < len(rest):
        head = rest[index]
        if len(texts) >= PRINTED_HEAD_LIMIT:
            # past the limit, the rest is one text, read like text that did not parse
            texts.append((None, rest[index:]))
            break
        if head.startswith("`"):
            closing = index if head.count("`") >= 2 and head.endswith("`") else next(
                (k for k in range(index + 1, len(rest)) if rest[k].count("`") % 2), len(rest) - 1
            )
            span = " ".join(rest[index : closing + 1])
            match = BACKTICK.match(span)
            body = match.group(1) if match else span[1:]
            texts.append((body, rest[closing + 1 :]))
            index = closing + 1
            continue
        glued = head[: -len(SUBSTITUTION_WORD)] if head.endswith(SUBSTITUTION_WORD) else None
        if glued is not None and (not glued or may_vanish(glued)):
            body = substitution_body(tokens, first, before + head.count(SUBSTITUTION_WORD))
            texts.append((body, rest[index + 1 :]))
            before += head.count(SUBSTITUTION_WORD)
            index += 1
            continue
        if not may_vanish(head):
            break
        before += head.count(SUBSTITUTION_WORD)
        index += 1
    return texts


PRINTED_HEAD_LIMIT = 8  # substitutions in a row read as the command word, each with the words after it
LOOKUP_BODY = re.compile(r"\s*(?:command\s+-[vV]|which|type\s+-[pP])\s+([\w./+-]+)\s*")
CERTAIN_OPTIONS = re.compile(r"-[neE]+")


def printed_words(body: str) -> str | None:
    """The words a substitution body surely prints: an `echo` of literal words, with nothing that
    could change or redirect its output (no expansion, escape, glob, redirection or other
    command), else None."""
    if any(char in body for char in ";&|<>()`$\\*?[\n#"):
        return None
    try:
        words = shlex.split(body)
    except ValueError:
        return None
    if words in (["true"], [":"], ["false"]):
        return ""  # prints nothing: the words after it are the command
    if not words or words[0] != "echo":
        return None
    args = words[1:]
    while args and CERTAIN_OPTIONS.fullmatch(args[0]):
        args = args[1:]
    return " ".join(args)


ESCAPING_PRINT = re.compile(r"\s*(?:printf\b|echo\s+-[a-zA-Z]*e)")


def decoded_escapes(text: str) -> str:
    """`text` with the backslash escapes `printf` and `echo -e` decode (`\\x67`, `\\147`, `\\u0067`)."""
    text = re.sub(r"\\0?([0-7]{1,3})", lambda match: chr(int(match.group(1), 8)), text)
    try:
        return text.encode("latin-1", "backslashreplace").decode("unicode_escape")
    except UnicodeDecodeError:
        return text


def substitution_body(tokens: list[str], first: int, wanted: int) -> str | None:
    """The text of the `wanted`-th top-level `$(...)` (counted from 1) of the command whose first
    token is `first`, or None when there is none."""
    depth = seen = 0
    start = None
    for index in range(first, len(tokens)):
        token = tokens[index]
        if token == "(":
            if depth == 0 and opens_substitution(tokens, index):
                seen += 1
                if seen == wanted:
                    start = index + 1
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0 and start is not None:
                return " ".join(tokens[start:index])
        elif depth == 0 and token in SEPARATORS:
            return None
    return " ".join(tokens[start:]) if start is not None else None


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


GATED_BARE = re.compile(r"\bpush\b|\bpr\s+(?:ready|merge|create|new|revert)\b")
API_UNREAD = re.compile(r"--input\b|query=@")  # a GraphQL query the text does not hold
# what a `gh api` call names to reach a pull request: the REST path (`pulls` ending the
# endpoint, or `pulls/<n>/merge`) or a GraphQL mutation
API_PULLS = re.compile(
    r"\bpulls(?=$|[\s?#'\"])|\bpulls/[^/\s]+/merge\b|\b(?:mergePullRequest|markPullRequestReadyForReview|enablePullRequestAutoMerge"
    r"|enqueuePullRequest|createPullRequest|revertPullRequest)\b"
)
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
    return (
        words_in_order(text, WORD_GH, WORD_PR) is not None
        or GATED_BARE.search(text) is not None
        or mentions_api_publish(text)
    )


def mentions_api_publish(text: str) -> bool:
    """Whether `text` has `gh`, then `api`, then a pull request path or mutation (`API_PULLS`)
    or a GraphQL query it does not hold (`API_UNREAD` next to `graphql`)."""
    return words_in_order(unquoted(text), WORD_GH, WORD_API, API_PULLS) is not None or mentions_api_unread(text)


def mentions_api_unread(text: str) -> bool:
    """Whether `text` has `gh`, `api` and `graphql` with `--input` or `query=@`, either order."""
    text = unquoted(text)
    return (
        words_in_order(text, WORD_GH, WORD_API, WORD_GRAPHQL, API_UNREAD) is not None
        or words_in_order(text, WORD_GH, WORD_API, API_UNREAD, WORD_GRAPHQL) is not None
    )


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
            directory = None if hops > MAX_DIR_HOPS else hop_dir(directory, args[index + 1])
        elif arg in {"--git-dir", "--work-tree"} or arg.startswith(("--git-dir=", "--work-tree=")):
            directory = None
        index += 2 if arg in GIT_VALUE_FLAGS else 1
    return directory, index


def is_shell_command_flag(arg: str) -> bool:
    return arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]


STDIN_SCRIPT = re.compile(r"-|/dev/stdin|/dev/fd/\d+|/proc/self/fd/\d+")
SHELL_VALUE_OPTIONS = {"--rcfile", "--init-file"}
SHELL_NAME = re.compile(r"[a-z]*sh[\d.]*")  # bash, ash, fish, mksh, bash5, ssh (a remote shell reads it too)
EXEC_WRAPPERS = {
    "docker", "podman", "kubectl", "ssh", "xargs", "timeout", "nice", "nohup", "setsid", "stdbuf",
    "chroot", "flock", "watch", "unbuffer", "script", "su", "doas", "sudo", "env", "exec", "command",
    "time", "busybox", "toolbox", "distrobox", "lxc", "nsenter", "systemd-run",
}
UNSEEN_HEADS = re.compile(r"\b(?:bash|sh|zsh|dash|ksh|source|eval)\b|(?:^|[\s;&|(])\.(?=\s)")
UNSEEN_TEXT, UNSEEN_BODIES = "text", "bodies"  # what of the command text a check reads: all, or its substitutions


def holds_substitution(word: str) -> bool:
    return "$(" in word or "`" in word or SUBSTITUTION_WORD in word


def stdin_fed(segment: list[str], piped: bool) -> bool:
    """Whether a command's stdin carries text the guard does not read as commands: a
    here-document, a here-string or a process substitution on fd 0 (`<<`, `<<<`, `< <(...)`, no
    other descriptor before it), or a pipe into it. A file (`< x.sh`, `</dev/null`) is a script
    file, a limit of its own."""
    if piped:
        return True
    for index, word in enumerate(segment):
        fd = segment[index - 1] if index else None
        if isinstance(fd, FdWord) and fd != "0":
            continue
        if word in {"<<", "<<<", "<&"}:
            return True
        if word == "<" and index + 1 < len(segment) and SUBSTITUTION_WORD in segment[index + 1]:
            return True
    return False


def unseen_script(argv: list[str], fed: bool, own: bool | None = None) -> str:
    """What a shell, `source` or `eval` with these words runs that the guard never reads as
    commands: `UNSEEN_TEXT` when it reads a fed stdin (no `-c` and no script, `-s`, `-`,
    `/dev/stdin`: a here-document, a here-string, a pipe) or an fd (`/dev/fd/3`), so the whole
    command text is the script; `UNSEEN_BODIES` when the script is a process substitution
    (`bash <(...)`, `. <(...)`) or a `-c` or `eval` text holds a substitution (`bash -c "$(cat
    <<'EOF' ...)"`), so the substitutions' text is; "" otherwise. A command name that is an
    expansion (`$SHELL`) reading its own segment's fed stdin (`own`) counts as a shell; a literal
    shell may get one from anywhere in the command (`fed`). A script file (`bash x.sh`) and a
    payload in a variable (`bash -c "$X"`) are limits of their own."""
    if not argv:
        return ""
    head = head_name(argv[0])
    if head in SHELLS or SHELL_NAME.fullmatch(head):
        index = 1
        while index < len(argv):
            word = argv[index]
            if word == "--":
                index += 1
                break
            short = word[:1] in "-+" and not word.startswith("--") and len(word) > 1
            if word in SHELL_VALUE_OPTIONS or (short and word[-1] in "oO"):
                if word in SHELL_VALUE_OPTIONS and index + 1 < len(argv) and holds_substitution(argv[index + 1]):
                    return UNSEEN_BODIES  # `--rcfile <(echo ...)`: a startup file the guard cannot read
                index += 2  # `-o pipefail`, `-euo pipefail`, `-O extglob`
            elif short and word[0] == "-" and "c" in word[1:]:
                return UNSEEN_BODIES if index + 1 < len(argv) and holds_substitution(argv[index + 1]) else ""
            elif short and word[0] == "-" and "s" in word[1:]:
                return UNSEEN_TEXT if fed else ""  # `-s`: the commands come from stdin
            elif word[:1] in "-+" and len(word) > 1:
                index += 1
            else:
                break
        script = argv[index] if index < len(argv) else None
        if script is None:
            return UNSEEN_TEXT if fed else ""
        if STDIN_SCRIPT.fullmatch(script):
            return UNSEEN_TEXT
        return UNSEEN_BODIES if SUBSTITUTION_WORD in script else ""
    if head in {"source", "."}:
        operands = [word for word in argv[1:] if word != "--"]
        if not operands:
            return ""
        if STDIN_SCRIPT.fullmatch(operands[0]):
            return UNSEEN_TEXT
        return UNSEEN_BODIES if SUBSTITUTION_WORD in operands[0] else ""
    if head == "eval":
        return UNSEEN_BODIES if any(holds_substitution(word) for word in argv[1:]) else ""
    if (fed if own is None else own) and ("$" in argv[0] or "`" in argv[0]):
        return UNSEEN_TEXT  # `$SHELL <<< ...`, `B=bash; $B <<< ...`, `$(which bash) -s <<EOF`
    return ""


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
    untrusted: bool = False  # a quoted operator came out bare: a redirection cannot be told from a word
    cut: bool = False  # an unquoted `$(`, an unclosed one or a backtick span: a flag may hide in or after it
    source: str = ""  # with `untrusted`: the text its tokens were read from (comments and here-document bodies gone)
    unseen: str = ""  # a shell here runs a script the guard never sees, and what to read of it: `unseen_script`

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
    _untrusted: bool = False,
    _fed: bool = False,
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
    model = DirectoryModel(tokens, workdir, _untrusted)
    _untrusted = model.untrusted  # a nested payload walks under the same doubt
    fed_any = _fed or stdin_fed(tokens, False) or any(token in PIPES for token in tokens)
    again = -1  # `command_spans` yields a command twice when a backtick may fold its words
    for first, segment, cut in command_spans(tokens, merge=not _untrusted):
        workdir = model.at(first)
        spent = False
        # the bodies of the second reading are the first one's: read and charged once
        for inner in () if first == again else inner_commands(" ".join(segment), walk):
            if inner is None:
                spent = True
            elif depth >= DEPTH_LIMIT:
                yield Command([], {}, unresolved_dir(inner, workdir), True, inner)
            else:
                yield from commands(
                    inner, workdir, depth + 1, include_assignments=include_assignments, _walk=walk,
                    _untrusted=_untrusted, _fed=fed_any,
                )
        again = first
        rest, effects = strip_prefixes(segment, scan=include_assignments)
        if spent or (not include_assignments and mentions_gated(" ".join(git_runs_text(segment, rest)))):
            # Block on sight: the work budget is spent, or git is handed text (an inline
            # alias, `rebase -x`, `bisect run`, `submodule foreach`) that names a gated
            # operation. No directory is known and the text is not trusted.
            yield Command([], {}, None, True, " ".join(segment), True)
            continue
        for body, tail in () if include_assignments or _untrusted else printed_heads(tokens, first, segment, rest):
            # the shell runs what a substitution in command position prints, with the words after
            # it. A lookup (`$(command -v gh)`) prints the name the argv reading already reads; an
            # `echo` of literal words prints them, walked as a command; any other text is read as
            # text that did not parse. Each text is charged to the work budget like a nested walk
            if not walk.charge(len(body or "") + sum(len(word) + 1 for word in tail) + 1):
                yield Command([], {}, None, True, " ".join(segment)[:2000], True)
                break
            if body is not None and LOOKUP_BODY.fullmatch(body):
                continue
            certain = printed_words(body) if body is not None else None
            text = " ".join(([body] if body is not None else []) + tail)
            if body is not None and ESCAPING_PRINT.match(body):
                text += "\n" + " ".join([decoded_escapes(body)] + tail)  # `$(printf '\\x67h pr merge 12')`
            if certain is not None and depth < DEPTH_LIMIT:
                yield from commands(
                    # redirections change nothing of the command the text makes: they are left out
                    " ".join([certain] + [shlex.quote(word) for word in drop_redirections(tail)]), workdir, depth + 1,
                    _walk=walk, _untrusted=_untrusted, _fed=fed_any,
                )
            else:
                yield Command([], {}, unresolved_dir(text, workdir), True, text)
        if not include_assignments and rest:
            # a stdin anywhere in the command may reach a shell in a group, a subshell, a body or a
            # payload (`{ bash; } <<< ...`, `... | (cd x && bash)`, `bash -c 'exec sh' <<EOF`)
            own = stdin_fed(segment, first > 0 and tokens[first - 1] in PIPES)
            fed = fed_any or own
            plain_rest = drop_redirections(rest)
            unseen = unseen_script(plain_rest, fed, own)
            if not unseen and fed and plain_rest and head_name(plain_rest[0]) in EXEC_WRAPPERS:
                # behind a wrapper that runs its words (`docker exec -i app bash`), a shell still
                # reads this stdin; a shell's name as `grep`'s argument is no shell
                later = [i for i, word in enumerate(plain_rest[1:], 1) if head_name(word) in SHELLS]
                unseen = next((kind for i in later[:8] if (kind := unseen_script(plain_rest[i:], True))), "")
            if unseen:
                yield Command([], {}, workdir, text=" ".join(segment), unseen=unseen)
        assignments = {**inherited, **effects.assignments}
        target = workdir
        for value in effects.chdir:
            target = hop_dir(target, value, model.variables_at(first))
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
                    nested, target, depth + 1, assignments, include_assignments=include_assignments,
                    _walk=walk, _untrusted=_untrusted, _fed=fed_any,
                )
            continue
        positions: list[int] = []
        extra: list[Payload] = []
        # a real redirection is no word of the rescanned tail (`setsid gh pr create --draft >/dev/null`);
        # with a quoted operator about, it cannot be told from a word, so every word stays
        plain = rest if _untrusted else drop_redirections(rest)
        first_word = 1 if plain[:1] == rest[:1] else 0  # a redirection ahead of the head is no head
        if plain and (
            include_assignments or (head_name(plain[0]) not in NO_RESCAN_HEADS and not is_git_word(plain[0]))
        ):
            words = RESCAN_WORDS if include_assignments else DEFAULT_RESCAN_WORDS
            later = [
                i
                for i, word in enumerate(plain[first_word:], first_word)
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
                flag = next((i for i, arg in enumerate(plain[first_word:], first_word) if is_shell_command_flag(arg)), None)
                payload = plain[flag + 1 :] if flag is not None else []
                payload = payload[1:] if payload[:1] == ["--"] else payload
                if payload:
                    extra.append(Payload(payload[0], target))
        if positions or extra:
            quoted = [shlex.quote(word) for word in plain]
            suffix = [0] * (len(plain) + 1)  # characters of the tail that starts at each word
            for number in range(len(plain) - 1, -1, -1):
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
                            _untrusted=_untrusted,
                            # a rescanned tail is a shell on this stdin only behind a wrapper that
                            # runs its words (`docker exec -i app bash`), not `grep sh`
                            _fed=fed_any and (not payload.rescan or bool(plain) and head_name(plain[0]) in EXEC_WRAPPERS),
                        )
        if not rest:
            if include_assignments and effects.assignments:
                yield Command([], assignments, target)
            continue
        yield Command(
            rest, assignments, target, untrusted=_untrusted, cut=cut, source=tokens.cleaned if _untrusted else ""
        )


def truthy(value: str | None) -> bool:
    """An override is on unless unset, empty, `0`, `false`, `no` or `off`.

    The one truthy rule: hooks/pre-push-validate.sh spells the same set in bash.
    """
    return value is not None and value.strip().lower() not in {"", "0", "false", "no", "off"}
