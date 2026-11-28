"""The git guard's commit and push rules: `check_commit`, `check_push`, the push options read
as git's parse-options does (`PUSH_OPTIONS`), and the protected paths (`STATE_FILES`)."""

from __future__ import annotations

import re

import shell_tokens
from shell_dirs import UNKNOWN_PATH
from shell_lex import residues
from guard_base import Blocked, SEPARATORS, block, config_pair, git_output


# Local workflow state that never belongs in a commit, matched by basename.
STATE_FILES = (
    "PROJECT.md",
    "PROJECT_ARCHIVE.md",
    "PLAN.md",
    "WATCH.md",
    "CHERRY_PICK.md",
    "CI_FIX.md",
)


PROTECTED_DIRECTORY = ".ai-toolkit"


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


UNKNOWN_ADDED = "\ue001"  # a staged path an expansion names (`git add -f $F`)


def paths_added(action: dict) -> list[str]:
    """What `git add <args>` (or `git stage`) would stage, as repository paths where git can
    tell. A brace word is every path it makes; a path an expansion names is `UNKNOWN_ADDED`."""
    args = [alternative for arg in own_args(action.get("args", [])) for alternative in brace_words(arg)]
    if any(UNKNOWN_PATH.search(arg) and not arg.startswith("-") for arg in args):
        return [UNKNOWN_ADDED]
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


def update_index_paths(action: dict) -> list[str]:
    """The paths `git update-index --add` (or `--cacheinfo`) puts in the index."""
    args = own_args(action.get("args", []))
    found: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--cacheinfo" and index + 1 < len(args):
            found.append(args[index + 1].rsplit(",", 1)[-1])
            index += 2
            continue
        if arg.startswith("--cacheinfo="):
            found.append(arg.rsplit(",", 1)[-1])
        elif not arg.startswith("-"):
            found.append(arg)
        index += 1
    if any(UNKNOWN_PATH.search(path) for path in found):
        return [UNKNOWN_ADDED]
    return found


GIT_UNREADABLE = (
    "git in this command is nested too deep for the guard to read (sh -c, eval, functions "
    "or substitution spans more than 8 levels in), so it cannot tell what it pushes or commits. "
    "Run git as a plain command."
)


def check_commit(action: dict, added_before: list[str]) -> None:
    if action.get("unreadable"):
        raise block(GIT_UNREADABLE)
    config_source = unread_config_source(action)
    if config_source:
        raise block(CONFIG_SOURCE.format(source=config_source, what="commit"))
    if UNKNOWN_ADDED in added_before:
        raise block(
            "the guard cannot tell what this commit includes: the same command stages a path an "
            "expansion names, and local workflow state files must stay out of commits. Stage "
            "named paths, or run `git commit` as a command of its own."
        )
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
    if staged is None:
        raise block(
            "the guard cannot read what this commit includes (the repository or its staged "
            "files could not be read), and local workflow state files must stay out of "
            "commits. Run `git commit` from the repository."
        )
    candidates = staged.splitlines() + added_before
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


PUSH_BRANCH_UNREADABLE = (
    "the guard cannot tell which branch this push updates (the repository or its current "
    "branch could not be read), and force-pushing or deleting main/master is not allowed. "
    "Run it from the repository with an explicit branch (`git push --force origin <branch>`)."
)


EXPANSION = re.compile(r"[$`]")
MAIN_REF = re.compile(r"(?:refs/)?(?:heads/)?(?:main|master)")


# `git push -h` of git 2.39: each long option and how it takes its value ("flag": none,
# "value": the next word or `=`, "optional": only through `=`). A newer git may add options.
PUSH_OPTIONS = {
    "verbose": "flag", "quiet": "flag", "repo": "value", "all": "flag", "mirror": "flag",
    "delete": "flag", "tags": "flag", "dry-run": "flag", "porcelain": "flag", "force": "flag",
    "force-with-lease": "optional", "force-if-includes": "flag", "recurse-submodules": "value",
    "thin": "flag", "receive-pack": "value", "exec": "value", "set-upstream": "flag",
    "progress": "flag", "prune": "flag", "verify": "flag", "follow-tags": "flag",
    "signed": "optional", "atomic": "flag", "push-option": "value", "ipv4": "flag", "ipv6": "flag",
}
PUSH_SHORT = {
    "v": "verbose", "q": "quiet", "d": "delete", "n": "dry-run", "f": "force", "u": "set-upstream",
    "o": "push-option", "4": "ipv4", "6": "ipv6",
}


