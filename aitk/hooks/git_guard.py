"""The git guard: block git and gh commands that bypass the toolkit's safety rules.

Run as `python3 -m aitk.hooks.git_guard` with the PreToolUse payload on stdin
(`hooks/prevent-project-commit.sh` does this). Exit 0 allows, exit 2 blocks
with the reason on stderr, which the agent sees.

Blocked:
- `git commit --no-verify` / `-n`, `--no-gpg-sign`, and the `core.hooksPath`
  and `commit.gpgsign=false` overrides, also through `-c`, `--config-env`,
  `GIT_CONFIG_*` and aliases;
- `git push --no-verify`, force-pushing main or master, and deleting them;
- a commit that includes a local workflow state file (`STATE_FILES` from
  `aitk.project_state`) or any path under `.ai-toolkit/`, including files added
  earlier in the same command (`git add PROJECT.md && git commit`): the hook
  runs before the add, so the staged set is `git diff --cached` plus what those
  adds would stage;
- `gh pr ready` and `gh pr merge`, unless the user set `AITK_PR_READY=1` in the
  environment the session started with (set only when the user asked in
  words). `SKIP_PR_GATE=1` does not lift them;
- a command that assigns or exports any toolkit override itself (a prefix, an
  assignment-only segment, `env`, `export`/`declare`/`typeset`/`readonly`/
  `local`, a literal `+=` append, inside `bash -c`, `eval`, `env -S`, a
  substitution or a function body, behind a redirection, or after an `env`,
  shell or `eval` word later in the argv), whatever it runs: overrides count
  only from the session environment, so the hook never reads them from the
  command.

Every command the shell would run is checked: newline- and `;`-separated
commands, and-lists and or-lists, subshells, `sh -c` and `eval` payloads,
command substitutions, shell functions, and commands behind `env`, `sudo`,
`command`, `timeout`, `nohup`, `xargs`, `nice`, `ionice`, `stdbuf` or `time`.
A command that mentions git or gh and cannot be parsed blocks; an internal
error blocks a command that mentions git, gh or an override, and the wrapper
fails closed on those when python3 is missing.

Known limits (a tripwire, not a shell sandbox): a git alias defined in a file
the hook cannot read, `gh api` calls, and programs that run git themselves are
not seen. Substitution bodies are scanned wherever they are quoted, so a
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

What actually protects the gates is elsewhere: `bin/aitk deliver` cannot open a
ready PR (it has no flag and reads no override), and `gh pr ready`/`gh pr merge`
read `AITK_PR_READY` only from the session environment. This check keeps the
agent from shopping for an override it cannot get.

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
- a redirection operator erased with a quoted or numeric option value
  (`env -u '>' NAME=1 ...`);
- shell-specific grammar: a zsh anonymous function (`() { ...; }`), a function
  named after a wrapper (`env() { ...; }`), `nocorrect`/`repeat N`/`coproc`
  before a prefix, and a nameref set by a plain value
  (`declare -n r; r=NAME; declare -x r=1`);
- `read`, `printf -v` and `mapfile` (write targets, not assignments),
  `source`/`.` and scripts run separately, dynamically built names (`${!v}`,
  `eval "AITK_PR_$X=1"`), ANSI-C-quoted names (`$'\\x41ITK_PR_READY=1'`),
  substitution-built assignments (`env $(printf '...') ...`), aliases (the body
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
`create`/`new`). A mention makes the command unreadable and it blocks. No alias is
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
head (`echo '()' '{' gh pr ready 12`). Known limits, each a real `gh pr ready`/`merge`
it does not see (pinned in `PR_PUBLISH_LIMITS`): `gh` reached through a variable
(`g=gh; $g pr merge 12`), a quoted command string handed to a wrapper that runs it
through a shell without `-c` (`watch 'gh pr ready 12'`, `tmux new-session '...'`), every
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
that text, is read as the git top level instead), and the global options that take a separate value
(`--attr-source`, `--super-prefix`, `--namespace`, `-C`, `-c`, `--git-dir`,
`--work-tree`, `--config-env`) do not hide the subcommand. The patterns that scan
unresolved text are searched in order, once (`shell_tokens.words_in_order`), so a
long text that does not match is read in linear time, and so is the scan of
`$(...)`, backtick and `<(...)` bodies for a git commit or push (`has_unsafe_git_substitution`:
one pass over the openers, a position index for the git words).
"""

from __future__ import annotations

import bisect
import json
import os
import re
import shlex
import subprocess
import sys
from typing import Iterator

from aitk.hooks import shell_tokens
from aitk.project_state import STATE_FILES


SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&"}
SHELL_KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "for", "select", "case", "!", "{"}
# Wrappers that run the rest of the line as a command, after their own options.
RUNNING_WRAPPERS = {"timeout", "nohup", "xargs", "nice", "ionice", "stdbuf", "exec"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
MENTIONS_GIT = re.compile(r"\bgit\b|\bgh\b", re.I)
# The in-process time limit of `main()`. A hook past its timeout in hooks/hooks.json (30 s)
# fails open, so the guard stops itself first and blocks what it could not finish reading.
DEADLINE_SECONDS = 20.0
GH_GLOBAL_VALUE_FLAGS = {"-R", "--repo", "--hostname"}
PROTECTED_DIRECTORY = ".ai-toolkit"


class Blocked(Exception):
    pass


def block(message: str) -> Blocked:
    return Blocked(f"BLOCKED: {message}")


def resolve_path(base: str, path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base, path))


def is_git_executable(token: str) -> bool:
    """`git` or a path to it, whatever the case (`GIT` runs git on a case-insensitive filesystem)."""
    return token.lower() == "git" or ("/" in token and os.path.basename(token).lower() == "git")


def config_pair(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        return raw, ""
    key, value = raw.split("=", 1)
    return key, value


def configs_from_env(env: dict[str, str]) -> list[str]:
    configs: list[str] = []
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        return configs
    for index in range(count):
        key = env.get(f"GIT_CONFIG_KEY_{index}")
        value = env.get(f"GIT_CONFIG_VALUE_{index}", "")
        if key:
            configs.append(f"{key}={value}")
    return configs


def register_config(action: dict, raw_config: str) -> None:
    action["configs"].append(raw_config)
    key, value = config_pair(raw_config)
    if key.lower().startswith("alias."):
        action["aliases"][key.split(".", 1)[1]] = "commit --no-verify" if value == "<config-env>" else value


def git_base(action: dict) -> tuple[list[str], str]:
    git_args = ["git"]
    if action.get("git_dir"):
        git_args.append(f"--git-dir={action['git_dir']}")
    if action.get("work_tree"):
        git_args.append(f"--work-tree={action['work_tree']}")
    return git_args, action["workdir"]


def git_output(action: dict, args: list[str]) -> str | None:
    git_args, workdir = git_base(action)
    env = os.environ.copy()
    env.update(action.get("env", {}))
    try:
        result = subprocess.run(
            git_args + args,
            cwd=workdir,
            env=env,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def shell_tokens_or_empty(command_text: str) -> list[str]:
    try:
        return shell_tokens.tokenize(command_text)
    except ValueError:
        return []


def expand_shell_payload(command_text: str, positional: list[str]) -> list[str]:
    nested = shell_tokens_or_empty(command_text)
    if not nested:
        return []
    expanded: list[str] = []
    positional_zero = positional[0] if positional else ""
    positional_args = positional[1:] if positional else []
    for token in nested:
        if token in {"$@", "${@}", "\\$@", "\\${@}"}:
            if positional_args:
                expanded.extend(positional_args)
            else:
                expanded.append(token)
        elif token in {"$*", "${*}", "\\$*", "\\${*}"}:
            expanded.append(" ".join(positional_args) if positional_args else token)
        else:
            replaced = token
            if positional_zero:
                replaced = replaced.replace("\\${0}", positional_zero).replace("${0}", positional_zero)
                replaced = replaced.replace("\\$0", positional_zero).replace("$0", positional_zero)
            for index, value in enumerate(positional_args, start=1):
                replaced = replaced.replace(f"\\${{{index}}}", value).replace(f"${{{index}}}", value)
                replaced = replaced.replace(f"\\${index}", value).replace(f"${index}", value)
            expanded.append(replaced)
    return expanded


def expand_positional_tokens(tokens: list[str], positional: list[str]) -> list[str]:
    expanded: list[str] = []
    for token in tokens:
        if token in {"$@", "${@}"}:
            expanded.extend(positional)
        elif token in {"$*", "${*}"}:
            expanded.append(" ".join(positional))
        else:
            expanded.append(token)
    return expanded


def shell_var_name(token: str) -> str | None:
    if token.startswith("${") and token.endswith("}"):
        return token[2:-1]
    if token.startswith("$") and len(token) > 1:
        return token[1:]
    return None


SUBSTITUTION_START = re.compile(r"`|\$\(|<\(")
GIT_WORD_START = re.compile(r"\bgit(?=[\s\-$])", re.I)
COMMIT_OR_PUSH = re.compile(r"(?:commit|push)\b")
VARIABLE_GIT_ASSIGNMENT = re.compile(r"=git", re.I)
VARIABLE_GIT_ARGUMENT = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\s+(?:commit|push)\b")


def substitution_bodies(text: str) -> Iterator[str]:
    """Each `` `...` ``, `$(...)` and `<(...)` span, left to right and without overlap.

    The spans `` `[^`]*`|\\$\\([^)]*\\)|<\\([^)]*\\) `` would find, in linear time: an opener
    with no closer after it ends the search for that kind, where the pattern retries it
    from every later opener across the rest of the text.
    """
    position = 0
    closed = {"`": True, ")": True}
    while True:
        start = SUBSTITUTION_START.search(text, position)
        if start is None:
            return
        closer = "`" if start.group(0) == "`" else ")"
        end = text.find(closer, start.end()) if closed[closer] else -1
        if end < 0:
            closed[closer] = False
            position = start.end()
            continue
        yield text[start.start() : end + 1]
        position = end + 1


def positions_of(pattern: re.Pattern[str], text: str) -> list[int]:
    return [match.start() for match in pattern.finditer(text)]


def first_from(positions: list[int], at: int) -> int | None:
    """The first of the sorted `positions` that is `at` or later."""
    index = bisect.bisect_left(positions, at)
    return positions[index] if index < len(positions) else None


def variable_name_before(text: str, end: int) -> bool:
    """Whether `text` ends, before `end`, in an identifier: `[A-Za-z_][A-Za-z0-9_]*`."""
    index = end
    while index > 0 and text[index - 1].isascii() and (text[index - 1].isalnum() or text[index - 1] == "_"):
        index -= 1
        if text[index].isalpha() or text[index] == "_":
            return True
    return False


def body_runs_git_commit_or_push(body: str) -> bool:
    """`git commit`/`git push` (a dashed or `${...}` spelling too, or `NAME=git ... $VAR push`).

    Equivalent to the patterns `\\bgit(?:\\s+|-|\\$\\{[^}]+\\})[^)]*(commit|push)\\b` and
    `[A-Za-z_]\\w*=git[^)]*\\$[A-Za-z_]\\w*\\s+(commit|push)\\b`, in linear time: the word
    positions are listed once and each `git` start looks up the next one by bisection, where
    the patterns retry the tail from every `git` word across the whole body.
    """
    pushes = positions_of(COMMIT_OR_PUSH, body)
    arguments = positions_of(VARIABLE_GIT_ARGUMENT, body)
    if not pushes and not arguments:
        return False
    parentheses = positions_of(re.compile(r"\)"), body)
    braces = positions_of(re.compile(r"\}"), body)

    def reaches(after: int, targets: list[int]) -> bool:
        # a target at or after `after` with no `)` between
        target = first_from(targets, after)
        if target is None:
            return False
        closing = first_from(parentheses, after)
        return closing is None or closing >= target

    if pushes:
        for start in GIT_WORD_START.finditer(body):
            after = start.end()
            if body[after] == "$":
                if body[after + 1 : after + 2] != "{":
                    continue
                close = first_from(braces, after + 2)
                if close is None or close == after + 2:
                    continue  # `${...}` needs a name and a closing brace
                after = close
            if reaches(after + 1, pushes):
                return True
    if arguments:
        for assignment in VARIABLE_GIT_ASSIGNMENT.finditer(body):
            if variable_name_before(body, assignment.start()) and reaches(assignment.end(), arguments):
                return True
    return False


def has_unsafe_git_substitution(command_text: str) -> bool:
    return any(body_runs_git_commit_or_push(body) for body in substitution_bodies(command_text))


def segment_end_index(tokens: list[str], start: int) -> int:
    end = start
    while end < len(tokens) and tokens[end] not in SEPARATORS:
        end += 1
    return end


def new_action(workdir: str, aliases: dict, env: dict) -> dict:
    action = {
        "subcommand": None,
        "index": None,
        "args": [],
        "workdir": workdir,
        "git_dir": None,
        "work_tree": None,
        "configs": [],
        "aliases": dict(aliases),
        "env": dict(env),
    }
    for raw_config in configs_from_env(env):
        register_config(action, raw_config)
    return action


def parse_git_actions(
    tokens: list[str],
    base_workdir: str,
    depth: int = 0,
    inherited_env: dict | None = None,
    inherited_vars: dict | None = None,
    inherited_functions: dict | None = None,
    inherited_aliases: dict | None = None,
) -> list[dict]:
    """Every git invocation in `tokens`, in order, with its effective context."""
    actions: list[dict] = []
    if depth > 8:
        return actions
    current_workdir = base_workdir
    exported_env = dict(inherited_env or {})
    env_assignments = dict(exported_env)
    shell_vars = dict(inherited_vars or {})
    shell_functions = dict(inherited_functions or {})
    inherited_alias_map = dict(inherited_aliases or {})
    command_start = True
    count = len(tokens)
    i = 0

    def recurse(sub_tokens: list[str], workdir: str, env: dict) -> list[dict]:
        return parse_git_actions(
            sub_tokens,
            workdir,
            depth + 1,
            env,
            dict(shell_vars),
            dict(shell_functions),
            dict(inherited_alias_map),
        )

    while i < count:
        token = tokens[i]
        if token in SEPARATORS:
            command_start = True
            env_assignments = dict(exported_env)
            i += 1
            continue
        if command_start and ASSIGNMENT.match(token):
            key, value = token.split("=", 1)
            shell_vars[key] = value
            env_assignments[key] = value
            i += 1
            continue
        if command_start and token == "export":
            segment_end = segment_end_index(tokens, i + 1)
            for export_token in tokens[i + 1 : segment_end]:
                if ASSIGNMENT.match(export_token):
                    key, value = export_token.split("=", 1)
                    shell_vars[key] = value
                    exported_env[key] = value
                elif export_token in shell_vars:
                    exported_env[export_token] = shell_vars[export_token]
            env_assignments = dict(exported_env)
            command_start = False
            i = segment_end
            continue
        if command_start and token in SHELL_KEYWORDS:
            i += 1
            continue
        if command_start and token in {"time", "noglob"}:
            i += 1
            continue
        if command_start and os.path.basename(token) in RUNNING_WRAPPERS:
            # `timeout 60 git ...`, `nohup git ...`, `xargs git ...`, `nice -n 5 git ...`:
            # skip the wrapper and its own options; the rest is the command.
            segment_end = segment_end_index(tokens, i + 1)
            rest = shell_tokens.skip_options(
                os.path.basename(token), tokens[i + 1 : segment_end], shell_tokens.Effects()
            )
            i = segment_end - len(rest)
            continue
        if command_start and token == "cd":
            segment_end = segment_end_index(tokens, i + 1)
            if i + 1 < segment_end:
                current_workdir = resolve_path(current_workdir, tokens[i + 1])
            command_start = False
            i = segment_end
            continue
        if command_start and token == "function" and i + 2 < count:
            fn_name = tokens[i + 1]
            brace_index = i + 2
            if brace_index < count and tokens[brace_index] == "()":
                brace_index += 1
            if brace_index < count and tokens[brace_index] == "{":
                body_start = brace_index + 1
                body_end = body_start
                while body_end < count and tokens[body_end] != "}":
                    body_end += 1
                if body_end < count:
                    shell_functions[fn_name] = tokens[body_start:body_end]
                    i = body_end + 1
                    command_start = False
                    continue
        if command_start and i + 2 < count and tokens[i + 1] == "()" and tokens[i + 2] == "{":
            body_start = i + 3
            body_end = body_start
            while body_end < count and tokens[body_end] != "}":
                body_end += 1
            if body_end < count:
                shell_functions[token] = tokens[body_start:body_end]
                i = body_end + 1
                command_start = False
                continue
            i += 3
            continue
        if command_start and token in {"bash", "sh", "zsh"}:
            segment_end = segment_end_index(tokens, i + 1)
            j = i + 1
            while j < segment_end:
                shell_arg = tokens[j]
                if shell_arg == "-c" or (
                    shell_arg.startswith("-") and not shell_arg.startswith("--") and "c" in shell_arg[1:]
                ):
                    command_index = j + 1
                    while command_index < segment_end and tokens[command_index] == "--":
                        command_index += 1
                    if command_index < segment_end:
                        positional = tokens[command_index + 1 : segment_end]
                        actions.extend(
                            recurse(
                                expand_shell_payload(tokens[command_index], positional),
                                current_workdir,
                                dict(exported_env),
                            )
                        )
                    break
                j += 1
            command_start = False
            i = segment_end
            continue
        if command_start and token == "eval":
            segment_end = segment_end_index(tokens, i + 1)
            eval_parts = tokens[i + 1 : segment_end]
            payload = eval_parts[0] if len(eval_parts) == 1 else " ".join(shlex.quote(part) for part in eval_parts)
            actions.extend(recurse(shell_tokens_or_empty(payload), current_workdir, dict(exported_env)))
            command_start = False
            i = segment_end
            continue
        if command_start and token in {"sudo", "doas"}:
            i += 1
            while i < count and tokens[i] not in SEPARATORS:
                wrapper_token = tokens[i]
                if wrapper_token in {"-u", "-g", "-h", "-p", "-C"}:
                    i += 2
                    continue
                if wrapper_token.startswith(("-u=", "-g=", "-h=", "-p=", "-C=")):
                    i += 1
                    continue
                if wrapper_token.startswith("-"):
                    i += 1
                    continue
                break
            continue
        if command_start and token in {"command", "builtin"}:
            i += 1
            while i < count and tokens[i].startswith("-") and tokens[i] not in SEPARATORS:
                i += 1
            continue
        if command_start and token == "env":
            segment_end = segment_end_index(tokens, i + 1)
            env_workdir = current_workdir
            child_env = dict(env_assignments)
            j = i + 1
            while j < segment_end:
                env_token = tokens[j]
                if ASSIGNMENT.match(env_token):
                    key, value = env_token.split("=", 1)
                    shell_vars[key] = value
                    child_env[key] = value
                    j += 1
                    continue
                if env_token in {"-i", "-0", "--ignore-environment", "--null"}:
                    child_env = {}
                    j += 1
                    continue
                if env_token in {"-u", "--unset", "-C", "--chdir"}:
                    if env_token in {"-C", "--chdir"} and j + 1 < segment_end:
                        env_workdir = resolve_path(current_workdir, tokens[j + 1])
                    elif j + 1 < segment_end:
                        child_env.pop(tokens[j + 1], None)
                    j += 2
                    continue
                if env_token.startswith("--chdir="):
                    env_workdir = resolve_path(current_workdir, env_token.split("=", 1)[1])
                    j += 1
                    continue
                if env_token.startswith("--unset="):
                    child_env.pop(env_token.split("=", 1)[1], None)
                    j += 1
                    continue
                if env_token.startswith("-"):
                    j += 1
                    continue
                break
            if j < segment_end:
                actions.extend(recurse(tokens[j:segment_end], env_workdir, child_env))
            command_start = False
            i = segment_end
            continue
        word = token
        if command_start and shell_var_name(token) is not None:
            word = shell_vars.get(shell_var_name(token) or "", token)  # `G=git-push; $G -f origin main`
        dashed = shell_tokens.git_argv([word]) if command_start else None
        if dashed and len(dashed) == 2:
            # a dashed entry point (`git-push -f origin main`, a path ending in `/git-push`,
            # or a variable that holds one) is `git push -f origin main`; any other
            # `git-*` word is an ordinary executable. The action is built here, from its own
            # segment: splicing the tokens, or keeping the rest of the line per action, would
            # cost the whole remaining text every time.
            action = new_action(current_workdir, inherited_alias_map, env_assignments)
            action["subcommand"] = dashed[1]
            action["index"] = i
            action["args"] = tokens[i + 1 : segment_end_index(tokens, i + 1)]
            actions.append(action)
            command_start = False
            i += 1
            continue
        dynamic_git = None
        if command_start:
            dynamic_git = re.fullmatch(
                r"git(?:\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*)(?:(commit|push))?", token, re.I
            )

        if command_start and dynamic_git:
            subcommand = dynamic_git.group(1)
            args = tokens[i + 1 : segment_end_index(tokens, i + 1)]
            if subcommand is None and args:
                subcommand = args[0]
                args = args[1:]
            action = new_action(current_workdir, inherited_alias_map, env_assignments)
            action["subcommand"] = subcommand
            action["index"] = i
            action["args"] = args
            actions.append(action)
            command_start = False
            i += 1
            continue

        var_name = shell_var_name(token) if command_start else None
        variable_git = var_name and is_git_executable(shell_vars.get(var_name, ""))

        if command_start and token in shell_functions:
            segment_end = segment_end_index(tokens, i + 1)
            positional = tokens[i + 1 : segment_end]
            function_tokens = expand_positional_tokens(shell_functions[token], positional)
            actions.extend(recurse(function_tokens, current_workdir, dict(exported_env)))
            command_start = False
            i = segment_end
            continue

        if not (command_start and (is_git_executable(token) or variable_git)):
            command_start = False
            i += 1
            continue

        action = new_action(current_workdir, inherited_alias_map, env_assignments)
        j = i + 1
        while j < count:
            opt = tokens[j]
            if opt in SEPARATORS:
                break
            if opt == "-C":
                if j + 1 >= count:
                    break
                action["workdir"] = resolve_path(action["workdir"], tokens[j + 1])
                j += 2
                continue
            if opt == "--git-dir":
                if j + 1 >= count:
                    break
                action["git_dir"] = resolve_path(action["workdir"], tokens[j + 1])
                j += 2
                continue
            if opt.startswith("--git-dir="):
                action["git_dir"] = resolve_path(action["workdir"], opt.split("=", 1)[1])
                j += 1
                continue
            if opt == "--work-tree":
                if j + 1 >= count:
                    break
                action["work_tree"] = resolve_path(action["workdir"], tokens[j + 1])
                action["workdir"] = action["work_tree"]
                j += 2
                continue
            if opt.startswith("--work-tree="):
                action["work_tree"] = resolve_path(action["workdir"], opt.split("=", 1)[1])
                action["workdir"] = action["work_tree"]
                j += 1
                continue
            if opt == "-c":
                if j + 1 >= count:
                    break
                register_config(action, tokens[j + 1])
                j += 2
                continue
            if opt == "--config-env":
                if j + 1 >= count:
                    break
                key, env_name = config_pair(tokens[j + 1])
                register_config(action, f"{key}={env_assignments.get(env_name, '<config-env>')}")
                j += 2
                continue
            if opt.startswith("--config-env="):
                key, env_name = config_pair(opt.split("=", 1)[1])
                register_config(action, f"{key}={env_assignments.get(env_name, '<config-env>')}")
                j += 1
                continue
            if opt in {"--namespace", "--super-prefix", "--attr-source"}:  # `--exec-path` alone takes no value
                j += 2
                continue
            if opt.startswith(("--namespace=", "--exec-path=", "--super-prefix=", "--attr-source=")):
                j += 1
                continue
            if opt.startswith("-"):
                j += 1
                continue
            if opt in action["aliases"]:
                alias_tokens = shell_tokens_or_empty(action["aliases"][opt])
                if alias_tokens:
                    shell_alias = False
                    if alias_tokens[0].startswith("!"):
                        alias_tokens[0] = alias_tokens[0][1:]
                        shell_alias = True
                    if alias_tokens and not shell_alias and not is_git_executable(alias_tokens[0]):
                        alias_tokens = ["git"] + alias_tokens
                    nested_actions = parse_git_actions(
                        alias_tokens + tokens[j + 1 : segment_end_index(tokens, j + 1)],
                        action["workdir"],
                        depth + 1,
                        dict(exported_env),
                        dict(shell_vars),
                        dict(shell_functions),
                        dict(action.get("aliases", {})),
                    )
                    for nested_action in nested_actions:
                        nested_action["configs"] = action["configs"] + nested_action.get("configs", [])
                        nested_action["env"] = dict(action.get("env", {}), **nested_action.get("env", {}))
                    actions.extend(nested_actions)
                break

            action["subcommand"] = opt
            action["index"] = j
            action["args"] = tokens[j + 1 : segment_end_index(tokens, j + 1)]
            actions.append(action)
            break

        command_start = False
        i += 1

    return actions


def expand_configured_alias(action: dict) -> list[dict]:
    subcommand = action.get("subcommand")
    if not subcommand:
        return []
    alias_value = action.get("aliases", {}).get(subcommand)
    if alias_value is None:
        alias_value = git_output(action, ["config", "--get", f"alias.{subcommand}"])
        if alias_value is not None:
            alias_value = alias_value.strip()
    if not alias_value:
        return []

    alias_tokens = shell_tokens_or_empty(alias_value)
    if not alias_tokens:
        return []
    shell_alias = False
    if alias_tokens[0].startswith("!"):
        alias_tokens[0] = alias_tokens[0][1:]
        shell_alias = True
    if alias_tokens and not shell_alias and not is_git_executable(alias_tokens[0]):
        alias_tokens = ["git"] + alias_tokens

    nested = parse_git_actions(
        alias_tokens + action.get("args", []),
        action.get("workdir"),
        1,
        action.get("env", {}),
        inherited_aliases=action.get("aliases", {}),
    )
    for nested_action in nested:
        nested_action["configs"] = action.get("configs", []) + nested_action.get("configs", [])
        nested_action["env"] = dict(action.get("env", {}), **nested_action.get("env", {}))
    return nested


def short_commit_option_has_no_verify(arg: str) -> bool:
    if not arg.startswith("-") or arg.startswith("--"):
        return False
    # For options whose argument may be attached (`-mmsg`, `-Ffile`,
    # `-Ccommit`, `-ccommit`), Git treats the rest of the token as data.
    # Only an `n` before such a consuming option is the no-verify flag.
    for char in arg[1:]:
        if char == "n":
            return True
        if char in {"m", "F", "C", "c"}:
            return False
    return False


def config_value_false(value: str) -> bool:
    return value.strip().lower() in {"false", "no", "off", "0"}


def long_option_prefix(arg: str, option: str, min_prefix: str) -> bool:
    name = arg.split("=", 1)[0]
    return name.startswith("--") and len(name) >= len(min_prefix) and option.startswith(name)


def is_protected_path(path: str) -> bool:
    """A local workflow state file, or anything under `.ai-toolkit/`."""
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    return bool(parts) and (parts[-1] in STATE_FILES or PROTECTED_DIRECTORY in parts)


def own_args(args: list[str]) -> list[str]:
    for stop, token in enumerate(args):
        if token in SEPARATORS:
            return args[:stop]
    return args


def paths_added(action: dict) -> list[str]:
    """What `git add <args>` would stage, as repository paths where git can tell."""
    args = own_args(action.get("args", []))
    listed = git_output(action, ["add", "--dry-run", *args])
    if listed is not None:
        found = []
        for line in listed.splitlines():
            match = re.match(r"^add '(.*)'$", line.strip())
            if match:
                found.append(match.group(1))
        return found
    # The dry run failed (for example an ignored path without -f): fall back to
    # the literal pathspecs, so a refused add still counts as an attempt.
    return [arg for arg in args if not arg.startswith("-")]


def check_commit(action: dict, added_before: list[str]) -> None:
    args = own_args(action.get("args", []))
    for raw_config in action.get("configs", []):
        key, value = config_pair(raw_config)
        key = key.lower()
        if key == "core.hookspath":
            raise block("git commit with core.hooksPath override bypasses pre-commit hooks")
        if key == "commit.gpgsign" and (value == "<config-env>" or config_value_false(value)):
            raise block("git commit with commit.gpgsign=false violates signing rules")

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            break
        if long_option_prefix(arg, "--no-verify", "--no-veri"):
            raise block("git commit --no-verify violates global pre-commit rules")
        if long_option_prefix(arg, "--no-gpg-sign", "--no-g"):
            raise block("git commit --no-gpg-sign violates global signing rules")
        if short_commit_option_has_no_verify(arg):
            raise block("git commit -n bypasses pre-commit hooks")
        if arg in {"-m", "-F", "-C", "-c", "--message", "--file", "--reuse-message", "--reedit-message"}:
            i += 2
            continue
        i += 1

    staged = git_output(action, ["diff", "--cached", "--name-only"])
    candidates = (staged.splitlines() if staged is not None else []) + added_before
    protected = []
    for path in candidates:
        if is_protected_path(path) and path not in protected:
            protected.append(path)
    if protected:
        listing = "\n".join(f"  - {path}" for path in protected)
        raise Blocked(
            "BLOCKED: local workflow state is part of this commit. PROJECT.md and the other "
            "workflow state files, and everything under .ai-toolkit/ (org config, memory, "
            "metrics), stay out of commits.\n"
            f"{listing}\n"
            "Unstage with: git reset HEAD <file>, and do not add these files."
        )


def check_push(action: dict) -> None:
    args = own_args(action.get("args", []))
    for raw_config in action.get("configs", []):
        key, _value = config_pair(raw_config)
        if key.lower() == "core.hookspath":
            raise block("git push with core.hooksPath override bypasses pre-push hooks")

    current_branch = (git_output(action, ["branch", "--show-current"]) or "").strip()
    push_force = False
    dest_main = False
    ref_wide = False
    has_explicit_ref = False
    operands: list[str] = []
    delete_push = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            operands.extend(args[i + 1 :])
            break
        if long_option_prefix(arg, "--no-verify", "--no-veri"):
            raise block("git push --no-verify bypasses pre-push hooks")
        if "=" in arg and (
            long_option_prefix(arg, "--force-with-lease", "--force-w")
            or long_option_prefix(arg, "--force-with-includes", "--force-w")
        ):
            push_force = True
            lease_ref = arg.split("=", 1)[1].split(":", 1)[0]
            if re.fullmatch(r"(refs/heads/)?(main|master)", lease_ref):
                dest_main = True
                has_explicit_ref = True
        if (
            arg in {"--force", "--force-with-lease", "-f"}
            or long_option_prefix(arg, "--force", "--forc")
            or long_option_prefix(arg, "--force-with-lease", "--force-w")
            or long_option_prefix(arg, "--force-with-includes", "--force-w")
        ):
            push_force = True
        elif arg in {"--delete", "-d"} or long_option_prefix(arg, "--delete", "--del"):
            delete_push = True
        elif arg.startswith("--force="):
            push_force = True
            lease_ref = arg.split("=", 1)[1].split(":", 1)[0]
            if re.fullmatch(r"(refs/heads/)?(main|master)", lease_ref):
                dest_main = True
                has_explicit_ref = True
        elif arg in {"--all", "--mirror"}:
            ref_wide = True
        elif arg.startswith("-") and not arg.startswith("--"):
            if "f" in arg[1:]:
                push_force = True
        elif arg.startswith("--"):
            pass
        else:
            operands.append(arg)
        i += 1

    for index, operand in enumerate(operands):
        force_refspec = operand.startswith("+")
        refspec = operand[1:] if force_refspec else operand
        if force_refspec:
            push_force = True
        if refspec == ":":
            ref_wide = True
        if len(operands) >= 2 and index == 0:
            continue
        if len(operands) == 1 and operand in {"origin", "upstream"}:
            continue

        has_explicit_ref = True
        deleting_ref = refspec.startswith(":")
        dest = refspec.rsplit(":", 1)[-1]
        if dest == "HEAD":
            dest = current_branch
        if re.fullmatch(r"(refs/heads/)?(main|master)", dest or ""):
            dest_main = True
            if deleting_ref:
                delete_push = True

    if push_force and not has_explicit_ref and not dest_main:
        push_target = (
            git_output(action, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}"]) or ""
        ).strip()
        if re.fullmatch(r"([^/]+/)?(main|master)", push_target or ""):
            dest_main = True
    if push_force and (ref_wide or dest_main or (not has_explicit_ref and current_branch in {"main", "master"})):
        raise block("force-pushing main/master is not allowed")
    if delete_push and dest_main:
        raise block("deleting main/master is not allowed")


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
}
# `gh`, then `pr`, then `ready` or `merge`, each searched after the one before it: linear in the text
UNRESOLVED_PR_PUBLISH = (shell_tokens.WORD_GH, shell_tokens.WORD_PR, re.compile(r"\b(ready|merge)\b"))


OVERRIDE_VARIABLES = ("AITK_PR_READY", "SKIP_PR_GATE", "SKIP_PRECHECK")
EXPORTING_BUILTINS = {"export", "declare", "typeset", "readonly", "local", "integer", "float"}
# The fallback for command text that did not tokenize or nested too deep: a
# literal assignment or append, or an export-family builtin (also behind
# `builtin` or `command`) that mentions an override before the next separator.
# The builtin and the mention are searched in order within each separated command
# (`unresolved_sets_override`), never as one `builtin.*name` pattern, which
# backtracks across the whole text from every builtin word.
OVERRIDE_ASSIGNMENT = re.compile(r"\b(?:AITK_PR_READY|SKIP_PR_GATE|SKIP_PRECHECK)\+?=")
EXPORTING_BUILTIN = re.compile(r"\b(?:export|declare|typeset|readonly|local|integer|float)\b")
OVERRIDE_MENTION = re.compile(r"\b(?:AITK_PR_READY|SKIP_PR_GATE|SKIP_PRECHECK)\b")
COMMAND_SEPARATOR = re.compile(r"[;&|\n]")
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


def check_pr_publish(command: str, cwd: str, environ: dict[str, str]) -> None:
    """`gh pr ready` and `gh pr merge` need the user's AITK_PR_READY=1 (N4)."""
    if shell_tokens.truthy(environ.get("AITK_PR_READY")):
        return
    for found in shell_tokens.commands(command, cwd):
        if found.unreadable:
            # the work budget is spent, or git is handed text that mentions a gated
            # operation: the text cannot show what runs, so a contiguous `gh` in it
            # proves nothing either way
            raise block(PR_PUBLISH_UNREADABLE)
        if found.unresolved:
            match = shell_tokens.words_in_order(found.text, *UNRESOLVED_PR_PUBLISH)
            if match:
                raise block(PR_PUBLISH_MESSAGE.format(verb=match.group(1), effect=PR_PUBLISH_EFFECT[match.group(1)]))
            continue
        if not found.is_gh:
            continue
        args = found.argv[1:]
        if {"-h", "--help"} & set(args):
            continue
        words = shell_tokens.positional(args, GH_GLOBAL_VALUE_FLAGS)
        if words[:2] not in (["pr", "ready"], ["pr", "merge"]):
            continue
        if words[1] == "ready" and "--undo" in args:
            continue  # converting back to a draft publishes nothing
        raise block(PR_PUBLISH_MESSAGE.format(verb=words[1], effect=PR_PUBLISH_EFFECT[words[1]]))


def evaluate(command: str, cwd: str, environ: dict[str, str]) -> None:
    """Raise Blocked when `command`, run in `cwd`, breaks a guarded rule."""
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

    actions: list[dict] = []
    for action in parse_git_actions(tokens, cwd):
        if action.get("subcommand") in {"commit", "push", "add"}:
            actions.append(action)
        else:
            actions.extend(expand_configured_alias(action))

    added: list[str] = []
    for action in actions:
        subcommand = action.get("subcommand")
        if subcommand == "add":
            added.extend(paths_added(action))
        elif subcommand == "commit":
            check_commit(action, added)
        elif subcommand == "push":
            check_push(action)


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
        if MENTIONS_GIT.search(text) or OVERRIDE_MENTION.search(text):
            print(
                f"BLOCKED: the git guard hook failed ({type(error).__name__}: {error}). "
                "Stop and ask the user; do not work around the hook.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
