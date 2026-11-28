"""The git guard's commit and push rules: `check_commit`, `check_push`, the push options read
as git's parse-options does (`PUSH_OPTIONS`), and the protected paths (`STATE_FILES`)."""

from __future__ import annotations

import fnmatch
import os
import re

import shell_tokens
from shell_dirs import UNKNOWN_PATH
from shell_lex import brace_expand, residues
import git_effects
from guard_base import Blocked, SEPARATORS, block, config_pair, git_output, names


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
EXPANDED_PATH = re.compile(r"[$`]")  # a parameter or command substitution: what it names is unknown


def paths_added(action: dict) -> list[str]:
    """What `git add <args>` (or `git stage`) would stage, as repository paths where git can
    tell. A brace word is every path it makes; a path an expansion names is `UNKNOWN_ADDED`."""
    if unread_config_source(action, listing=True):
        return [UNKNOWN_ADDED]  # the dry run cannot see the config this add reads
    if any(arg.startswith("--pathspec-from-file") for arg in own_args(action.get("args", []))):
        return [UNKNOWN_ADDED]  # paths from a file or stdin (`--pathspec-from-file=-`)
    args = [alternative for arg in own_args(action.get("args", [])) for alternative in brace_words(arg)]
    if BRACE_OVERFLOW in args or any(EXPANDED_PATH.search(arg) and not arg.startswith("-") for arg in args):
        return [UNKNOWN_ADDED]  # (a glob is git's to read: its dry run below matches it)
    listed = git_output(action, ["add", "--dry-run", *args])
    if listed is not None:
        found = []
        for line in listed.splitlines():
            match = re.match(r"^(add|remove) '(.*)'$", line.strip())
            if not match:
                return [UNKNOWN_ADDED]  # the dry run prints paths raw: a newline in one splits it
            if match.group(1) == "add":
                found.append(match.group(2))
        return found
    # The dry run failed (for example an ignored path without -f): fall back to
    # the literal pathspecs, so a refused add still counts as an attempt; a glob counts
    # for every state file it matches (`PROJECT.m?`)
    literal = [arg for arg in args if not arg.startswith("-")]
    globbed = [name for arg in literal if re.search(r"[*?\[]", arg) for name in STATE_FILES if fnmatch.fnmatch(name, os.path.basename(arg))]
    return literal + globbed


def update_index_paths(action: dict) -> list[str]:
    """The paths `git update-index --add` (or `--cacheinfo`) puts in the index."""
    if unread_config_source(action, listing=True):
        return [UNKNOWN_ADDED]
    args = own_args(action.get("args", []))
    if any(arg in {"--stdin", "--index-info"} for arg in args):
        return [UNKNOWN_ADDED]  # paths from stdin
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
    if any(EXPANDED_PATH.search(path) for path in found):
        return [UNKNOWN_ADDED]
    return found


GIT_UNREADABLE_MAYBE = (
    "this command has more expansions that may be git than the guard reads (16), and one may push "
    "or commit. Run git by its name."
)
BRACES_UNREADABLE = (
    "a brace word in this git command makes more words than the guard reads (1,024), and one may be "
    "a push or commit flag or main. Spell the words out."
)
BRACE_OVERFLOW = "\ue002"  # a brace word past the expansion limit
SUBCOMMAND_UNREADABLE = (
    "the guard cannot read which git subcommand `{word}` is (a substitution, an operator form, an "
    "array, the positional parameters after `set`, or a variable this command sets to a value it "
    "cannot read), and it may be a push or a commit with any flags. Write the git subcommand literally."
)
VALUES_UNREADABLE = (
    "this command gives a variable more values than the guard reads, and one may be a push or a "
    "commit with any flags. Write the git command literally."
)
SPECULATIVE = (
    "`{word}` is set in this command to a value the guard cannot read, and the words after it, read "
    "as `git {subcommand}`, {what}. Write the command literally."
)
GIT_UNREADABLE = (
    "git in this command is nested too deep for the guard to read (sh -c, eval, functions "
    "or substitution spans more than 8 levels in), so it cannot tell what it pushes or commits. "
    "Run git as a plain command."
)


