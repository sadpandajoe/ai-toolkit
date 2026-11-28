"""The git guard's reading of git's own words: `parse_git_actions`, configured aliases, and the
scan of substitution bodies for a git commit or push (`has_unsafe_git_substitution`)."""

from __future__ import annotations

import bisect
import functools
import os
import re
import shlex
import subprocess
from typing import Iterator

import shell_tokens
from guard_base import SEPARATORS, block, config_pair, git_output, is_git_executable
from gh_text import quoted_split


SHELL_KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "for", "select", "case", "!", "{"}
# Wrappers that run the rest of the line as a command, after their own options.
RUNNING_WRAPPERS = {"timeout", "nohup", "xargs", "nice", "ionice", "stdbuf", "exec"}
LATER_GIT_LIMIT = 16  # later words of one command read as the command it may run
GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env", "--attr-source"}
STARTS_COMMANDS = {"env", "sudo", "doas", "eval", "command", "builtin", "nohup", "timeout", "nice", "xargs", "exec"}
GIT_COMMANDS = shell_tokens.GIT_ENTRY_POINTS | {"stage", "send-pack"}


def subcommand_readings(word: str, shell_vars: dict) -> list[str]:
    """The git subcommands a word may be: itself, a variable set in the same command (`P=push; git
    $P`), what an expansion may come out as (`${S:-push}`), or, for an expansion the guard cannot
    read, both `push` and `commit`, so either check runs."""
    name = shell_var_name(word)
    if name is not None and name in shell_vars:
        return [shell_vars[name]]
    if "$" not in word and "`" not in word:
        return [word]
    known = sorted(shell_tokens.may_be(word, {"push", "commit", "add", "stage", "send-pack"}))
    return known or ["push", "commit"]


def may_run_git(tokens: list[str], j: int, end: int) -> bool:
    """Whether the word at token `j`, behind a command the guard does not know, may start a
    command that runs git: git followed by a git command (`setsid git push`; `pytest -k git
    tests` names none), a dashed entry point (`git-push`), a shell with a `-c` text, or a
    command that runs the rest of its words (`env`, `sudo`, `eval`), with git among them."""
    word = tokens[j]
    name = shell_tokens.head_name(word)
    if is_git_executable(word) or (("$" in word or "`" in word) and "git" in shell_tokens.may_be(word, {"git"})):
        k = j + 1
        while k < end and tokens[k].startswith("-"):
            k += 2 if tokens[k] in GIT_GLOBAL_VALUE else 1
        return k < end and (tokens[k] in GIT_COMMANDS or any(t.startswith("alias.") for t in tokens[j + 1 : k]))
    if name.startswith("git-") and name[4:] in GIT_COMMANDS:
        return True
    rest = tokens[j + 1 : end]
    if name in shell_tokens.SHELLS or shell_tokens.SHELL_NAME.fullmatch(name):
        return any(shell_tokens.is_shell_command_flag(t) for t in rest) and any(shell_tokens.WORD_GIT.search(t) for t in rest)
    if name in STARTS_COMMANDS:
        return any(is_git_executable(t) or shell_tokens.WORD_GIT.search(t) for t in rest)
    return False
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def resolve_path(base: str, path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base, path))


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


def shell_tokens_or_empty(command_text: str) -> list[str]:
    try:
        return shell_tokens.tokenize(command_text)
    except ValueError:
        return []


def expand_shell_payload(command_text: str, positional: list[str]) -> list[str]:
    nested = shell_tokens_or_empty(command_text)
    if not nested:
        return []
    expanded = shell_tokens.Tokens()
    expanded.quoted_operators = getattr(nested, "quoted_operators", False)
    positional_zero = positional[0] if positional else ""
    positional_args = positional[1:] if positional else []
    for token in nested:
        if token in {"$@", "${@}", "\\$@", "\\${@}"}:
            if positional_args:
                expanded.extend(positional_args)
            else:
                expanded.append(token)
        elif token in {"$*", "${*}", "\\$*", "\\${*}"}:
            # unquoted, `$*` splits into words as `$@` does; the quotes are gone by here
            if positional_args:
                expanded.extend(positional_args)
            else:
                expanded.append(token)
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


def git_words(tokens: list[str], start: int, untrusted: bool) -> tuple[list[str], list[int], int, bool]:
    """The words of the git command at `start`: its substitutions are one word each and its
    redirections are gone, so globals, subcommand and arguments are read from git's own words."""
    return shell_tokens.command_words(tokens, start, merge=not untrusted)


