"""The git guard: block git and gh commands that bypass the toolkit's safety rules.

Run as `python3 -E -s hooks/lib/git_guard.py` with the PreToolUse payload on
stdin (`hooks/prevent-project-commit.sh` does this). It imports only the
standard library and its sibling modules in `hooks/lib/`, so it runs without
the rest of the toolkit. Exit 0 allows, exit 2 blocks
with the reason on stderr, which the agent sees.

Blocked:
- `git commit --no-verify` / `-n`, `--no-gpg-sign`, and the `core.hooksPath`
  and `commit.gpgsign=false` overrides, also through `-c`, `--config-env`,
  `GIT_CONFIG_*` and aliases;
- `git push --no-verify`, force-pushing main or master, and deleting them;
- a commit that includes a local workflow state file (`STATE_FILES`) or any
  path under `.ai-toolkit/`, including files added
  earlier in the same command (`git add PROJECT.md && git commit`): the hook
  runs before the add, so the staged set is `git diff --cached` plus what those
  adds would stage;
- `gh pr create` (or `gh pr new`, `gh pr revert`) without `--draft`, and `gh pr ready` and
  `gh pr merge`, unless the user set `AITK_PR_READY=1` in the environment the
  session started with (set only when the user asked in words);
- `gh pr create` (or `gh pr new`) whose commit has no passing check recorded on
  its exact tree by `scripts/verify.py` (`check_pr_verified`, the record format
  in `verify_record`). No session override lifts it: when nothing meaningful
  can run, the user's agreement goes into a `--partial` record, or the user
  opens the PR from their own terminal, where this hook does not run. The PR's
  commit is HEAD of the directory the command runs in, as `shell_tokens` models
  it (`shell_tokens.DirectoryModel`: a subshell's `cd` is restored, one that may not have
  run leaves the directory unknown), or its
  `--head` branch when that resolves locally; a directory the guard knows it
  cannot follow, and a creation it cannot read, block;
- a command that assigns or exports any toolkit override itself (a prefix, an
  assignment-only segment, `env`, `export`/`declare`/`typeset`/`readonly`/
  `local`, a literal `+=` append, inside `bash -c`, `eval`, `env -S`, a
  substitution or a function body, behind a redirection, or after an `env`,
  shell or `eval` word later in the argv), whatever it runs: overrides count
  only from the session environment, so the hook never reads them from the
  command.

Every command the shell would run is checked: newline- and `;`-separated
commands, and-lists and or-lists, subshells, `sh -c` and `eval` payloads,
command substitutions, shell functions (also run by `trap`, a backtick span or a
variable), and commands behind `env`, `sudo`, `command`, `timeout`, `nohup`, `xargs`,
`nice`, `ionice`, `stdbuf` or `time`. Behind any other command that is not a printing
one (`setsid`, `caffeinate`, `flock x`), a later word that may start git is read as
the command too (`git_walk.may_run_git`).
A command that mentions git or gh and cannot be parsed blocks; an internal
error blocks a command that mentions git, gh or an override, and the wrapper
fails closed on those when python3 is missing.

Text that did not parse, or nests too deep, is searched for `gh`, then `pr`, then
`ready`/`merge`/`create`/`new`/`revert` in order over the whole text (origin/main's rule, a draft
flag anywhere exempting only a create, new or revert) AND piece by piece, and blocks on either. A
quoted or escaped operator standing alone as a word (`'>'`, `\\;`, `${X-a;b}`) makes the guard
read the whole command that way too (`untrusted_text_verbs`, `gh_api_text_creates`): ready and
merge are lifted by the override, create, new and revert never get a draft credit.

Git's own words: redirections are dropped and a `$(...)` is one word before the globals, the
subcommand and the arguments are read, and a redirection ahead of the head does not hide it
(`>/dev/null git push`). Push options are read as git 2.39's parse-options does (`PUSH_OPTIONS`):
value flags take the next word, a unique prefix of a long option is that option, an ambiguous
one pushes nothing, the first operand is the repository, whatever it spells, and a refspec
destination with a `*` counts as main. `--mirror` blocks. A `sh -c`, `bash -c` or `eval`
payload does not know the outer shell's directory, so `$(git branch --show-current)` inside one
is never resolved.

Known limits (a tripwire, not a shell sandbox): a word that expands to a push option
(`git push origin main $F`, `git push $F origin main`), a git alias defined in a file
the hook cannot read, `gh api` calls, and programs that run git themselves are
not seen. Directory changes follow `shell_tokens`' rules (`cd`, `pushd`, `git -C`,
`env -C`): `cd -`, `popd`, a bare `pushd`, a target the shell expands, a `cd` that may
not have run (after `||`, after `&&` once the list ends, in a pipeline, in a list ended
by `&`, in an if/while/until/for/select/case body), an `eval` that changes directory,
every `cd` in text with a quoted or escaped operator character (so an unescaped
`find -exec ... \\;` too) and everything after a function definition followed by a
`cd` leave the directory unknown until a subshell restores it or an absolute `cd`
re-anchors it (not after a function). Not modelled: a sourced file's `cd`, `CDPATH`,
`pushd +N`, `cd ~-`, `C=cd; $C X`, `trap 'cd X' DEBUG` and `eval "$X"`, and so do
`--git-dir`/`--work-tree` values the shell expands. Where the directory is unknown
the guard cannot read the repository, so it blocks what needs it: a force push or a
delete whose branch it cannot read, a commit whose staged files it cannot read, and a
subcommand that is not a git command (it may be a repository alias for a gated
operation). Substitution bodies are scanned wherever they are quoted, so a
single-quoted `$(...)` that only prints text blocks like a live one.

Override-assignment check: a tripwire, not a sandbox. It is the opt-in token
scan of `shell_tokens.commands(..., include_assignments=True)` and nothing more:
it reads the command the way the git checks do, through recognized wrappers,
`builtin`/`command` prefixes, redirections, function bodies, a later `env`,
shell or `eval` word, and `bash -c`, `eval`, `env -S` and substitution
payloads. It blocks a literal truthy assignment, every `+=` append and a bare
or valueless export of an override (`declare -p` only prints), and an
`integer`/`float` declaration or any attribute beyond x/g/r/p (`-i`, `-n`, `-F`,
`-E`, `-Z`, `-T`) that mentions an override, because those change the value the
literal text shows. Text that only mentions an assignment is allowed: `echo
NAME=1`, `git push # NAME=1`, `git log --grep=NAME=1`, a commit message or a
`git grep` pattern that carries export wording and a name.

What actually protects the PR boundary is elsewhere: a non-draft `gh pr create`,
`gh pr ready` and `gh pr merge` read `AITK_PR_READY` only from the session
environment. This check keeps the agent from shopping for an override it
cannot get.

Known limits of the scan, each a real override it does not see:
- brace expansion that builds a name (`env {NAME,X}=1 ...`);
- arithmetic setters, which export under `set -a`: `(( NAME = 1 ))`,
  `let NAME++`, `let NAME=1`, `((++NAME))` after a falsy export, an indexed
  write (`NAME[0]=1`) and a `${NAME:=1}` expansion;
- array-literal (`NAME=(1)`), process-substitution (`NAME=<(...)`) and
  carriage-return values, which read as falsy or empty;
- heredoc bodies, which the tokenizer skips, so a body piped to a shell is not
  read (the same property keeps prose in a heredoc commit message allowed);
- a name quoted with a locale string (`AITK_PR_$"READY"`);
- a redirection operator erased with a quoted option value
  (`env -u '>' NAME=1 ...`);
- shell-specific grammar: a zsh anonymous function (`() { ...; }`), a function
  named after a wrapper (`env() { ...; }`), `nocorrect`/`repeat N`/`coproc`
  before a prefix, and a nameref set by a plain value
  (`declare -n r; r=NAME; declare -x r=1`);
- `read`, `printf -v` and `mapfile` (write targets, not assignments),
  `source`/`.` and scripts run separately, dynamically built names (`${!v}`,
  `eval "AITK_PR_$X=1"`), substitution-built assignments (`env $(printf '...') ...`), aliases (the body
  is quoted text) and profile writes, which alter later shell startup rather
  than this command.

`tests/test_git_guard_hook.py` pins every case above in `OVERRIDE_SCAN_LIMITS`;
a fix moves the case into the BLOCK list and out of this list. (Operator runs the shell
lexer returns as one token, `;(`, `)&&`, `&&(`, `|(`, `f()(`, are split into their
operators by `shell_tokens.tokenize`, so the subshell or function body after one is read;
that case moved to `OVERRIDE_ASSIGNMENT_BLOCK`. A quoted word made only of operator
characters is split too, an accepted over-block.)

Time limit: a PreToolUse hook that runs past its `timeout` in hooks/hooks.json (30 s
here) FAILS OPEN, the tool call runs. `main()` therefore parses under
`DEADLINE_SECONDS` (`shell_tokens.deadline`, a SIGALRM timer that raises a
BaseException no `except Exception` swallows): a command not finished in time blocks as
too large or complex to check, whatever it mentions, since quoting can hide git from a
text match. Heads are compared without case (`GIT`, `Gh`), and the fail-closed
mention patterns and the wrapper's prefilter ignore case too.
Over-blocks the scan accepts: `echo env NAME=1` (a later `env` word restarts
the scan) and a single-quoted `$(NAME=1)` (substitution bodies are scanned
wherever they are quoted).

`gh pr ready` / `gh pr merge` traversal: the default traversal of
`shell_tokens.commands` rescans from every later `gh`, `git`, shell, `env` or
`eval` word (and from the string after a later `-c`) behind any head that is
not `gh`, `git` or a command that only prints (`echo`, `printf`, `cat`, `grep`,
...), so `setsid`, `uv run`, `flock`, `chronic`, `watch -n1`, `find -exec ...
\\;`, `builtin command`, `su -c` and `eval -- '...'` payloads are seen, even
when an earlier argument is itself named `gh` (`flock /tmp/gh gh pr merge 12`).
Function-definition heads (`name() {`) are dropped (`echo() { gh pr ready 12; }; echo`).
Text git itself runs is never resolved (block on sight): the words after `git
rebase -x`/`--exec` (every spelling), `git bisect run`, `git submodule foreach` and
`git for-each-repo` (the git command after its options), and the whole segment of a command that carries an inline alias (`git -c
alias.NAME=...`, `-calias.NAME=...`, `--config-env=alias.NAME=VAR`, a
`GIT_CONFIG_KEY_n=alias.NAME` assignment, a bare `alias.NAME=...` word in a segment
with a `git` word, and `git config alias.NAME ...`; a bare `alias.NAME` word alone
(`grep alias.x`, `git push origin alias.cleanup`) is no alias; with or without a
wrapper in front), are only checked for a MENTION of a gated operation after the quote characters,
backslashes and backticks are removed (`shell_tokens.mentions_gated`: `gh` followed
later by `pr`, `git` followed later by `push`, a bare `push`, `pr ready`/`merge`/
`create`/`new`/`revert`). A mention makes the command unreadable and it blocks. No alias is
looked up, so a builtin and an alias are not told apart. Plain `git rebase -x 'make
test'`, `git bisect run ./t.sh`, `git submodule foreach 'echo $name'` and `git -c
alias.st=status st` are not affected. Budget: the traversal charges the characters of
every tail it rescans, every string a later `-c` word hands to a shell and every `$(...)`/backtick body
it scans against `MAX_TAIL_CHARS` for the whole call (the first tokenize of the command
and the walk of an `sh -c`, `eval` or `env -S` payload are not charged; nesting is bounded by `DEPTH_LIMIT`); a segment past it, and every later segment that
would read more, is one unreadable command (`true sh sh ...` thousands of times, a few
words around one 100 KB word, or `$(` thousands of times) and blocks whatever its text
says, so a `gh pr merge 12` after the budget is spent blocks too. It accepts over-blocks
on commands that only carry such a word after an unknown head (`ssh host gh pr merge
12`), on any gated mention in a segment that also carries an inline alias or in the
words git runs (a commit message that says `gh pr merge` next to `-c alias.x=...`, an
alias that is never invoked, `git rebase -x 'echo push'`, a filename such as
`./push.sh`), and on a quoted `()` followed by a quoted `{`, which reads as a function
head (`echo '()' '{' gh pr ready 12`). Flags and the verb are read as gh's own parser
does (`gh_args`, with the flag tables of gh 2.103.0: a version assumption, so a flag a newer
gh adds is unknown and grants no draft, help or undo). A command name or verb that holds a
variable, substitution, brace or glob (`"$GH" pr ready 12`, `$(command -v gh) pr merge 12`,
`{gh,} pr merge 12`, `gh pr $V 12`) is read as gh or as an unknown verb (cobra's reading
decides it), which is gated; `gh pr revert` is gated like `create`. A positional word with an
expansion (`--draft $X`), or an unquoted `$(...)`, `<(...)` or backtick span anywhere among the
words (`-t $(x)--draft`), or a quoted or escaped operator about, grant no draft, help or undo
(accepted over-block: `gh pr ready --undo "$PR"`, `gh pr create --draft -t $(git log -1 --format=%s)`),
and a creation with one fails the verify gate. A backtick opens a span only outside quotes; a
command with one is read folded and as it is. The argv reading always runs; a quoted or escaped
operator adds a text reading of each piece cut where the shell really separates commands (`quoted_split`). A `$(...)` inside a command is one word of it, so the words
after it are read (`gh -R $(echo o/r) pr merge 12`); one where the verb stands is unknown.

`gh api` PR create, merge and ready are gated too (`gh_args.api_effect`, redirections
dropped first): a PUT to `repos/<o>/<r>/pulls/<n>/merge` or `repositories/<id>/pulls/<n>/merge`
needs `AITK_PR_READY=1` like `gh pr merge`, as does a GraphQL query naming `mergePullRequest`,
`markPullRequestReadyForReview`, `enablePullRequestAutoMerge` or `enqueuePullRequest`. A POST
to `.../pulls`, a query naming `createPullRequest` or `revertPullRequest`, and a query the
guard cannot read (`--input`, `-F query=@file`, a `query=` with a shell expansion or backtick;
a `$name` is a GraphQL variable only when an operation's definition list declares it) block with no override, like an
unchecked `gh pr create`; so does a non-GET call with no endpoint. PATCH, DELETE, HEAD and the
rest do neither. An expansion in the endpoint, a method that is an expansion, an unknown flag,
a `-H` value with an expansion (it may be a method override) or an unclosed `$(` may be either, and blocks when it could be
(`gh api "$URL" -X PUT`). Other API writes (refs, contents, merges into a branch, `gh repo
sync --force`) and `curl` are not modelled: for those, GitHub's branch protection is the
boundary, not this hook. Not seen, pinned in `PR_PUBLISH_LIMITS`: `gh api $ARGS` (the whole
call in a variable), a whole-segment expansion standing alone for `pulls` or `merge`
(`repos/o/r/$X`), and `curl`. A literal query holding a backtick blocks with no override (an
accepted over-block). Known limits, each a real
`gh pr
ready`/`merge` it does not see (pinned in `PR_PUBLISH_LIMITS`): `gh` reached through a
function wrapper (`g() { gh "$@"; }; g pr merge 12`), `gh` aliases and extensions, an
expanded name behind an unknown wrapper (`g=gh; setsid $g pr merge 12`: rescanning from every
expansion word could spend the work budget on ordinary commands), a variable that holds more
than the name (`c='gh pr'; $c merge 12`), a
quoted command string handed to a wrapper that runs it through a shell without `-c` (`watch 'gh pr ready 12'`, `tmux new-session '...'`), every
git config value or tool option that runs a shell other than an inline alias (`git
filter-branch` filters, `git -c core.pager=...`, `-c credential.helper='!...'`, `git
difftool -x`, `sequence.editor`, `core.editor`, `diff.external`, `core.sshCommand` and
`mergetool.<n>.cmd` are the same class), `GIT_CONFIG_*` or an alias value exported by an
earlier command (the alias key and the text in different segments), an alias an earlier
call or a file already holds (`git config alias.m '!gh pr merge'` blocks, but the later
`git m 12` is an ordinary git command, as is a value routed through a variable), an
alias value assigned in the environment of a shell whose payload names the key (`env
A='!gh pr merge 12' sh -c 'git --config-env=alias.x=A x'`), and `GIT_DIR` on `gh`
itself.

Dashed git entry points are read as their subcommand wherever git is looked for
(`git-push`, `$(git --exec-path)/git-rebase -x ...`, `git-submodule foreach`, `git
submodule--helper foreach`), but only a name git installs (`shell_tokens.GIT_ENTRY_POINTS`)
counts: any other `git-*` head (`./git-run`, `git-x`, `/opt/x/git-wrap`) is an ordinary
executable and gets the wrapper rescan like `setsid`. A variable that holds an entry
point is read the same way (`G=git-push; $G -f origin main`). Accepted over-blocks: a later
argument word that names an entry point restarts the scan, so `chmod +x bin/git-push`
and `make git-push` read as a push, and so does an executable named `./git-push`. The
inline-alias `-c alias.x` word counts only among git's own global options, before its
subcommand (`git -C d -c alias.x x` counts; `grep -c alias.x`, `git grep -c alias.x docs`
and `git log -c alias.x push` do not; a `g -c alias.x x` wrapper is an accepted miss). A
`-C` or `cd` target that holds `$`, a backtick, a glob character (`*?[`), a tab, a newline (or
`~` for `-C`) leaves the working
directory unknown (`None`) before any path arithmetic, so the review gate blocks `cd
"$X" && gh pr create` with "cannot follow" (`cd "$(git rev-parse --show-toplevel)"`, exactly
that text, is read as the git top level instead; so is `$NAME` or `${NAME}` when an earlier
segment set `NAME=` to a literal path, from the model's table, never `shell_vars`), and the global options that take a separate value
(`--attr-source`, `--super-prefix`, `--namespace`, `-C`, `-c`, `--git-dir`,
`--work-tree`, `--config-env`) do not hide the subcommand. The patterns that scan
unresolved text are searched in order, once (`shell_tokens.words_in_order`), so a
long text that does not match is read in linear time, and so is the scan of
`$(...)`, backtick and `<(...)` bodies for a git commit or push (`has_unsafe_git_substitution`:
one pass over the openers, a position index for the git words).
"""