def check_speculative(action: dict) -> None:
    """A reading of `$C <words>` as `git push <words>` or `git commit <words>`, where the command
    sets C to a value the guard cannot read. It blocks only on what no ordinary command spells:
    a forced or deleting push that names main/master or every ref, or `--no-verify` in full. The
    current branch and short flags are not read (`$RM -rf build`, `$PY -m pytest -n 4`)."""
    args = own_args(action.get("args", []))
    word, subcommand = action["speculative"], action.get("subcommand")
    if any(long_option_prefix(arg, "--no-verify", "--no-veri") for arg in args):
        raise block(SPECULATIVE.format(word=word, subcommand=subcommand, what="skip the hooks (`--no-verify`)"))
    if subcommand != "push":
        return
    read = read_push_options(args)
    if read is None:
        return
    force, delete, wide, lease_main, operands = read
    refspecs = operands[1:]
    forced = force or any(spec.startswith("+") for spec in refspecs)
    deleting = delete or any(spec.startswith(":") and len(spec) > 1 for spec in refspecs)
    dests = [spec.lstrip("+").rsplit(":", 1)[-1] for spec in refspecs]
    names_main = lease_main or any(MAIN_REF.fullmatch(dest) or "*" in dest for dest in dests)
    if (forced or deleting) and (wide or names_main or ":" in refspecs):
        raise block(SPECULATIVE.format(word=word, subcommand=subcommand, what="force-push or delete main/master"))


COMMIT_OPTION_UNKNOWN = (
    "this `git commit` has an option the guard does not know (it knows git 2.39's), so it cannot tell "
    "what the commit stages, and local workflow state files must stay out of commits. Spell the "
    "options as git 2.39 does."
)
HOOK_SKIP_ENV = (("HUSKY", lambda value: value.strip() == "0"), ("HUSKY_SKIP_HOOKS", lambda value: bool(value.strip())),
                 ("SKIP", lambda value: bool(value.strip())))


def hook_skip(action: dict, what: str) -> None:
    """Block a commit or push whose environment tells a hook manager to skip hooks (`HUSKY=0`,
    `SKIP=lint` for pre-commit)."""
    env = action.get("env", {})
    for name, skips in HOOK_SKIP_ENV:
        if name in env and skips(env[name]):
            raise block(f"git {what} with `{name}={env[name]}` skips the hooks the toolkit runs")


def commit_staging(action: dict, args: list[str]) -> list[str]:
    """What `git commit` stages by itself: the tracked changes with `-a`, the paths it names
    (with `-i`/`-o` or alone), `UNKNOWN_ADDED` for `--pathspec-from-file`. An option the guard does
    not know blocks (`COMMIT_OPTION_UNKNOWN`), except in a reading the guard guessed (git's
    subcommand an expansion, or git itself one): words git would not take are probably not git's,
    so the options and literal paths it does know are read (a newer git may take the rest)."""
    options, operands, known = git_effects.read_options("commit", args)
    if not known:
        if not (action.get("guessed") or action.get("maybe_git")):
            raise block(COMMIT_OPTION_UNKNOWN)
        operands = [operand for operand in operands if not EXPANDED_PATH.search(operand)]
    found: list[str] = []
    if "pathspec-from-file" in options:
        found.append(UNKNOWN_ADDED)
    if "all" in options:
        listed = names(git_output(action, ["diff", "--name-only", "-z"]))
        found += listed if listed is not None else [UNKNOWN_ADDED]
    paths = [operand for operand in operands if operand != "--"]
    if paths:
        if any(EXPANDED_PATH.search(path) for path in paths):
            found.append(UNKNOWN_ADDED)
        else:
            listed = names(git_output(action, ["diff", "--name-only", "-z", "HEAD", "--", *paths]))
            found += listed if listed is not None else paths
    return found