def git_readings(tokens: list[str], start: int, untrusted: bool) -> list[tuple[list[str], list[int]]]:
    """Every way the shell may hand git its words (`git_words`): also as they stand when a quoted
    operator is about (`git push -o '>' --force origin main`: the `>` is a word, not a
    redirection), and without the words that may expand to nothing (`git $X push --force`).
    A wrong guess can only block more, so every reading is checked."""
    words, positions, _end, _cut = git_words(tokens, start, untrusted)
    readings = [(words, positions)]
    if untrusted:
        raw, raw_positions, _end, _cut = shell_tokens.command_words(tokens, start, merge=False, keep_redirections=True)
        if raw != words:
            readings.append((raw, raw_positions))
    for reading_words, reading_positions in list(readings):
        kept = vanish_kept(reading_words)
        if len(kept) != len(reading_words):
            readings.append(([reading_words[k] for k in kept], [reading_positions[k] for k in kept]))
    return readings


def vanish_kept(words: list[str]) -> list[int]:
    """The indexes of git's words with those that may expand to nothing dropped where the
    subcommand would stand (`git $X push`): an option's value (`-C $(...)`) and the words after
    the subcommand stay, since dropping them reads a different command, not the one bash runs."""
    kept = [0]
    index = 1
    while index < len(words):
        word = words[index]
        if word in GIT_GLOBAL_VALUE:
            kept += [index, index + 1][: len(words) - index]
            index += 2
        elif word.startswith("-"):
            kept.append(index)
            index += 1
        elif shell_tokens.may_vanish(word):
            index += 1
        else:
            kept += list(range(index, len(words)))
            break
    return kept


SAME = object()  # `shell_workdir`: the shell is where this token list starts