from __future__ import annotations

import json
import os
import re
import sys

import gh_args
import guard_base
import shell_lex
import shell_tokens
import shell_values
import verify_record
from guard_base import Blocked, block, is_git_executable
from git_rules import check_commit, check_push, check_speculative, is_protected_path, long_option_prefix, own_args, paths_added, update_index_paths
from gh_text import COMMAND_SEPARATOR, push_marker, unresolved_gated, unseen_git, untrusted_pieces, untrusted_text_verbs
from git_walk import GIT_GLOBAL_VALUE, expand_configured_alias, has_unsafe_git_substitution, parse_git_actions

# Re-exported: the tests read these names through this module.
from git_rules import STATE_FILES, resolve_push_option  # noqa: F401
from gh_text import DRAFT_FLAG, UNRESOLVED_PR_PUBLISH, quoted_split  # noqa: F401


MENTIONS_GIT = re.compile(r"\bgit\b|\bgh\b", re.I)
# The in-process time limit of `main()`. A hook past its timeout in hooks/hooks.json (30 s)
# fails open, so the guard stops itself first and blocks what it could not finish reading.
DEADLINE_SECONDS = 20.0


PR_PUBLISH_MESSAGE = (
    "`gh pr {verb}` {effect}, and only the user's explicit request in words "
    "authorizes that (rules/universal.md). Do not bypass this on your own: stop "
    "and ask the user, who alone can override it."
)
PR_PUBLISH_UNREADABLE = (
    "this command could not be read in full (too much text to scan, or git is handed text "
    "that mentions `gh pr` or a push: an inline alias, `rebase -x`, `bisect run`, "
    "`submodule foreach`, `for-each-repo`), so the guard cannot tell whether it runs `gh pr ready` or "
    "`gh pr merge`, which need the user's explicit request in words (rules/universal.md). "
    "Split it into plain commands. Do not bypass this on your own: stop and ask the user, "
    "who alone can override it."
)
PR_PUBLISH_EFFECT = {
    "ready": "takes a draft pull request out of draft",
    "merge": "merges a pull request",
    "create": "without `--draft` opens a pull request ready for review (add `--draft`)",
    "new": "without `--draft` opens a pull request ready for review (add `--draft`)",
    "revert": "without `--draft` opens a pull request ready for review (add `--draft`)",
}
PR_PUBLISH_UNKNOWN = (
    "the guard cannot read which gh command or verb this runs (a shell expansion in its name "
    "or verb), and `gh pr ready`, `gh pr merge` and a non-draft `gh pr create` need the user's "
    "explicit request in words (rules/universal.md). Write the command and the verb literally "
    "(`gh pr view 12`, not `gh pr $V 12`)."
)
PR_PUBLISH_API = (
    "`gh api` {what}, and only the user's explicit request in words authorizes that "
    "(rules/universal.md). Do not bypass this on your own: stop and ask the user, who "
    "alone can override it."
)
PR_API_CREATE = {
    gh_args.CREATE_API: (
        "`gh api` {what}, which skips the verify gate that `gh pr create` passes and which has "
        "no override. Open the PR with `gh pr create --draft`, which the guard checks."
    ),
    gh_args.UNREADABLE_API: (
        "`gh api` {what}, and the PR gate has no override. Write the endpoint, the method and "
        "the GraphQL query literally in the command (no variable in the endpoint, method or "
        "query, no redirection ahead of them, no `--input` or `@file`), or open the PR with "
        "`gh pr create --draft`, which the guard checks."
    ),
}
API_WHAT = {
    gh_args.MERGE_API: "merges or readies a pull request",
    gh_args.CREATE_API: "opens a pull request",
    gh_args.UNREADABLE_API: "has an endpoint or GraphQL query the guard cannot read, so it could open a pull request",
}
PR_PUBLISH_UNTRUSTED = " The guard cannot rely on this command's flags ({why}); spell them out."
PR_QUOTED_OPERATOR = (
    "`gh pr {verb}` shares its command with a quoted or escaped `<`, `>`, `;`, `|`, `&` or "
    "parenthesis standing alone as a word (`'>'`, `\\;`), which the guard cannot tell from an "
    "operator, so it cannot read which words are this command's flags. Run `gh pr {verb}` as a "
    "command of its own, without such a word."
)