def check_committed_index(action: dict, added_before: list[str], seen_only: bool) -> None:
    """A command that commits the index without `git commit` (`merge --continue`, `rebase
    --continue`, `write-tree`): the state-file rule on what the index and the earlier commands
    staged, and its `--no-verify` spelled long. `seen_only` (a command the guard does not know may
    do it): only a state file actually seen blocks."""
    args = own_args(action.get("args", []))
    if not seen_only and any(long_option_prefix(arg, "--no-verify", "--no-veri") for arg in args):
        raise block(f"git {action.get('subcommand')} --no-verify skips the hooks the toolkit runs")
    staged = names(git_output(action, ["diff", "--cached", "--name-only", "-z"]))
    if staged is None and not seen_only:
        raise block(
            f"the guard cannot read what `git {action.get('subcommand')}` commits (the repository or its "
            "staged files could not be read), and local workflow state files must stay out of commits."
        )
    if UNKNOWN_ADDED in added_before and not seen_only:
        raise block(
            f"the guard cannot tell what `git {action.get('subcommand')}` commits: the same command stages "
            "paths the guard cannot list. Run it as a command of its own."
        )
    protected = sorted({path for path in (staged or []) + added_before if is_protected_path(path)})
    if protected:
        raise block(
            f"local workflow state is part of what `git {action.get('subcommand')}` commits ("
            + ", ".join(protected) + "). Unstage it first (git reset HEAD <file>)."
        )


