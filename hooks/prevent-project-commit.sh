#!/bin/bash
#
# prevent-project-commit.sh — provider-neutral PreToolUse hook
#
# Blocks unsafe git flags and git commit when local workflow state files are staged.
# Fail-open: exits 0 on any unexpected state (never blocks on errors).
#
# Exit codes:
#   0 — allow
#   2 — block (unsafe git flag/action or protected state file staged for commit)
#

set -euo pipefail

# Fail open on any error
trap 'exit 0' ERR

# Read JSON from stdin
INPUT=$(cat)

# Extract fields (fail open if jq unavailable or fields missing)
if ! command -v jq &>/dev/null; then
    exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null) || exit 0

if ! command -v python3 &>/dev/null; then
    exit 0
fi

export HOOK_COMMAND="$COMMAND"
export HOOK_CWD="$CWD"

# From here on, the Python guard owns fail-open vs block behavior. Keep exit 2
# intact for intentional blocks; any other Python failure should allow.
trap - ERR
set +e

python3 <<'PY'
import os
import re
import shlex
import subprocess
import sys

command = os.environ.get("HOOK_COMMAND", "")
cwd = os.environ.get("HOOK_CWD", "")


def allow():
    sys.exit(0)


def block(message):
    print(f"BLOCKED: {message}", file=sys.stderr)
    sys.exit(2)


try:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
except Exception:
    allow()

if not tokens or not cwd:
    allow()

def resolve_path(base, path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base, path))


def is_git_executable(token):
    return token == "git" or ("/" in token and os.path.basename(token) == "git")


def config_pair(raw):
    if "=" not in raw:
        return raw, ""
    key, value = raw.split("=", 1)
    return key, value


def configs_from_env(env):
    configs = []
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


def register_config(action, raw_config):
    action["configs"].append(raw_config)
    key, value = config_pair(raw_config)
    if key.lower().startswith("alias."):
        action["aliases"][key.split(".", 1)[1]] = "commit --no-verify" if value == "<config-env>" else value


def git_base(action):
    git_args = ["git"]
    workdir = action["workdir"]
    if action.get("git_dir"):
        git_args.append(f"--git-dir={action['git_dir']}")
    if action.get("work_tree"):
        git_args.append(f"--work-tree={action['work_tree']}")
    return git_args, workdir


def git_output(action, args):
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
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def shell_tokens(command_text):
    try:
        nested = shlex.shlex(command_text, posix=True, punctuation_chars=True)
        nested.whitespace_split = True
        return list(nested)
    except Exception:
        return []


def expand_shell_payload(command_text, positional):
    nested = shell_tokens(command_text)
    if not nested:
        return []
    expanded = []
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


def expand_positional_tokens(tokens, positional):
    expanded = []
    for token in tokens:
        if token in {"$@", "${@}"}:
            expanded.extend(positional)
        elif token in {"$*", "${*}"}:
            expanded.append(" ".join(positional))
        else:
            expanded.append(token)
    return expanded


def shell_var_name(token):
    if token.startswith("${") and token.endswith("}"):
        return token[2:-1]
    if token.startswith("$") and len(token) > 1:
        return token[1:]
    return None


def has_unsafe_git_substitution(command_text):
    substitution_pattern = r"`[^`]*`|\$\([^)]*\)|<\([^)]*\)"
    git_pattern = r"\bgit(?:\s+|\$\{[^}]+\})[^)]*(commit|push)\b"
    variable_git_pattern = r"[A-Za-z_][A-Za-z0-9_]*=git[^)]*\$[A-Za-z_][A-Za-z0-9_]*\s+(commit|push)\b"
    for match in re.finditer(substitution_pattern, command_text):
        body = match.group(0)
        if re.search(git_pattern, body) or re.search(variable_git_pattern, body):
            return True
    return False


if has_unsafe_git_substitution(command):
    block("git commit/push inside command substitution or process substitution bypasses safety checks")


