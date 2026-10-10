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
- `gh pr ready` and `gh pr merge`, unless the user set `AITK_PR_READY=1` (a
  command prefix or the session env, set only when the user asked in words).
  `SKIP_PR_GATE=1` does not lift them.

Every command the shell would run is checked: newline- and `;`-separated
commands, and-lists and or-lists, subshells, `sh -c` and `eval` payloads,
command substitutions, shell functions, and commands behind `env`, `sudo`,
`command`, `timeout`, `nohup`, `xargs`, `nice`, `ionice`, `stdbuf` or `time`.
A command that mentions git or gh and cannot be parsed blocks, and so does an
internal error; the wrapper fails closed when python3 is missing.

Known limits (a tripwire, not a shell sandbox): a git alias defined in a file
the hook cannot read, `gh api` calls, and programs that run git themselves are
not seen.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

from aitk.hooks import shell_tokens
from aitk.project_state import STATE_FILES


SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&"}
SHELL_KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "for", "select", "case", "!", "{"}
# Wrappers that run the rest of the line as a command, after their own options.
RUNNING_WRAPPERS = {"timeout", "nohup", "xargs", "nice", "ionice", "stdbuf", "exec"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
MENTIONS_GIT = re.compile(r"\bgit\b|\bgh\b")
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
    return token == "git" or ("/" in token and os.path.basename(token) == "git")


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


def has_unsafe_git_substitution(command_text: str) -> bool:
    substitution_pattern = r"`[^`]*`|\$\([^)]*\)|<\([^)]*\)"
    git_pattern = r"\bgit(?:\s+|\$\{[^}]+\})[^)]*(commit|push)\b"
    variable_git_pattern = r"[A-Za-z_][A-Za-z0-9_]*=git[^)]*\$[A-Za-z_][A-Za-z0-9_]*\s+(commit|push)\b"
    for match in re.finditer(substitution_pattern, command_text):
        body = match.group(0)
        if re.search(git_pattern, body) or re.search(variable_git_pattern, body):
            return True
    return False


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
        dynamic_git = None
        if command_start:
            dynamic_git = re.fullmatch(r"git(?:\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*)(?:(commit|push))?", token)

        if command_start and dynamic_git:
            subcommand = dynamic_git.group(1)
            args = tokens[i + 1 :]
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
            if opt in {"--namespace", "--exec-path"}:
                j += 2
                continue
            if opt.startswith("--namespace=") or opt.startswith("--exec-path="):
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
                        alias_tokens + tokens[j + 1 :],
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
            action["args"] = tokens[j + 1 :]
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
PR_PUBLISH_EFFECT = {
    "ready": "takes a draft pull request out of draft",
    "merge": "merges a pull request",
}
UNRESOLVED_PR_PUBLISH = re.compile(r"\bgh\b.*\bpr\b.*\b(ready|merge)\b", re.S)


def check_pr_publish(command: str, cwd: str, environ: dict[str, str]) -> None:
    """`gh pr ready` and `gh pr merge` need the user's AITK_PR_READY=1 (N4)."""
    if shell_tokens.truthy(environ.get("AITK_PR_READY")):
        return
    for found in shell_tokens.commands(command, cwd):
        if found.unresolved:
            match = UNRESOLVED_PR_PUBLISH.search(found.text)
            if match and not shell_tokens.truthy(found.assignments.get("AITK_PR_READY")):
                raise block(PR_PUBLISH_MESSAGE.format(verb=match.group(1), effect=PR_PUBLISH_EFFECT[match.group(1)]))
            continue
        if found.name != "gh":
            continue
        args = found.argv[1:]
        if {"-h", "--help"} & set(args):
            continue
        words = shell_tokens.positional(args, GH_GLOBAL_VALUE_FLAGS)
        if words[:2] not in (["pr", "ready"], ["pr", "merge"]):
            continue
        if words[1] == "ready" and "--undo" in args:
            continue  # converting back to a draft publishes nothing
        if shell_tokens.truthy(found.assignments.get("AITK_PR_READY")):
            continue
        raise block(PR_PUBLISH_MESSAGE.format(verb=words[1], effect=PR_PUBLISH_EFFECT[words[1]]))


def evaluate(command: str, cwd: str, environ: dict[str, str]) -> None:
    """Raise Blocked when `command`, run in `cwd`, breaks a guarded rule."""
    if not command or not cwd:
        return
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
        evaluate(command, cwd, dict(os.environ))
    except Blocked as blocked:
        print(str(blocked), file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - an internal error blocks git and gh
        if MENTIONS_GIT.search(command if isinstance(command, str) else raw):
            print(
                f"BLOCKED: the git guard hook failed ({type(error).__name__}: {error}). "
                "Stop and ask the user; do not work around the hook.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