def check_commit(action: dict, added_before: list[str]) -> None:
    if action.get("unreadable"):
        raise block(action.get("unreadable_why") or GIT_UNREADABLE)
    config_source = unread_config_source(action)
    if config_source:
        raise block(CONFIG_SOURCE.format(source=config_source, what="commit"))
    if UNKNOWN_ADDED in added_before:
        raise block(
            "the guard cannot tell what this commit includes: the same command stages paths the "
            "guard cannot list (a path an expansion names, or an add under configuration the guard "
            "cannot read), and local workflow state files must stay out of commits. Stage named "
            "paths, or run `git commit` as a command of its own."
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

    hook_skip(action, "commit")
    extra = commit_staging(action, args)
    if UNKNOWN_ADDED in extra:
        raise block(
            "the guard cannot tell what this commit includes (it names a path an expansion makes, or "
            "takes paths from a file or stdin with `--pathspec-from-file`), and local workflow state "
            "files must stay out of commits. Stage named paths, then commit."
        )
    staged = names(git_output(action, ["diff", "--cached", "--name-only", "-z"]))
    if staged is None:
        raise block(
            "the guard cannot read what this commit includes (the repository or its staged "
            "files could not be read), and local workflow state files must stay out of "
            "commits. Run `git commit` from the repository."
        )
    candidates = staged + added_before + extra
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
# Variables that redirect or drop a config file git reads. The guard's own queries never take
# them from the command (`guard_base.QUERY_ENV`), so with one set they cannot see what git will.
UNREAD_CONFIG_ENV = (
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG", "GIT_CONFIG_NOSYSTEM",
    "HOME", "XDG_CONFIG_HOME",
)
# Markers the walker leaves in an action's env (never a real name, so no query takes them):
ENV_CLEARED = "\x00cleared"  # `env -i`: git runs with no HOME
UNSET = "\x00unset:"  # `env -u NAME`, `unset NAME`, `export -n NAME`
# Inline keys that change nothing of which paths an add stages or a diff lists (or that the rules
# read themselves); any other inline key makes a listing query unknown.
LISTING_NEUTRAL = re.compile(
    r"(?i)^(?:user|author|committer|alias|gpg|color|advice|i18n|pager|credential|http|push|remote|branch)\."
    r"|^(?:commit\.gpgsign|core\.(?:editor|pager|quotepath|autocrlf|safecrlf|eol)|sequence\.editor"
    r"|init\.defaultbranch)$"
)


def unread_config_source(action: dict, listing: bool = False) -> str | None:
    """A configuration source the guard does not read, set by the command itself: an include
    (`-c include.path=...`), a config file the environment chooses or drops (`GIT_CONFIG_GLOBAL=`,
    `HOME=`, `env -i`, `unset HOME`), or, for a query that lists paths (`listing`), an inline key
    that may change what it lists (`-c core.excludesFile=...`)."""
    for raw_config in action.get("configs", []):
        key, _value = config_pair(raw_config)
        if key.lower() == "include.path" or key.lower().startswith("includeif."):
            return f"`{key}`"
    env = action.get("env", {})
    for name in UNREAD_CONFIG_ENV:
        if name in env:
            return f"`{name}`"
    if ENV_CLEARED in env:
        return "`env -i`"
    for name in ("HOME", "XDG_CONFIG_HOME"):
        if UNSET + name in env:
            return f"an unset `{name}`"
    if listing:
        for raw_config in action.get("configs", []):
            key, _value = config_pair(raw_config)
            if not LISTING_NEUTRAL.match(key):
                return f"`-c {key}`"
    return None


PUSH_DEST_KEY = re.compile(
    r"(?i)^(?:remote\..+\.(?:push|mirror)|push\..+|remote\.pushdefault|branch\..+\.(?:merge|remote|pushremote))$"
)


def brace_words(word: str) -> list[str]:
    """The words a brace expansion makes of `word` (`+mai{n,n}` is `+main`, `ma{i..i}n` is `main`),
    in bash's order, with the residues of its expansions as well; `[BRACE_OVERFLOW]` past the
    expansion limit; or `word` itself."""
    if "{" not in word or ("," not in word and ".." not in word):
        return [word]
    made = brace_expand(word)
    if made is None:
        return [BRACE_OVERFLOW]
    alternatives = sorted(option for option in residues(word) if option)
    return [option for option in made if option] + [option for option in alternatives if option not in made] or [word]


def forced_refspec_main(value: str, forced: bool = False) -> bool:
    """Whether a `remote.<name>.push` refspec forces main/master (or a glob that may be it): a `+`
    one, or any one when the push itself is forced."""
    if not value.startswith("+") and not forced:
        return False
    dest = value.lstrip("+").rsplit(":", 1)[-1]
    return bool(MAIN_REF.fullmatch(dest) or "*" in dest or dest in {"", "HEAD", "@"})


def forced_by_config(action: dict, operands: list[str], forced: bool = False) -> None:
    """Block a push whose remote's configuration forces or mirrors main: given in the command
    (`-c remote.origin.push=+refs/heads/main:refs/heads/main`, `-c remote.origin.mirror=true`)
    or configured in the repository, for a push that names no refspec of its own."""
    for raw_config in action.get("configs", []):
        key, value = config_pair(raw_config)
        key = key.lower()
        if PUSH_DEST_KEY.match(key) and (value == "<config-env>" or EXPANSION.search(value)):
            # a value the guard cannot read may be `+refs/heads/main:refs/heads/main`
            raise block(FORCED_BY_CONFIG.format(source=f"`{key}`, a value the guard cannot read"))
        if key.startswith("remote.") and key.endswith(".mirror") and not config_value_false(value):
            raise block(FORCED_BY_CONFIG.format(source=f"`{key}`"))
        if key.startswith("remote.") and key.endswith(".push") and forced_refspec_main(value, forced):
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
    if any(forced_refspec_main(line.strip(), forced) for line in pushes.splitlines()):
        raise block(FORCED_BY_CONFIG.format(source=f"`remote.{remote}.push`"))


def check_push(action: dict) -> None:
    if action.get("unreadable"):
        raise block(action.get("unreadable_why") or GIT_UNREADABLE)
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

    hook_skip(action, "push")
    forced_by_config(action, operands, push_force)
    if (push_force or delete_push) and len(operands) <= 1:
        # no refspec of its own: where it goes comes from configuration
        if action.get("destination_unknown"):
            raise block(
                "an earlier command in this command changes where a push goes (an upstream or a remote "
                "rename), so the guard cannot tell which branch this forced push updates, and "
                "force-pushing main/master is not allowed. Name the branch (`git push --force origin <branch>`)."
            )
        supplied = [config_pair(raw)[0] for raw in action.get("configs", []) if PUSH_DEST_KEY.match(config_pair(raw)[0])]
        if supplied:
            raise block(
                f"this forced push sets where it goes (`{supplied[0]}`) in the same command, so the guard "
                "cannot tell which branch it updates. Set push configuration and force-push in separate commands."
            )
        default = git_output(action, ["config", "--get", "push.default"])
        if push_force and (default or "").strip().lower() == "matching":
            raise block(FORCED_BY_CONFIG.format(source="`push.default=matching`"))
    # the first operand is the repository, whatever it spells; the refspecs follow it. A brace
    # word is every word it expands to (`{main,main}` is `main main`)
    refspecs = [alternative for operand in operands[1:] for alternative in brace_words(operand)]
    if BRACE_OVERFLOW in refspecs and (push_force or delete_push):
        raise block(BRACES_UNREADABLE)
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