OVERRIDE_VARIABLES = ("AITK_PR_READY", "SKIP_PRECHECK")
EXPORTING_BUILTINS = {"export", "declare", "typeset", "readonly", "local", "integer", "float"}
# The fallback for command text that did not tokenize or nested too deep: a
# literal assignment or append, or an export-family builtin (also behind
# `builtin` or `command`) that mentions an override before the next separator.
# The builtin and the mention are searched in order within each separated command
# (`unresolved_sets_override`), never as one `builtin.*name` pattern, which
# backtracks across the whole text from every builtin word.
OVERRIDE_ASSIGNMENT = re.compile(r"\b(?:AITK_PR_READY|SKIP_PRECHECK)\+?=")
EXPORTING_BUILTIN = re.compile(r"\b(?:export|declare|typeset|readonly|local|integer|float)\b")
OVERRIDE_MENTION = re.compile(r"\b(?:AITK_PR_READY|SKIP_PRECHECK)\b")
# The message names no variable: hook output never spells an override out.
OVERRIDE_MESSAGE = (
    "BLOCKED: this command sets a toolkit override variable in its own environment. "
    "Overrides count only from the environment the session started with; the user "
    "sets one before launching the session. Stop and ask the user; do not work "
    "around the hook."
)


def unresolved_sets_override(text: str) -> bool:
    """The text-only form of `sets_override`, for a command that did not parse."""
    if OVERRIDE_ASSIGNMENT.search(text):
        return True
    return any(
        shell_tokens.words_in_order(command, EXPORTING_BUILTIN, OVERRIDE_MENTION) is not None
        for command in COMMAND_SEPARATOR.split(text)
    )