def parse_git_actions(
    tokens,
    base_workdir=None,
    depth=0,
    inherited_env=None,
    inherited_vars=None,
    inherited_functions=None,
    inherited_aliases=None,
):
    actions = []
    if depth > 8:
        return actions
    current_workdir = base_workdir or cwd
    exported_env = dict(inherited_env or {})
    env_assignments = dict(exported_env)
    shell_vars = dict(inherited_vars or {})
    shell_functions = dict(inherited_functions or {})
    inherited_alias_map = dict(inherited_aliases or {})
    command_start = True
    separators = {";", "&&", "||", "|", "&", "(", ")"}
    shell_keywords = {"if", "then", "do", "else", "elif", "while", "until", "for", "select", "case", "!", "{"}
    assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
    count = len(tokens)
    i = 0

    while i < count:
        token = tokens[i]
        if token in separators:
            command_start = True
            env_assignments = dict(exported_env)
            i += 1
            continue
        if command_start and assignment.match(token):
            key, value = token.split("=", 1)
            shell_vars[key] = value
            env_assignments[key] = value
            i += 1
            continue
        if command_start and token == "export":
            segment_end = i + 1
            while segment_end < count and tokens[segment_end] not in separators:
                segment_end += 1
            j = i + 1
            while j < segment_end:
                export_token = tokens[j]
                if assignment.match(export_token):
                    key, value = export_token.split("=", 1)
                    shell_vars[key] = value
                    exported_env[key] = value
                elif export_token in shell_vars:
                    exported_env[export_token] = shell_vars[export_token]
                j += 1
            env_assignments = dict(exported_env)
            command_start = False
            i = segment_end
            continue
        if command_start and token in shell_keywords:
            i += 1
            continue
        if command_start and token in {"time", "noglob"}:
            i += 1
            continue
        if command_start and token == "cd":
            segment_end = i + 1
            while segment_end < count and tokens[segment_end] not in separators:
                segment_end += 1
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
            segment_end = i + 1
            while segment_end < count and tokens[segment_end] not in separators:
                segment_end += 1

            j = i + 1
            while j < segment_end:
                shell_arg = tokens[j]
                if shell_arg == "-c" or (shell_arg.startswith("-") and not shell_arg.startswith("--") and "c" in shell_arg[1:]):
                    command_index = j + 1
                    while command_index < segment_end and tokens[command_index] == "--":
                        command_index += 1
                    if command_index < segment_end:
                        positional = tokens[command_index + 1 : segment_end]
                        actions.extend(parse_git_actions(expand_shell_payload(tokens[command_index], positional), current_workdir, depth + 1, dict(exported_env), dict(shell_vars), dict(shell_functions), dict(inherited_alias_map)))
                    break
                j += 1

            command_start = False
            i = segment_end
            continue
        if command_start and token == "eval":
            segment_end = i + 1
            while segment_end < count and tokens[segment_end] not in separators:
                segment_end += 1
            eval_parts = tokens[i + 1 : segment_end]
            payload = eval_parts[0] if len(eval_parts) == 1 else " ".join(shlex.quote(part) for part in eval_parts)
            actions.extend(parse_git_actions(shell_tokens(payload), current_workdir, depth + 1, dict(exported_env), dict(shell_vars), dict(shell_functions), dict(inherited_alias_map)))
            command_start = False
            i = segment_end
            continue
        if command_start and token in {"sudo", "doas"}:
            i += 1
            while i < count and tokens[i] not in separators:
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
            while i < count and tokens[i].startswith("-") and tokens[i] not in separators:
                i += 1
            continue
        if command_start and token == "env":
            segment_end = i + 1
            while segment_end < count and tokens[segment_end] not in separators:
                segment_end += 1
            env_workdir = current_workdir
            child_env = dict(env_assignments)
            j = i + 1
            while j < segment_end:
                env_token = tokens[j]
                if assignment.match(env_token):
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
                actions.extend(parse_git_actions(tokens[j:segment_end], env_workdir, depth + 1, child_env, dict(shell_vars), dict(shell_functions), dict(inherited_alias_map)))
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
            action = {
                "subcommand": subcommand,
                "index": i,
                "args": args,
                "workdir": current_workdir,
                "git_dir": None,
                "work_tree": None,
                "configs": [],
                "aliases": dict(inherited_alias_map),
                "env": dict(env_assignments),
            }
            for raw_config in configs_from_env(env_assignments):
                register_config(action, raw_config)
            actions.append(action)
            command_start = False
            i += 1
            continue

        var_name = shell_var_name(token) if command_start else None
        variable_git = var_name and is_git_executable(shell_vars.get(var_name, ""))

        if command_start and token in shell_functions:
            segment_end = i + 1
            while segment_end < count and tokens[segment_end] not in separators:
                segment_end += 1
            positional = tokens[i + 1 : segment_end]
            function_tokens = expand_positional_tokens(shell_functions[token], positional)
            actions.extend(parse_git_actions(function_tokens, current_workdir, depth + 1, dict(exported_env), dict(shell_vars), dict(shell_functions), dict(inherited_alias_map)))
            command_start = False
            i = segment_end
            continue

        if not (command_start and (is_git_executable(token) or variable_git)):
            command_start = False
            i += 1
            continue

        action = {
            "subcommand": None,
            "index": None,
            "args": [],
            "workdir": current_workdir,
            "git_dir": None,
            "work_tree": None,
            "configs": [],
            "aliases": dict(inherited_alias_map),
            "env": dict(env_assignments),
        }
        for raw_config in configs_from_env(env_assignments):
            register_config(action, raw_config)
        j = i + 1
        while j < count:
            opt = tokens[j]
            if opt in separators:
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
                raw_config = tokens[j + 1]
                register_config(action, raw_config)
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
            if opt in {
                "--no-pager",
                "--bare",
                "--literal-pathspecs",
                "--glob-pathspecs",
                "--noglob-pathspecs",
                "--icase-pathspecs",
            }:
                j += 1
                continue
            if opt.startswith("-"):
                j += 1
                continue
            if opt in action["aliases"]:
                alias_tokens = shell_tokens(action["aliases"][opt])
                if alias_tokens:
                    shell_alias = False
                    if alias_tokens[0].startswith("!"):
                        alias_tokens[0] = alias_tokens[0][1:]
                        shell_alias = True
                    if alias_tokens and not shell_alias and not is_git_executable(alias_tokens[0]):
                        alias_tokens = ["git"] + alias_tokens
                    nested_actions = parse_git_actions(alias_tokens + tokens[j + 1 :], action["workdir"], depth + 1, dict(exported_env), dict(shell_vars), dict(shell_functions), dict(action.get("aliases", {})))
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