def resolve_push_option(name: str) -> tuple[str, bool] | None:
    """(option, negated) for a long option as git's parse-options reads it: an exact name (or
    `no-` and a name), else the one option the text is a prefix of. An ambiguous or unknown
    text is None: git exits with an error there and pushes nothing."""
    if name in PUSH_OPTIONS:
        return name, False
    if name.startswith("no-") and name[3:] in PUSH_OPTIONS:
        return name[3:], True
    found = {(option, False) for option in PUSH_OPTIONS if option.startswith(name)}
    if name.startswith("no-"):
        found |= {(option, True) for option in PUSH_OPTIONS if option.startswith(name[3:])}
    elif "no-".startswith(name):
        found |= {(option, True) for option in PUSH_OPTIONS}
    return found.pop() if len(found) == 1 else None


def read_push_options(args: list[str]):
    """(force, delete, ref-wide, lease names main, operands) of `git push`'s words, or None
    for `--no-verify`. Options read as parse-options does (see PUSH_OPTIONS); an option may
    follow an operand; the first operand is the repository, the rest are refspecs."""
    force = delete = wide = lease_main = False
    operands: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--":
            operands.extend(args[i:])
            break
        if long_option_prefix(arg, "--no-verify", "--no-veri"):
            return None
        if arg.startswith("--"):
            name, equals, value = arg[2:].partition("=")
            found = resolve_push_option(name)
            if found is None:
                continue
            option, negated = found
            if negated:
                if option == "verify":
                    return None
                continue  # a negation takes no value and never loosens what was read
            kind = PUSH_OPTIONS[option]
            if kind == "value" and not equals:
                i += 1
            if option in {"force", "force-with-lease"}:
                force = True
                if equals and MAIN_REF.fullmatch(value.split(":", 1)[0]):
                    lease_main = True
            elif option in {"delete", "prune"}:
                delete = True  # `--prune` deletes what a glob refspec no longer names, main included
            elif option == "all":
                wide = True
            elif option == "mirror":
                wide = force = True  # mirroring forces every ref, main included
        elif len(arg) > 1 and arg[0] == "-":
            for position, char in enumerate(arg[1:], 1):
                if char == "o":  # the rest of the word, or the next word, is its value
                    if position == len(arg) - 1:
                        i += 1
                    break
                option = PUSH_SHORT.get(char)
                if char == "f" or option == "force":
                    force = True
                elif option == "delete":
                    delete = True
        else:
            operands.append(arg)
    return force, delete, wide, lease_main, operands


CONFIG_SOURCE = (
    "this {what} reads git configuration the guard cannot see ({source}), which may skip hooks or "
    "force what it pushes. Run git without it."
)
FORCED_BY_CONFIG = (
    "the configuration of this push ({source}) forces or mirrors main/master, and force-pushing "
    "main/master is not allowed."
)
UNREAD_CONFIG_ENV = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG")


def unread_config_source(action: dict) -> str | None:
    """A configuration source the guard does not read, set by the command itself: an include
    (`-c include.path=...`) or a config file chosen by the environment (`GIT_CONFIG_GLOBAL=...`)."""
    for raw_config in action.get("configs", []):
        key, _value = config_pair(raw_config)
        if key.lower() == "include.path" or key.lower().startswith("includeif."):
            return f"`{key}`"
    for name in UNREAD_CONFIG_ENV:
        if name in action.get("env", {}):
            return f"`{name}`"
    return None


def brace_words(word: str) -> list[str]:
    """The words a brace expansion makes of `word` (`+mai{n,n}` is `+main`), or `word` itself."""
    if "{" not in word or "," not in word:
        return [word]
    alternatives = sorted(option for option in residues(word) if option)
    return alternatives or [word]


def forced_refspec_main(value: str) -> bool:
    """Whether a `remote.<name>.push` refspec forces main/master (or a glob that may be it)."""
    if not value.startswith("+"):
        return False
    dest = value[1:].rsplit(":", 1)[-1]
    return bool(MAIN_REF.fullmatch(dest) or "*" in dest or dest in {"", "HEAD", "@"})