def sets_override(found: shell_tokens.Command) -> bool:
    """Whether one parsed command assigns, appends to or exports an override."""
    for key, value in found.assignments.items():
        if key.endswith("+"):
            if key[:-1] in OVERRIDE_VARIABLES:
                return True  # an append: the resulting value is unknown
        elif key in OVERRIDE_VARIABLES and shell_tokens.truthy(value):
            return True
    if found.name in EXPORTING_BUILTINS:
        flags = "".join(arg[1:] for arg in found.argv[1:] if arg[:1] in "-+" and "=" not in arg)
        if (found.name in {"integer", "float"} or any(c.isalpha() and c not in "xgrp" for c in flags)) and (
            OVERRIDE_MENTION.search(" ".join(found.argv[1:]))
        ):
            return True  # value-changing attributes make the literal unreliable
        printing = found.name in {"declare", "typeset"} and "p" in flags
        for arg in found.argv[1:]:
            name, sep, value = arg.partition("=")
            if sep and name.endswith("+"):
                if name[:-1] in OVERRIDE_VARIABLES:
                    return True
            elif name in OVERRIDE_VARIABLES and ((not sep and not printing) or shell_tokens.truthy(value)):
                return True  # a bare name exports a value the hook cannot see
    return found.unresolved and unresolved_sets_override(found.text)


def check_override_assignment(command: str, cwd: str) -> None:
    """Overrides count only from the session environment, never from the command."""
    for found in shell_tokens.commands(command, cwd, include_assignments=True):
        if sets_override(found):
            raise Blocked(OVERRIDE_MESSAGE)


_WALKED: dict[tuple[str, str], list[shell_tokens.Command]] = {}  # filled only inside `evaluate`
_WALKING = [False]


def walk_commands(command: str, cwd: str) -> list[shell_tokens.Command]:
    """`shell_tokens.commands(command, cwd)`, walked once per `evaluate` and shared by its checks
    (a check called on its own walks afresh)."""
    if not _WALKING[0]:
        return list(shell_tokens.commands(command, cwd))
    key = (command, cwd)
    if key not in _WALKED:
        _WALKED[key] = list(shell_tokens.commands(command, cwd))
    return _WALKED[key]