def new_action(
    workdir: str | None, aliases: dict, env: dict, untrusted: bool = False, shell_dir: str | None = None
) -> dict:
    action = {
        "untrusted": untrusted,
        "shell_dir": shell_dir,  # where the shell expands `$(...)` words, whatever `-C` says
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


def set_git_path(action: dict, key: str, value: str) -> None:
    """Record a `--git-dir`/`--work-tree` value; one the shell expands makes the directory unknown."""
    if shell_tokens.UNKNOWN_CD_TARGET.search(value) or value.startswith("~") or action["workdir"] is None:
        action[key] = None
        action["workdir"] = None
    else:
        action[key] = resolve_path(action["workdir"], value)


def parse_git_actions(
    tokens: list[str],
    base_workdir: str | None,
    depth: int = 0,
    inherited_env: dict | None = None,
    inherited_vars: dict | None = None,
    inherited_functions: dict | None = None,
    inherited_aliases: dict | None = None,
    parens_untrusted: bool = False,
    shell_workdir: object = SAME,
    _pieces: bool = False,
    _aliases_open: tuple[str, ...] = (),
) -> list[dict]:
    """Every git invocation in `tokens`, in order, with its effective context.

    The directory of each command is `shell_tokens.DirectoryModel`'s; None is unknown. With a
    quoted operator about, each piece the shell really separates is also read with the
    separators the lexer made of quoted words kept as words (`git commit -m ';' --no-verify`).
    Past the nesting limit, git in the text is one unreadable action, which blocks.
    """
    actions: list[dict] = []
    if depth > 8:
        if shell_tokens.WORD_GIT.search(" ".join(tokens)):
            return [{**new_action(None, {}, {}, True), "subcommand": "push", "unreadable": True}]
        return actions
    tokens = shell_tokens.join_toplevel(tokens)  # `cd $(git rev-parse --show-toplevel)` is one word
    model = shell_tokens.DirectoryModel(tokens, base_workdir, parens_untrusted)
    parens_untrusted = model.untrusted
    current_workdir = base_workdir
    exported_env = dict(inherited_env or {})
    env_assignments = dict(exported_env)
    shell_vars = dict(inherited_vars or {})
    shell_functions = dict(inherited_functions or {})
    inherited_alias_map = dict(inherited_aliases or {})
    command_start = True
    wrapped = False  # the command word was reached through a wrapper (`exec`, `sudo`, `nohup`, ...)
    count = len(tokens)
    i = 0

    def shell_dir() -> str | None:
        return current_workdir if shell_workdir is SAME else shell_workdir  # type: ignore[return-value]

    def recurse(sub_tokens: list[str], workdir: str | None, env: dict, shell: object = SAME) -> list[dict]:
        return parse_git_actions(
            sub_tokens,
            workdir,
            depth + 1,
            env,
            dict(shell_vars),
            dict(shell_functions),
            dict(inherited_alias_map),
            parens_untrusted,
            shell_workdir if shell is SAME else shell,
        )

    def later_git(start: int) -> list[dict]:
        """The git actions of every later word of the command at token `start` that may start
        what it runs (`may_run_git`), each read as the command from there to the end of the
        command. Past `LATER_GIT_LIMIT` of them, the command is one unreadable action, which
        blocks."""
        end = segment_end_index(tokens, start + 1)
        starts = [j for j in range(start + 1, end) if may_run_git(tokens, j, end)]
        if len(starts) > LATER_GIT_LIMIT:
            return [{**new_action(None, {}, {}, True), "subcommand": "push", "unreadable": True}]
        found: list[dict] = []
        for j in starts:
            found.extend(recurse(tokens[j:end], current_workdir, dict(env_assignments)))
        return found

    def span_tail(start: int) -> list[dict]:
        """The git actions of the words after the backtick span that opens at token `start`."""
        closing = next((j for j in range(start + 1, count) if tokens[j].count("`") % 2), None)
        if closing is None or not tokens[closing].endswith("`") or closing + 1 >= count:
            return []
        tail_end = segment_end_index(tokens, closing + 1)
        if tail_end <= closing + 1:
            return []
        return recurse(tokens[closing + 1 : tail_end], current_workdir, dict(env_assignments))

    while i < count:
        token = tokens[i]
        current_workdir = model.at(i)
        if token in SEPARATORS:
            command_start = True
            wrapped = False
            env_assignments = dict(exported_env)
            i += 1
            continue
        if command_start and ASSIGNMENT.match(token):
            key, value = token.split("=", 1)
            shell_vars[key] = value
            env_assignments[key] = value
            if value.count("`") % 2:
                # `` a=`b c` git push``: the value's backtick span runs on past this word; the
                # words after it are the command, read as one of their own as well
                actions.extend(span_tail(i))
            i += 1
            continue
        if command_start and token in shell_tokens.REDIRECTIONS:
            # `>/dev/null git push ...`: a redirection ahead of the command is not the command
            # (when a quoted operator may be this word, keep a git head that follows)
            keep = parens_untrusted and i + 1 < count and is_git_executable(tokens[i + 1])
            i += 1 if keep else 2
            continue
        if (
            command_start
            and i + 1 < count
            and tokens[i + 1] in shell_tokens.REDIRECTIONS
            and shell_tokens.REDIRECTION_FD.fullmatch(token)
        ):
            i += 1  # `2>&1 git push`: the fd; the operator follows
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
            wrapped = True
            continue
        if command_start and os.path.basename(token) in RUNNING_WRAPPERS:
            wrapped = True
            # `timeout 60 git ...`, `nohup git ...`, `xargs git ...`, `nice -n 5 git ...`:
            # skip the wrapper and its own options; the rest is the command.
            segment_end = segment_end_index(tokens, i + 1)
            rest = shell_tokens.skip_options(
                os.path.basename(token), tokens[i + 1 : segment_end], shell_tokens.Effects()
            )
            i = segment_end - len(rest)
            continue
        if command_start and token in {"cd", "pushd", "popd"}:  # the directory model follows it
            segment_end = segment_end_index(tokens, i + 1)
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
        if command_start and (
            shell_tokens.head_name(token) in shell_tokens.SHELLS
            or shell_tokens.SHELL_NAME.fullmatch(shell_tokens.head_name(token))
        ):  # `bash`, `/bin/sh`, `dash`
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
                                None,  # the outer shell may have expanded a `$(...)` in the payload
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
            actions.extend(recurse(shell_tokens_or_empty(payload), current_workdir, dict(exported_env), None))
            command_start = False
            i = segment_end
            continue
        if command_start and shell_tokens.head_name(token) in {"sudo", "doas"}:
            wrapped = True
            i += 1
            while i < count and tokens[i] not in SEPARATORS:
                wrapper_token = tokens[i]
                if wrapper_token in {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "--prompt", "--user", "--group", "--host", "--chdir", "--role", "--type", "--other-user", "--close-from", "--command-timeout"}:
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
            wrapped = True
            i += 1
            while i < count and tokens[i].startswith("-") and tokens[i] not in SEPARATORS:
                i += 1
            continue
        if command_start and shell_tokens.head_name(token) == "env":
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
                if env_token in {"-u", "--unset", "-C", "--chdir", "-P", "-a", "--argv0"}:  # (`-P`, `-a`: a value)
                    if env_token in {"-C", "--chdir"} and j + 1 < segment_end:
                        env_workdir = shell_tokens.hop_dir(env_workdir, tokens[j + 1], model.variables_at(i))
                    elif j + 1 < segment_end:
                        child_env.pop(tokens[j + 1], None)
                    j += 2
                    continue
                if env_token.startswith("--chdir="):
                    env_workdir = shell_tokens.hop_dir(env_workdir, env_token.split("=", 1)[1], model.variables_at(i))
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
                actions.extend(recurse(tokens[j:segment_end], env_workdir, child_env, shell_dir()))
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
            action = new_action(current_workdir, inherited_alias_map, env_assignments, parens_untrusted, shell_dir())
            action["subcommand"] = dashed[1]
            action["index"] = i
            action["args"] = git_words(tokens, i, parens_untrusted)[0][1:]
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
            args = git_words(tokens, i, parens_untrusted)[0][1:]
            if subcommand is None and args:
                subcommand = args[0]
                args = args[1:]
            action = new_action(current_workdir, inherited_alias_map, env_assignments, parens_untrusted, shell_dir())
            action["subcommand"] = subcommand
            action["index"] = i
            action["args"] = args
            actions.append(action)
            command_start = False
            i += 1
            continue

        var_name = shell_var_name(token) if command_start else None
        variable_git = var_name and is_git_executable(shell_vars.get(var_name, ""))
        # `${X}git push`, `${GIT:-git} push`: a word that may come out as git is read as git
        variable_git = variable_git or (command_start and "git" in shell_tokens.may_be(token, {"git"}))

        if command_start and var_name and shell_vars.get(var_name) in shell_functions:
            token = shell_vars[var_name]  # `F=f; $F`: the variable names a function
        if command_start and token == "trap" and i + 1 < count and tokens[i + 1] not in SEPARATORS:
            # `trap f EXIT`, `trap 'git push --force' EXIT`: the first word is a command run later
            actions.extend(recurse(shell_tokens_or_empty(tokens[i + 1]), current_workdir, dict(exported_env)))
        if "`" in token and not command_start:
            # `: `f``: a backtick span among the words runs its body, functions included
            for body in shell_tokens.BACKTICK.findall(token):
                actions.extend(recurse(shell_tokens_or_empty(body), current_workdir, dict(exported_env)))
        if command_start and token in shell_functions:
            segment_end = segment_end_index(tokens, i + 1)
            positional = tokens[i + 1 : segment_end]
            function_tokens = expand_positional_tokens(shell_functions[token], positional)
            actions.extend(recurse(function_tokens, current_workdir, dict(exported_env)))
            command_start = False
            i = segment_end
            continue

        if not (command_start and (is_git_executable(token) or variable_git)):
            if command_start and shell_tokens.may_vanish(token) and i + 1 < count and tokens[i + 1] not in SEPARATORS:
                # `$X git push`, `` `true` git push``: a word that expands to nothing leaves the
                # next one the command. Read so, which only adds: as a command of its own the
                # word runs no git the guard could read
                i += 1
                continue
            if command_start and token.startswith("`") and token.count("`") % 2:
                # `` `echo x` git push``: the span is walked as it was, and the words after it
                # are read as a command of their own as well
                actions.extend(span_tail(i))
            if command_start and (wrapped or shell_tokens.head_name(token) not in shell_tokens.INERT_HEADS):
                # (after a wrapper the word may be an option's value: `exec -a echo git push`)
                # `setsid git push`, `caffeinate git push`, `flock /tmp/x git push`: behind a
                # command the guard does not know, a later `git` word may be the command it runs.
                # Each is read as one too; a printing command (`echo git push`) runs none
                actions.extend(later_git(i))
            command_start = False
            i += 1
            continue

        for words, positions in git_readings(tokens, i, parens_untrusted):
            action = new_action(current_workdir, inherited_alias_map, env_assignments, parens_untrusted, shell_dir())
            count_words = len(words)
            j = 1
            while j < count_words:
                opt = words[j]
                if opt == "-C":
                    if j + 1 >= count_words:
                        break
                    action["workdir"] = shell_tokens.hop_dir(action["workdir"], words[j + 1], model.variables_at(i))
                    j += 2
                    continue
                if opt == "--git-dir" or opt.startswith("--git-dir="):
                    if opt == "--git-dir" and j + 1 >= count_words:
                        break
                    value = words[j + 1] if opt == "--git-dir" else opt.split("=", 1)[1]
                    set_git_path(action, "git_dir", value)
                    j += 2 if opt == "--git-dir" else 1
                    continue
                if opt == "--work-tree" or opt.startswith("--work-tree="):
                    if opt == "--work-tree" and j + 1 >= count_words:
                        break
                    value = words[j + 1] if opt == "--work-tree" else opt.split("=", 1)[1]
                    set_git_path(action, "work_tree", value)
                    action["workdir"] = action["work_tree"]
                    j += 2 if opt == "--work-tree" else 1
                    continue
                if opt == "-c":
                    if j + 1 >= count_words:
                        break
                    register_config(action, words[j + 1])
                    j += 2
                    continue
                if opt == "--config-env":
                    if j + 1 >= count_words:
                        break
                    key, env_name = config_pair(words[j + 1])
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
                        if not shell_alias and opt in _aliases_open:
                            break  # `alias.x=y`, `alias.y=x`: git reports the loop and runs nothing
                        nested_actions = parse_git_actions(
                            alias_tokens + words[j + 1 :],
                            action["workdir"],
                            depth + 1,
                            dict(exported_env),
                            dict(shell_vars),
                            dict(shell_functions),
                            dict(action.get("aliases", {})),
                            parens_untrusted,
                            action["shell_dir"],
                            # a shell alias starts a new git, which expands afresh
                            _aliases_open=() if shell_alias else _aliases_open + (opt,),
                        )
                        for nested_action in nested_actions:
                            nested_action["configs"] = action["configs"] + nested_action.get("configs", [])
                            nested_action["env"] = dict(action.get("env", {}), **nested_action.get("env", {}))
                        actions.extend(nested_actions)
                    break

                action["index"] = positions[j]
                action["args"] = words[j + 1 :]
                for subcommand in subcommand_readings(opt, shell_vars):
                    actions.append({**action, "subcommand": subcommand})
                break

        command_start = False
        i += 1

    source = getattr(tokens, "cleaned", "")
    if parens_untrusted and source and not _pieces:
        # a quoted `;`, `|`, `&` or parenthesis came out bare and cut git's words: read each
        # real piece once more with those as words. Its directory is the start's when nothing
        # moves it, else unknown
        workdir = base_workdir if len(set(model.dirs)) == 1 else None
        for piece in quoted_split(source):
            if not shell_tokens.WORD_GIT.search(piece):
                continue
            try:
                piece_tokens = shell_tokens.tokenize(piece)
            except ValueError:
                continue
            neutral = [PIECE_WORD if token in SEPARATORS else token for token in piece_tokens]
            actions.extend(
                parse_git_actions(
                    neutral, workdir, depth + 1, dict(exported_env), dict(shell_vars), dict(shell_functions),
                    dict(inherited_alias_map), True, shell_workdir, _pieces=True,
                )
            )
    return actions


PIECE_WORD = "\ue000"  # a separator the lexer made of a quoted word, read back as a word


@functools.lru_cache(maxsize=1)
def git_command_names() -> frozenset[str] | None:
    """The names `git help` knows, read outside any repository (so no alias is in it); None if unreadable."""
    try:
        result = subprocess.run(
            ["git", "--list-cmds=builtins,main,others"],
            cwd="/",
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    names = frozenset(result.stdout.split())
    return names if result.returncode == 0 and names else None


def expand_configured_alias(action: dict) -> list[dict]:
    subcommand = action.get("subcommand")
    if not subcommand:
        return []
    alias_value = action.get("aliases", {}).get(subcommand)
    if alias_value is None and action.get("workdir") is None:
        names = git_command_names()
        if names is None or subcommand not in names:
            raise block(
                f"the guard cannot read the repository this command runs in, so it cannot tell "
                f"whether `git {subcommand}` is an alias for a push or a commit. Run it from "
                "the repository, or spell out the git command."
            )
        return []
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
        parens_untrusted=action.get("untrusted", False),
        shell_workdir=action.get("shell_dir"),
    )
    for nested_action in nested:
        nested_action["configs"] = action.get("configs", []) + nested_action.get("configs", [])
        nested_action["env"] = dict(action.get("env", {}), **nested_action.get("env", {}))
    return nested


GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env", "--attr-source"}