def forced_by_config(action: dict, operands: list[str]) -> None:
    """Block a push whose remote's configuration forces or mirrors main: given in the command
    (`-c remote.origin.push=+refs/heads/main:refs/heads/main`, `-c remote.origin.mirror=true`)
    or configured in the repository, for a push that names no refspec of its own."""
    for raw_config in action.get("configs", []):
        key, value = config_pair(raw_config)
        key = key.lower()
        if key.startswith("remote.") and key.endswith(".mirror") and not config_value_false(value):
            raise block(FORCED_BY_CONFIG.format(source=f"`{key}`"))
        if key.startswith("remote.") and key.endswith(".push") and forced_refspec_main(value):
            raise block(FORCED_BY_CONFIG.format(source=f"`{key}`"))
    if len(operands) > 1:
        return
    remote = operands[0] if operands else "origin"
    if UNKNOWN_PATH.search(remote) or "/" in remote or ":" in remote:
        return  # a URL or path names no configured remote
    mirror = git_output(action, ["config", "--bool", f"remote.{remote}.mirror"])
    if (mirror or "").strip() == "true":
        raise block(FORCED_BY_CONFIG.format(source=f"`remote.{remote}.mirror`"))
    pushes = git_output(action, ["config", "--get-all", f"remote.{remote}.push"]) or ""
    if any(forced_refspec_main(line.strip()) for line in pushes.splitlines()):
        raise block(FORCED_BY_CONFIG.format(source=f"`remote.{remote}.push`"))


def check_push(action: dict) -> None:
    if action.get("unreadable"):
        raise block(GIT_UNREADABLE)
    args = own_args(action.get("args", []))
    for raw_config in action.get("configs", []):
        key, _value = config_pair(raw_config)
        if key.lower() == "core.hookspath":
            raise block("git push with core.hooksPath override bypasses pre-push hooks")

    config_source = unread_config_source(action)
    if config_source:
        raise block(CONFIG_SOURCE.format(source=config_source, what="push"))
    # the same command switched branches first (`git checkout main && git push -f origin HEAD`):
    # the branch read now is not the one the push will see
    branch_output = None if action.get("branch_unknown") else git_output(action, ["branch", "--show-current"])
    current_branch = (branch_output or "").strip()
    push_force = False
    dest_main = False
    ref_wide = False
    has_explicit_ref = False
    delete_push = False
    operands = read_push_options(args)
    if operands is None:
        raise block("git push --no-verify bypasses pre-push hooks")
    push_force, delete_push, ref_wide, lease_main, operands = operands
    if lease_main:
        dest_main = has_explicit_ref = True

    # `$(git branch --show-current)` is expanded by the shell where it stands, which is the
    # push's repository only when nothing (`-C`, `env -C`, `--git-dir`, `--work-tree`) moves it
    runs_here = (
        action["workdir"] is not None
        and action["workdir"] == action.get("shell_dir")
        and not action.get("git_dir")
        and not action.get("work_tree")
        and "GIT_DIR" not in action.get("env", {})
        and "GIT_WORK_TREE" not in action.get("env", {})
    )

    forced_by_config(action, operands)
    # the first operand is the repository, whatever it spells; the refspecs follow it. A brace
    # word is every word it expands to (`{main,main}` is `main main`)
    refspecs = [alternative for operand in operands[1:] for alternative in brace_words(operand)]
    for operand in refspecs:
        force_refspec = operand.startswith("+")
        refspec = operand[1:] if force_refspec else operand
        if force_refspec:
            push_force = True
        if refspec == ":":
            ref_wide = True
        has_explicit_ref = True
        deleting_ref = refspec.startswith(":")
        dest = refspec.rsplit(":", 1)[-1]
        if dest in {"HEAD", "@"} or (runs_here and dest in shell_tokens.CURRENT_BRANCH_SUBSTITUTIONS):
            if branch_output is None and (push_force or delete_push or deleting_ref):
                raise block(PUSH_BRANCH_UNREADABLE)
            dest = current_branch
        elif EXPANSION.search(dest) and (push_force or delete_push or deleting_ref):
            raise block(
                "the guard cannot read which branch this push updates (its destination "
                f"`{dest}` is expanded by the shell), and force-pushing or deleting main/master "
                "is not allowed. Name the branch (`git push --force origin <branch>`)."
            )
        if MAIN_REF.fullmatch(dest or "") or "*" in dest:  # a glob may be main
            dest_main = True
            if deleting_ref:
                delete_push = True

    if push_force and not has_explicit_ref and not dest_main:
        push_target = (
            git_output(action, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}"]) or ""
        ).strip()
        if re.fullmatch(r"([^/]+/)?(main|master)", push_target or ""):
            dest_main = True
    if push_force and (ref_wide or dest_main):
        raise block("force-pushing main/master is not allowed")
    if push_force and not has_explicit_ref:
        if branch_output is None:
            raise block(PUSH_BRANCH_UNREADABLE)
        if current_branch in {"main", "master"}:
            raise block("force-pushing main/master is not allowed")
    if delete_push and dest_main:
        raise block("deleting main/master is not allowed")