def check_pr_publish(command: str, cwd: str, environ: dict[str, str]) -> None:
    """A non-draft `gh pr create`/`new`/`revert`, `gh pr ready` and `gh pr merge` need the
    user's AITK_PR_READY=1, read only from the session environment."""
    if shell_tokens.truthy(environ.get("AITK_PR_READY")):
        return
    read_sources: set[str] = set()
    found_all = walk_commands(command, cwd)
    for found in found_all:
        if found.untrusted and not found.unresolved and found.source not in read_sources:
            # a quoted operator: the words may be cut wrong, so the text is read too (the
            # argv reading below still runs, whatever this finds)
            read_sources.add(found.source)
            for piece in untrusted_pieces(found.source):
                for verb in untrusted_text_verbs(piece):
                    if verb in {"ready", "merge"}:
                        raise block(PR_PUBLISH_MESSAGE.format(verb=verb, effect=PR_PUBLISH_EFFECT[verb]))
                    raise block(PR_QUOTED_OPERATOR.format(verb=verb))
                if shell_tokens.mentions_api_publish(piece):
                    raise block(PR_PUBLISH_API.format(what="could merge, ready or open a pull request"))
        if found.unreadable:
            # the work budget is spent, or git is handed text that mentions a gated
            # operation: the text cannot show what runs, so a contiguous `gh` in it
            # proves nothing either way
            raise block(PR_PUBLISH_UNREADABLE + api_note(found.text))
        if found.unresolved:
            for verb in unresolved_gated(found.text):
                raise block(PR_PUBLISH_MESSAGE.format(verb=verb, effect=PR_PUBLISH_EFFECT[verb]))
            if shell_tokens.mentions_api_publish(found.text):
                raise block(PR_PUBLISH_API.format(what="could merge, ready or open a pull request"))
            continue
        for verb, args, cut in gh_verbs(found):
            flags = gh_args.walk(args, verb, cut)
            if verb == gh_args.UNKNOWN:
                raise block(PR_PUBLISH_UNKNOWN)
            if not publishes_nothing(verb, flags):
                note = "" if flags.trusted else PR_PUBLISH_UNTRUSTED.format(
                    why=untrusted_reason(flags, cut, found.untrusted)
                )
                raise block(PR_PUBLISH_MESSAGE.format(verb=verb, effect=PR_PUBLISH_EFFECT[verb]) + note)
        for args, cut in gh_api_calls(found):
            if gh_args.api_effect(args, cut) == gh_args.MERGE_API:
                raise block(PR_PUBLISH_API.format(what=API_WHAT[gh_args.MERGE_API]))


def untrusted_reason(flags: gh_args.Flags, cut: bool, untrusted: bool = False) -> str:
    if flags.unknown_flags:
        return f"it has the flag `{flags.unknown_flags[0]}`, which gh 2.103.0 does not have"
    if untrusted:
        return "a quoted or escaped operator in the command may cut or hide its words"
    if cut:
        return "an unquoted `$(`, `<(` or backtick span may hide or glue a flag"
    return "a word with a variable, brace or glob may become a flag"


def publishes_nothing(verb: str, flags: gh_args.Flags) -> bool:
    """Whether `gh pr VERB` with these flags opens, readies or merges nothing: help, a draft
    (create, new, revert), or `--undo` (ready, which converts back to a draft)."""
    if verb in {"create", "new", "revert"}:
        return flags.on("draft") or flags.asks_help
    if verb == "ready":
        return flags.on("undo") or flags.asks_help
    return verb == "merge" and flags.asks_help


def argv_readings(found: shell_tokens.Command) -> list[list[str]]:
    """A command's words without its redirections, read two ways: a digit word apart from its
    operator (`gh api 5 >/dev/null ...`) is an argument to the shell and to gh, and an earlier
    guard dropped it as a descriptor. With a quoted operator about (`found.untrusted`) a
    redirection may be a quoted word (`$G pr -t '>' merge 12`), so the words as they stand are
    read too. A wrong guess can only block more, so every reading counts."""
    readings = []
    for guess in (False, True):
        argv = shell_tokens.drop_redirections(found.argv, guess)
        if argv and argv not in readings:
            readings.append(argv)
    if found.untrusted and found.argv and found.argv not in readings:
        readings.append(list(found.argv))
    return readings


def gh_verbs(found: shell_tokens.Command) -> list[tuple[str, list[str], bool]]:
    """The gated `gh pr` verbs one command can run, with the arguments to read for each and
    whether the command is cut (an unquoted substitution, an unclosed `$(`, a backtick span, or a
    quoted operator about, which may cut the words in two: no draft, help or undo credit; see
    `gh_args.pr_commands`). Its redirections are dropped. A command name that holds an expansion
    (`"$GH"`, `${g/x/h}`, `{gh,}`, a substitution) is read as gh. A command with a quoted operator
    about (`found.untrusted`) is also read as text, which adds to this: `untrusted_pieces`."""
    found_verbs: list[tuple[str, list[str], bool]] = []
    for argv in argv_readings(found):
        if os.path.basename(argv[0]).lower() == "gh":
            commands = gh_args.pr_commands(argv[1:])
        elif gh_args.has_expansion(argv[0]):
            commands = gh_args.pr_commands(argv[1:], expands=True)
        else:
            continue
        found_verbs.extend((verb, args, found.cut or found.untrusted) for verb, args in commands)
    return found_verbs


def api_note(text: str) -> str:
    """Names `gh api` when it is why a command's text was refused."""
    if shell_tokens.mentions_api_publish(text):
        return (
            " The text names `gh api` with a pull request path, a pull request mutation or a "
            "query the guard cannot read (`gh api` merge, ready and create are gated)."
        )
    return ""


def gh_api_calls(found: shell_tokens.Command) -> list[tuple[list[str], bool]]:
    """The arguments after `api` of every `gh api` one command can run, each with whether the
    command is cut (see `gh_verbs`); the name is read as in `gh_verbs`."""
    found_calls: list[tuple[list[str], bool]] = []
    for argv in argv_readings(found):
        if os.path.basename(argv[0]).lower() == "gh":
            calls = gh_args.api_commands(argv[1:])
        elif gh_args.has_expansion(argv[0]):
            calls = gh_args.api_commands(argv[1:], expands=True)
        else:
            continue
        found_calls.extend((args, found.cut or found.untrusted) for args in calls)
    return found_calls