actions = parse_git_actions(tokens)


def expand_configured_alias(action):
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

    alias_tokens = shell_tokens(alias_value)
    if not alias_tokens:
        return []
    shell_alias = False
    if alias_tokens[0].startswith("!"):
        alias_tokens[0] = alias_tokens[0][1:]
        shell_alias = True
    if alias_tokens and not shell_alias and not is_git_executable(alias_tokens[0]):
        alias_tokens = ["git"] + alias_tokens

    nested = parse_git_actions(alias_tokens + action.get("args", []), action.get("workdir"), 1, action.get("env", {}), inherited_aliases=action.get("aliases", {}))
    for nested_action in nested:
        nested_action["configs"] = action.get("configs", []) + nested_action.get("configs", [])
        nested_action["env"] = dict(action.get("env", {}), **nested_action.get("env", {}))
    return nested


expanded_actions = []
for action in actions:
    if action.get("subcommand") in {"commit", "push"}:
        expanded_actions.append(action)
    else:
        expanded_actions.extend(expand_configured_alias(action))
actions = expanded_actions


def short_commit_option_has_no_verify(arg):
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


def config_value_false(value):
    return value.strip().lower() in {"false", "no", "off", "0"}


def long_option_prefix(arg, option, min_prefix):
    name = arg.split("=", 1)[0]
    return name.startswith("--") and len(name) >= len(min_prefix) and option.startswith(name)