PR_VERIFY_BLOCK = "`gh pr create` opens a PR only for a tree a check passed on, and {reason}. {remedy}"
VERIFY_REMEDY_RUN = (
    "Run the change's own test or acceptance command through `python3 {script} -- <command>`; "
    "when only related checks can run here, add `--partial \"<what CI still runs>\"`. A command "
    "that checks nothing is working around the hook. If nothing meaningful can run for this "
    "change, stop and ask the user; with their agreement, record the closest real check with `--partial`."
)
VERIFY_REMEDY_FAILED = (
    "Only a pass of that same command on this tree clears it; a different command does not. Fix "
    "what fails and run it again through `python3 {script} -- <command>`; if the command itself "
    "is wrong, stop and tell the user, who can open the PR from their own terminal, where this "
    "hook does not run."
)
VERIFY_REMEDY_UNSTABLE = (
    "Only a run of that same command that leaves the files as they were clears this tree; a "
    "different command does not. Run it again through `python3 {script} -- <command>`; if it "
    "rewrites files every time, commit what it writes or stop and tell the user."
)
VERIFY_REMEDY_UNCOMMITTED = (
    "This checkout also holds changes the commit doesn't ({paths}); every check run here includes "
    "them, so a new run cannot match the commit. Commit them if they belong to the change (a run "
    "made before the commit counts once the commit holds exactly what it tested); otherwise stop "
    "and tell the user. Deleting, reverting or ignoring work you didn't make to get past this is "
    "working around the hook."
)
VERIFY_REMEDY_OTHER_BRANCH = (
    "`verify.py` records the checkout it runs in, so run the check in a checkout of `{branch}` "
    "and open the PR from there."
)
VERIFY_REMEDY_NO_BRANCH = "Open the PR from a checkout of that branch, after its check passed there."
VERIFY_REMEDY_NO_CHECKOUT = "Run `gh pr create` from the repository, after its check passed there."
VERIFY_REMEDY_NO_COMMIT = "Commit the change first, then run its check through `python3 {script} -- <command>`."
PR_VERIFY_UNREADABLE = (
    "this command could not be read in full, so the guard cannot rule out a `gh pr create` in it, "
    "and the PR gate has no override. Run `gh pr create` as a plain command from the repository "
    "and the rest as plain commands; if this one cannot be split, stop and tell the user."
)
PR_VERIFY_UNKNOWN = (
    "the guard cannot read which gh command or verb this runs (a shell expansion), so it cannot "
    "rule out a `gh pr create`, and the PR gate has no override. Write the command and the "
    "verb literally."
)
PR_VERIFY_UNKNOWN_FLAG = (
    "`gh pr create` has the flag `{flag}`, which the guard does not know (it knows gh 2.103.0's "
    "flags), so it cannot tell which branch it opens (`--head` may hide behind it), and the PR "
    "gate has no override. Use only flags gh 2.103.0 has."
)
PR_VERIFY_EXPANDED = (
    "`gh pr create` has a word with a variable, brace or glob that may become a flag (`--head x`), "
    "so the guard cannot tell which branch it opens, and the PR gate has no override. Spell "
    "the flags out."
)
VERIFY_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts", "verify.py")
CREATE_WORD = re.compile(r"\b(create|new)\b")
# in text that did not parse: `pulls` not followed by an id (`pulls/12/merge` is a merge), or a creating mutation
API_CREATE_TEXT = re.compile(r"\bpulls(?=$|[\s?#'\"])|\b(?:createPullRequest|revertPullRequest)\b")


def gh_api_text_creates(text: str) -> bool:
    """Whether text the guard cannot read as commands has a `gh api` that could open a pull request."""
    text = shell_tokens.unquoted(text)
    return (
        shell_tokens.words_in_order(text, shell_tokens.WORD_GH, shell_tokens.WORD_API, API_CREATE_TEXT) is not None
        or shell_tokens.mentions_api_unread(text)
    )


def refuse(reason: str, remedy: str, **values: str) -> Blocked:
    return block(PR_VERIFY_BLOCK.format(reason=reason, remedy=remedy.format(script=VERIFY_SCRIPT, **values)))


def require_verified(workdir: str, heads: list[str]) -> None:
    top = verify_record.toplevel(workdir)
    if top is None:
        raise refuse(f"`{workdir}` is not inside a git checkout", VERIFY_REMEDY_NO_CHECKOUT)
    if len(set(heads)) > 1:
        named = ", ".join(f"`{head}`" for head in heads)
        raise refuse(f"it names more than one `--head` branch ({named})", "Give `--head` once.")
    current = verify_record.commit(top)
    branch = heads[0].split(":", 1)[-1] if heads else ""
    if heads:
        target = verify_record.commit(top, branch)
        if target is None:
            raise refuse(f"its `--head` branch `{heads[0]}` is not a local branch the guard can read", VERIFY_REMEDY_NO_BRANCH)
    else:
        target = current
        if target is None:
            raise refuse("this checkout has no commit yet", VERIFY_REMEDY_NO_COMMIT)
    ok, reason, record = verify_record.verdict(top, target, is_protected_path)
    if ok:
        return
    # Name a remedy that can lift this block, or the model loops on one that cannot.
    if target != current:
        raise refuse(reason, VERIFY_REMEDY_OTHER_BRANCH, branch=branch)
    pending = uncommitted(top, target)
    if pending:
        raise refuse(reason, VERIFY_REMEDY_UNCOMMITTED, paths=verify_record.listing(pending))
    if record is not None:
        raise refuse(reason, VERIFY_REMEDY_FAILED if record["exit"] != 0 else VERIFY_REMEDY_UNSTABLE)
    raise refuse(reason, VERIFY_REMEDY_RUN)


def uncommitted(top: str, target: str) -> list[str]:
    """What a check run in this checkout would see that its commit `target` lacks."""
    read = verify_record.worktree_paths(top, target, is_protected_path, verify_record.known_outputs(top))
    return read[0] if read else []


def check_pr_verified(command: str, cwd: str, environ: dict[str, str]) -> None:
    """`gh pr create` needs a passing `scripts/verify.py` record on the tree it opens.
    No override lifts it (`environ` is unused, kept for the checks' shared signature)."""
    read_sources: set[str] = set()
    found_all = walk_commands(command, cwd)
    for found in found_all:
        if found.untrusted and not found.unresolved and found.source not in read_sources:
            read_sources.add(found.source)  # a quoted operator: the text is read too (`untrusted_pieces`)
            for piece in untrusted_pieces(found.source):
                for verb in untrusted_text_verbs(piece):
                    if verb in {"create", "new"}:
                        raise block(PR_QUOTED_OPERATOR.format(verb=verb))
                if gh_api_text_creates(piece):
                    raise block(PR_API_CREATE[gh_args.UNREADABLE_API].format(what="could open a pull request"))
        if found.unreadable:
            raise block(PR_VERIFY_UNREADABLE + api_note(found.text))
        if found.unresolved:
            if shell_tokens.words_in_order(found.text, shell_tokens.WORD_GH, shell_tokens.WORD_PR, CREATE_WORD):
                raise block(PR_VERIFY_UNREADABLE)
            if gh_api_text_creates(found.text):
                raise block(PR_API_CREATE[gh_args.UNREADABLE_API].format(what="could open a pull request"))
            continue
        for args, cut in gh_api_calls(found):
            effect = gh_args.api_effect(args, cut)
            if effect in {gh_args.CREATE_API, gh_args.UNREADABLE_API}:
                raise block(PR_API_CREATE[effect].format(what=API_WHAT[effect]))
        for verb, args, cut in gh_verbs(found):
            if verb not in {"create", "new", gh_args.UNKNOWN}:
                continue  # a revert's tree is made on the server
            if verb == gh_args.UNKNOWN:
                raise block(PR_VERIFY_UNKNOWN)
            flags = gh_args.walk(args, verb, cut)
            if flags.asks_help:
                continue
            if flags.unknown_flags:
                raise block(PR_VERIFY_UNKNOWN_FLAG.format(flag=flags.unknown_flags[0]))
            if flags.expanded:
                raise block(PR_VERIFY_EXPANDED)
            if found.workdir is None:
                raise block(
                    "the guard cannot follow the directory this `gh pr create` runs in, so it "
                    "cannot check which commit it opens. Run it as a plain command from the repository."
                )
            require_verified(found.workdir, flags.heads)


UNSEEN_SCRIPT = (
    "a shell in this command runs text the guard cannot read as commands (its stdin from a "
    "here-document, a here-string or a pipe, a process substitution, or a substitution in its "
    "`-c` or `eval` text), and that text has {what}. Run {what} as a plain command, so the guard "
    "can check it."
)
UNSEEN_FED = re.compile(r"<|\|")
UNSEEN_HEAD_TEXT = re.compile(r"[a-z]*sh[\d.]*\b|\b(?:source|eval)\b|(?:^|[\s;&|(])\.(?=\s)")


def unseen_texts(command: str, cwd: str) -> list[str]:
    """The text of what a shell here runs unseen (`shell_tokens.unseen_script`): the whole command
    when a shell reads its stdin, the bodies of its substitutions when one holds the script."""
    bare = re.sub(r"[\\'\"]", "", command)  # the walk reads words unquoted: `b\ash`, `ba''sh`
    if not UNSEEN_HEAD_TEXT.search(bare) and not (("$" in command or "`" in command) and UNSEEN_FED.search(command)):
        return []
    kinds = {found.unseen for found in walk_commands(command, cwd) if found.unseen}
    if shell_tokens.UNSEEN_TEXT in kinds:
        return [command]
    if not kinds:
        return []
    bodies: list[str] = []
    for body in shell_tokens.inner_commands(command.replace("<(", "$(").replace(">(", "$("), shell_tokens.Walk()):
        if body is None:
            return [command]  # past the budget: all of it
        bodies.append(body)
    return bodies


def check_expanded_git(command: str, cwd: str) -> None:
    """A command name that is an expansion the guard cannot resolve (`$GIT push`, `$(which git)
    push`, `"$(command -v git)" push`) may be git: its words, read as git's, block when they push
    with a force or delete flag or commit (`unseen_git`)."""
    if "$" not in command and "`" not in command:
        return
    for found in walk_commands(command, cwd):
        if found.unresolved or not found.argv:
            continue
        argv = shell_tokens.drop_redirections(found.argv)
        # the command word, or, behind a command that is not a printing one, any later word
        # (`setsid $GIT push`)
        printing = shell_tokens.head_name(argv[0]) in shell_tokens.INERT_HEADS if argv else True
        for position, head in enumerate(argv):
            if is_git_executable(head) or (position and printing):
                break  # from a `git` word on, the walker reads git's own words
            follows_expansion = position and ("$" in argv[position - 1] or "`" in argv[position - 1])
            if ("$" in head or "`" in head) and not follows_expansion:
                # one reading per run of expansions: the first one's reads past the rest (`$X $Y push`)
                expanded_git_words(argv[position + 1 :])


def expanded_git_words(words: list[str]) -> None:
    """Block when `words`, read as the words of git behind an expansion, define an alias
    (`-c alias.x=...`), or push with a force, delete or no-verify flag, or commit."""
    index = 0
    while index < len(words):
        word = words[index]
        if word in GIT_GLOBAL_VALUE:
            if word == "-c" and words[index + 1 : index + 2] and words[index + 1].lower().startswith("alias."):
                raise block(EXPANDED_GIT.format(what="an inline alias (`-c alias.`)"))
            index += 2
        elif word.startswith("-") or shell_tokens.may_vanish(word):
            index += 1
        else:
            break
    if index >= len(words) or words[index] not in {"push", "commit"}:
        return
    # git's own words, as the shell hands them over (a quoted `;` in a value is no cut), and the
    # text reading as well
    if words[index] == "commit":
        what = "`git commit`"
    elif any(push_marker(word) for word in words[index + 1 :]):
        what = "`git push` with a force, delete or no-verify flag"
    else:
        what = unseen_git(" ".join(["git"] + words[index:]))
    if what:
        raise block(EXPANDED_GIT.format(what=what))


EXPANDED_GIT = (
    "this command's name is an expansion the guard cannot resolve, and its words read as {what}. "
    "Run git by its name, so the guard can check it."
)


def gated_in_text(text: str, environ: dict[str, str]) -> str | None:
    """What the rules for text that did not parse find gated in `text`: a gated `gh` (the user's
    AITK_PR_READY=1 lifts only ready, merge and a non-draft open), a `gh pr create` or a `gh api`
    PR creation, a forced or deleting `git push`, a `git commit`; None if nothing."""
    if not shell_tokens.truthy(environ.get("AITK_PR_READY")):
        for verb in unresolved_gated(text):
            return f"`gh pr {verb}`"
        if shell_tokens.mentions_api_publish(text):
            return "a `gh api` pull request call"
    if shell_tokens.words_in_order(text, shell_tokens.WORD_GH, shell_tokens.WORD_PR, CREATE_WORD):
        return "`gh pr create`"
    if gh_api_text_creates(text):
        return "a `gh api` pull request creation"
    return unseen_git(text)


def check_unseen_script(command: str, cwd: str, environ: dict[str, str]) -> None:
    """What a shell runs that the guard never reads as commands (`unseen_texts`, here-document
    bodies included) is read by the rules for text that did not parse (`gated_in_text`)."""
    for text in unseen_texts(command, cwd):
        what = gated_in_text(text, environ)
        if what:
            raise block(UNSEEN_SCRIPT.format(what=what))


UNREAD_VALUE = (
    "`{word}` is set in this command to a value the guard cannot read, and the text that can be its "
    "value has {what}. Write the command literally, so the guard can check it."
)