for action in actions:
    subcommand = action.get("subcommand")
    if subcommand not in {"commit", "push"}:
        continue

    args = action.get("args", [])
    configs = action.get("configs", [])
    for stop, token in enumerate(args):
        if token in {";", "&&", "||", "|", "&", "(", ")"}:
            args = args[:stop]
            break

    if subcommand == "commit":
        for raw_config in configs:
            key, value = config_pair(raw_config)
            key = key.lower()
            if key == "core.hookspath":
                block("git commit with core.hooksPath override bypasses pre-commit hooks")
            if key == "commit.gpgsign" and (value == "<config-env>" or config_value_false(value)):
                block("git commit with commit.gpgsign=false violates signing rules")

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--":
                break
            if long_option_prefix(arg, "--no-verify", "--no-veri"):
                block("git commit --no-verify violates global pre-commit rules")
            if long_option_prefix(arg, "--no-gpg-sign", "--no-g"):
                block("git commit --no-gpg-sign violates global signing rules")
            if short_commit_option_has_no_verify(arg):
                block("git commit -n bypasses pre-commit hooks")
            if arg in {"-m", "-F", "-C", "-c", "--message", "--file", "--reuse-message", "--reedit-message"}:
                i += 2
                continue
            i += 1

        staged = git_output(action, ["diff", "--cached", "--name-only"])
        if staged is None:
            continue
        protected_names = {
            "PROJECT.md",
            "PROJECT_ARCHIVE.md",
            "PLAN.md",
            "WATCH.md",
            "CHERRY_PICK.md",
            "CI_FIX.md",
        }
        protected = [
            line
            for line in staged.splitlines()
            if line.rsplit("/", 1)[-1] in protected_names
        ]
        if protected:
            print(
                "Local workflow state file(s) are staged for commit. These files contain session or batch state and should not be checked in.\n",
                file=sys.stderr,
            )
            for path in protected:
                print(f"  - {path}", file=sys.stderr)
            print("\nUnstage with: git reset HEAD <file>", file=sys.stderr)
            sys.exit(2)

    if subcommand == "push":
        for raw_config in configs:
            key, _value = config_pair(raw_config)
            if key.lower() == "core.hookspath":
                block("git push with core.hooksPath override bypasses pre-push hooks")

        current_branch = (git_output(action, ["branch", "--show-current"]) or "").strip()
        push_force = False
        dest_main = False
        ref_wide = False
        has_explicit_ref = False
        operands = []
        delete_push = False

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--":
                operands.extend(args[i + 1 :])
                break
            if long_option_prefix(arg, "--no-verify", "--no-veri"):
                block("git push --no-verify bypasses pre-push hooks")
            if "=" in arg and (long_option_prefix(arg, "--force-with-lease", "--force-w") or long_option_prefix(arg, "--force-with-includes", "--force-w")):
                push_force = True
                lease_ref = arg.split("=", 1)[1].split(":", 1)[0]
                if re.fullmatch(r"(refs/heads/)?(main|master)", lease_ref):
                    dest_main = True
                    has_explicit_ref = True
            if arg in {"--force", "--force-with-lease", "-f"} or long_option_prefix(arg, "--force", "--forc") or long_option_prefix(arg, "--force-with-lease", "--force-w") or long_option_prefix(arg, "--force-with-includes", "--force-w"):
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

        for i, operand in enumerate(operands):
            force_refspec = operand.startswith("+")
            refspec = operand[1:] if force_refspec else operand
            if force_refspec:
                push_force = True
            if refspec == ":":
                ref_wide = True
            if len(operands) >= 2 and i == 0:
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
            push_target = (git_output(action, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}"]) or "").strip()
            if re.fullmatch(r"([^/]+/)?(main|master)", push_target or ""):
                dest_main = True
        if push_force and (ref_wide or dest_main or (not has_explicit_ref and current_branch in {"main", "master"})):
            block("force-pushing main/master is not allowed")
        if delete_push and dest_main:
            block("deleting main/master is not allowed")

allow()
PY
status=$?

if [[ "$status" -eq 2 ]]; then
    exit 2
fi

exit 0