def unread_value_texts(command: str) -> list[tuple[str, str]]:
    """(word, text) for a command word `$N` that the command sets to a value the guard cannot read
    (`read -r C <<< ...`, `printf -v C ...`): the text that can be its value, which is every segment
    that writes N (not its uses) and every here-string and here-document body."""
    try:
        tokens = shell_tokens.tokenize(command)
    except ValueError:
        return []
    values = shell_values.assigned_values(tokens, command)
    names = {
        name
        for index, token in enumerate(tokens)
        if (name := shell_values.plain_variable(token)) in values
        and values[name].unknown
        and shell_values.command_position(tokens, index)
    }
    if not names:
        return []
    texts: list[str] = []
    for _start, segment in shell_lex.segment_spans(tokens):
        joined = " ".join(segment)
        if shell_values.plain_variable(segment[0]) not in names and any(
            re.search(rf"(?<![A-Za-z0-9_$]){re.escape(name)}(?![A-Za-z0-9_])", joined) for name in names
        ):
            texts.append(joined)
    texts += [tokens[index + 1] for index, token in enumerate(tokens) if token == "<<<" and index + 1 < len(tokens)]
    texts += shell_lex.heredoc_bodies(command)
    word = "$" + sorted(names)[0]
    return [(word, text) for text in texts]


def check_unread_value(command: str, environ: dict[str, str]) -> None:
    """A command word the command sets to a value the guard cannot read is read as the text that
    can be its value (`read -r C <<< "git push --force origin main"; $C`)."""
    if "$" not in command:
        return
    for word, text in unread_value_texts(command):
        what = gated_in_text(text, environ)
        if what:
            raise block(UNREAD_VALUE.format(word=word, what=what))


def evaluate(command: str, cwd: str, environ: dict[str, str]) -> None:
    """Raise Blocked when `command`, run in `cwd`, breaks a guarded rule."""
    _WALKED.clear()
    guard_base.GIT_OUTPUTS.clear()
    _WALKING[0] = guard_base.CACHING[0] = True
    try:
        evaluate_walked(command, cwd, environ)
    finally:
        _WALKING[0] = guard_base.CACHING[0] = False
        _WALKED.clear()
        guard_base.GIT_OUTPUTS.clear()


def evaluate_walked(command: str, cwd: str, environ: dict[str, str]) -> None:
    """`evaluate`, with one shared walk of the command's words."""
    if not command or not cwd:
        return
    check_override_assignment(command, cwd)
    try:
        tokens = shell_tokens.tokenize(command)
    except ValueError as error:
        if MENTIONS_GIT.search(command):
            raise block(
                f"this command could not be parsed ({error}), so the git guard cannot "
                "check it. Rewrite it with balanced quotes."
            )
        return
    if not tokens:
        return

    if has_unsafe_git_substitution(command):
        raise block("git commit/push inside command substitution or process substitution bypasses safety checks")

    check_pr_publish(command, cwd, environ)
    check_pr_verified(command, cwd, environ)
    check_unseen_script(command, cwd, environ)
    check_unread_value(command, environ)
    check_expanded_git(command, cwd)
    check_actions(parse_git_actions(tokens, cwd))


def check_actions(found: list[dict]) -> None:
    """The git rules over one command's git actions, in order: a configured alias is expanded
    first, then each action is checked with what the earlier ones staged, switched or configured."""
    actions: list[dict] = []
    for action in found:
        if action.get("subcommand") in CHECKED_SUBCOMMANDS:
            actions.append(action)
        else:
            actions.extend(expand_configured_alias(action))

    added: list[str] = []
    switched = remote_config = False
    for action in actions:
        subcommand = action.get("subcommand")
        if action.get("speculative"):
            check_speculative(action)
            continue
        args = own_args(action.get("args", []))
        if subcommand in {"add", "stage"}:
            added.extend(paths_added(action))
        elif subcommand == "update-index":
            added.extend(update_index_paths(action))
        elif subcommand == "commit":
            check_commit(action, added)
        elif subcommand in {"push", "send-pack"}:
            if remote_config:
                raise block(
                    "this command changes a remote's push or mirror configuration before it "
                    "pushes, so the guard cannot tell what the push sends. Change the "
                    "configuration and push as separate commands."
                )
            check_push({**action, "branch_unknown": True} if switched else action)
        elif subcommand in {"checkout", "switch"} and switches_branch(subcommand, args):
            switched = True
        elif subcommand == "config" and any(REMOTE_PUSH_KEY.match(arg) for arg in args):
            remote_config = True
        elif subcommand == "remote" and any(arg.startswith("--mirror") for arg in args):
            remote_config = True
        elif subcommand in {"merge", "am", "rebase"} and any(
            long_option_prefix(arg, "--no-verify", "--no-veri") for arg in args
        ):
            raise block(f"git {subcommand} --no-verify skips the hooks the toolkit runs")


CHECKED_SUBCOMMANDS = {
    "commit", "push", "add", "stage", "update-index", "send-pack", "checkout", "switch", "config",
    "remote", "merge", "am", "rebase",
}
REMOTE_PUSH_KEY = re.compile(r"(?i)remote\.[^.]+\.(?:push|mirror)$|push\.")


def switches_branch(subcommand: str, args: list[str]) -> bool:
    """Whether `git checkout` or `git switch` with these words may change the branch: anything but
    a file checkout (`git checkout -- file`, `git checkout <tree> -- file`)."""
    if subcommand == "switch":
        return True
    return "--" not in args and not any(arg in {"-p", "--patch"} for arg in args)


def main() -> int:
    raw = sys.stdin.read()
    command = ""
    try:
        payload = json.loads(raw or "{}")
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or ""
        cwd = payload.get("cwd") or ""
        if not isinstance(command, str) or not isinstance(cwd, str):
            return 0
        with shell_tokens.deadline(DEADLINE_SECONDS):
            evaluate(command, cwd, dict(os.environ))
    except Blocked as blocked:
        print(str(blocked), file=sys.stderr)
        return 2
    except shell_tokens.DeadlineExceeded:
        # A hook past its timeout fails open, so a command the guard could not finish
        # reading blocks: its raw text can hide git behind quotes (`g'i't`) a mention
        # match cannot see, and no ordinary command takes this long to read.
        print(
            "BLOCKED: this command is too large or complex for the git guard to check in "
            "time. Run it as a simpler command; do not work around the hook.",
            file=sys.stderr,
        )
        return 2
    except Exception as error:  # noqa: BLE001 - an internal error blocks git, gh and overrides
        text = command if isinstance(command, str) else raw
        # quoting can hide the word from a raw match (`g'i't`): read it as the shell does
        if any(
            MENTIONS_GIT.search(form) or OVERRIDE_MENTION.search(form)
            for form in (text, shell_tokens.unquoted(text))
        ):
            print(
                f"BLOCKED: the git guard hook failed ({type(error).__name__}: {error}). "
                "Stop and ask the user; do not work around the hook.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
