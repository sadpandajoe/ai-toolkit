"""What a git command does, on the way, to a later push or commit in the same command:
`effects(action)`, from one table of what is proven neutral (`NEUTRAL`) and readers for the rest.

Four effects per subcommand, each `N` (neutral) or `U` (unknown):
- `branch`: which branch HEAD is (a later forced push of HEAD, or one with no refspec, needs it);
- `index`: what a later commit commits (`paths` adds the paths a reader can name);
- `destination`: where a later push with no refspec goes (`branch -u`, `remote rename`, `push -u`);
- `commits`: whether it commits the index itself (`merge --continue`, `write-tree`): `YES`, or `U`.

A reader is neutral only when every option word is in its list (`git_options`, git 2.39's, resolved
by unique prefix and short cluster as git's parse-options does); any other option makes its effect
unknown. A subcommand not in the table is unknown for the branch and the index; a name that is no
git command (a third-party `git absorb`, a `!` alias) is unknown for all four.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re

from git_options import OPTIONS
from guard_base import git_output, names

N, U, YES = "n", "u", "yes"
UNKNOWN_PATH = ""  # the same marker as `git_rules.UNKNOWN_ADDED`: a path the guard cannot name

# Neutral for all four: commands that read, or set up, without moving HEAD or the index.
NEUTRAL = frozenset(
    """status log diff show grep blame annotate describe shortlog reflog rev-parse rev-list ls-files ls-tree
    ls-remote cat-file merge-base check-ignore check-attr check-mailmap check-ref-format for-each-ref show-ref
    show-branch name-rev format-patch diff-tree diff-index diff-files whatchanged range-diff cherry count-objects
    fsck verify-commit verify-tag verify-pack var help version archive bundle request-pull hash-object
    interpret-trailers stripspace merge-tree difftool rerere pack-refs commit-graph checkout-index fetch gc prune
    repack maintenance worktree init clone notes tag clean lfs rm config add stage update-index send-pack
    commit-tree""".split()
)
EXPANDED = re.compile(r"[$`]")
PATHSPEC_PATTERN = re.compile(r"[*?\[]|^:")  # a glob or pathspec magic (`*.md`, `:(icase)project.md`)
SUBMODULE_ADD_VALUES = {"-b", "--branch", "--name", "--reference", "--depth"}
SUBMODULE_ADD_FLAGS = {"-q", "--quiet", "-f", "--force", "--dissociate", "--"}


@dataclass
class Effect:
    branch: str = N
    index: str = N
    paths: list = field(default_factory=list)
    destination: str = N
    commits: str = N
    known: bool = True  # every option word was read (a maybe-git reading contributes only then)


def resolve_long(name: str, longs: dict) -> tuple[str, bool] | None:
    """(option, negated) for a long option as parse-options reads it: exact, `no-` and a name, or the
    one option it is a unique prefix of; None for an unknown or ambiguous text."""
    if name in longs:
        return name, False
    if name.startswith("no-") and name[3:] in longs:
        return name[3:], True
    found = {(option, False) for option in longs if option.startswith(name)}
    if name.startswith("no-"):
        found |= {(option, True) for option in longs if option.startswith(name[3:])}
    return found.pop() if len(found) == 1 else None


def read_options(command: str, args: list[str]) -> tuple[dict, list[str], bool]:
    """(options by long name, operands, whether every option was known) of `git COMMAND ARGS`. The
    operands keep a `--` so readers can tell paths from revisions."""
    spec = OPTIONS[command]
    longs, shorts = spec["long"], spec["short"]
    options: dict = {}
    operands: list[str] = []
    known = True
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            operands.append("--")
            operands.extend(args[index:])
            break
        if arg.startswith("--") and len(arg) > 2:
            name, equals, value = arg[2:].partition("=")
            resolved = resolve_long(name, longs)
            if resolved is None:
                known = False
                continue
            option, negated = resolved
            if negated:
                options["no-" + option] = True
                continue
            kind = longs[option]
            if kind == "value" and not equals:
                value = args[index] if index < len(args) else ""
                index += 1
            options[option] = value if (equals or kind == "value") else True
        elif arg.startswith("-") and len(arg) > 1:
            for position, char in enumerate(arg[1:], 1):
                if char not in shorts:
                    known = False
                    break
                option, kind = shorts[char]
                rest = arg[position + 1 :]
                if kind == "value":
                    if rest:
                        options[option] = rest
                    else:
                        options[option] = args[index] if index < len(args) else ""
                        index += 1
                    break
                if kind == "optional":
                    options[option] = rest or True
                    break
                options[option] = True
        else:
            operands.append(arg)
    return options, operands, known


def split_paths(operands: list[str]) -> tuple[list[str], list[str] | None]:
    """(the operands before `--`, the paths after it, or None with no `--`)."""
    if "--" in operands:
        cut = operands.index("--")
        return operands[:cut], operands[cut + 1 :]
    return operands, None


def resolves(action: dict, rev: str, tree: bool = False) -> bool:
    if EXPANDED.search(rev):
        return False
    return git_output(action, ["rev-parse", "--verify", "-q", rev + ("^{tree}" if tree else "")]) is not None


def tree_paths(action: dict, tree: str, paths: list[str]) -> list[str]:
    """The tree reader: what `<tree> -- <paths>` stages that HEAD does not have (`git diff`, which
    reads globs and pathspec magic as checkout does; `ls-tree` reads them literally), else the tree's
    own listing (an unborn HEAD), else the literal paths. A path the guard cannot name for an expanded
    tree or path, or for a pattern only the first listing reads."""
    if EXPANDED.search(tree) or any(EXPANDED.search(path) for path in paths):
        return [UNKNOWN_PATH]
    changed = names(git_output(action, ["diff", "--name-only", "-z", "--no-renames", "HEAD", tree, "--", *paths]))
    if changed is not None:
        return changed
    if any(PATHSPEC_PATTERN.search(path) for path in paths):
        return [UNKNOWN_PATH]
    listed = names(git_output(action, ["ls-tree", "-r", "-z", "--name-only", tree, "--", *paths]))
    return listed if listed is not None else list(paths)


def file_checkout(args: list[str]) -> bool:
    """`git checkout -- file`, `git checkout <tree> -- file`, `-p`: a `--` with a path after it
    (`git checkout main --` switches to main)."""
    if any(arg in {"-p", "--patch"} for arg in args):
        return True
    return "--" in args and args.index("--") < len(args) - 1


def checkout_effect(action: dict, args: list[str]) -> Effect:
    branch = N if file_checkout(args) else U  # anything but a file checkout may change the branch
    options, operands, known = read_options("checkout", args)
    if not known:
        return Effect(branch=U, index=U, known=False)
    if any(name in options for name in ("b", "B", "orphan", "detach", "patch")):
        return Effect(branch=branch)
    revisions, paths = split_paths(operands)
    if "pathspec-from-file" in options:  # every path of the tree, since the file's are unread
        return Effect(branch=branch, paths=tree_paths(action, revisions[0], []) if revisions else [])
    if paths:
        return Effect(branch=branch, paths=tree_paths(action, revisions[0], paths) if revisions else [])
    if paths is not None:
        return Effect(branch=branch)  # `checkout other --`: a switch, so the index is that commit's
    if len(operands) <= 1:
        return Effect(branch=branch)  # a branch switch or a path from the index: both neutral
    if resolves(action, operands[0], tree=True):
        return Effect(branch=branch, paths=tree_paths(action, operands[0], operands[1:]))
    return Effect(branch=branch, paths=list(operands))  # a branch made earlier in this command, perhaps


def reset_effect(action: dict, args: list[str]) -> Effect:
    options, operands, known = read_options("reset", args)
    if not known:
        return Effect(index=U, known=False)
    revisions, paths = split_paths(operands)
    if "soft" in options:
        rev = revisions[0] if revisions else "HEAD"
        if EXPANDED.search(rev) or action.get("workdir") is None:
            return Effect(paths=[UNKNOWN_PATH])
        if not resolves(action, rev):
            return Effect()  # the reset fails, so nothing it would undo is staged
        listed = names(git_output(action, ["diff", "--name-only", "-z", "--no-renames", rev, "HEAD"]))
        return Effect(paths=listed if listed is not None else [UNKNOWN_PATH])
    if "pathspec-from-file" in options:  # every path of the tree, since the file's are unread
        tree = revisions[0] if revisions else "HEAD"
        return Effect() if tree in {"HEAD", "@"} else Effect(paths=tree_paths(action, tree, []))
    if paths is not None:
        tree = revisions[0] if revisions else "HEAD"
        return Effect() if tree in {"HEAD", "@"} else Effect(paths=tree_paths(action, tree, paths))
    if len(operands) <= 1:
        return Effect()  # a commit (`reset HEAD~1`: the index is the new HEAD) or a path from HEAD
    if operands[0] in {"HEAD", "@"}:
        return Effect()
    if resolves(action, operands[0], tree=True):
        return Effect(paths=tree_paths(action, operands[0], operands[1:]))
    return Effect(paths=list(operands))


def restore_effect(action: dict, args: list[str]) -> Effect:
    options, operands, known = read_options("restore", args)
    if not known:
        return Effect(index=U, known=False)
    if "staged" not in options:
        return Effect()
    source = options.get("source")
    _revisions, paths = split_paths(operands)
    paths = paths if paths is not None else [operand for operand in operands if operand != "--"]
    if not source or source is True or source in {"HEAD", "@"}:
        return Effect()
    return Effect(paths=tree_paths(action, source, paths))


def read_tree_effect(action: dict, args: list[str]) -> Effect:
    options, operands, known = read_options("read-tree", args)
    if not known or options or len(operands) != 1:
        return Effect(index=U, known=known)
    return Effect(paths=tree_paths(action, operands[0], []))


def mv_effect(action: dict, args: list[str]) -> Effect:
    _options, operands, known = read_options("mv", args)
    operands = [operand for operand in operands if operand != "--"]
    if not known or len(operands) < 2:
        return Effect(index=U if not known else N, known=known)
    destination, sources = operands[-1], operands[:-1]
    if any(EXPANDED.search(word) for word in operands):
        return Effect(paths=[UNKNOWN_PATH])
    workdir = action.get("workdir")
    is_dir = workdir is not None and os.path.isdir(os.path.join(workdir, destination))
    if is_dir or len(sources) > 1:
        return Effect(paths=[os.path.join(destination, os.path.basename(source.rstrip("/"))) for source in sources])
    return Effect(paths=[destination])


def apply_effect(_action: dict, args: list[str]) -> Effect:
    options, _operands, known = read_options("apply", args)
    if not known or any(name in options for name in ("cached", "index", "3way")):
        return Effect(index=U, known=known)
    return Effect()


def branch_effect(_action: dict, args: list[str]) -> Effect:
    options, _operands, known = read_options("branch", args)
    if not known:
        return Effect(branch=U, destination=U, known=False)
    moved = any(name in options for name in ("move", "M", "m"))
    upstream = any(name in options for name in ("set-upstream-to", "unset-upstream", "u"))
    return Effect(branch=U if moved else N, destination=U if upstream else N)


def rebase_effect(_action: dict, args: list[str]) -> Effect:
    options, operands, known = read_options("rebase", args)
    if not known:
        return Effect(branch=U, known=False)
    operands = [operand for operand in operands if operand != "--"]
    branch = U if (len(operands) >= 2 or ("root" in options and len(operands) >= 1)) else N
    return Effect(branch=branch, commits=YES if "continue" in options else N)


def merge_like(command: str):
    def effect(_action: dict, args: list[str]) -> Effect:
        options, _operands, known = read_options(command, args)
        if not known:
            return Effect(index=U, known=False)
        staged = any(name in options for name in ("squash", "no-commit"))
        return Effect(index=U if staged else N, commits=YES if "continue" in options else N)

    return effect


def am_effect(_action: dict, args: list[str]) -> Effect:
    options, _operands, known = read_options("am", args)
    return Effect(commits=YES if ("continue" in options or "resolved" in options) else N, known=known)


def stash_effect(_action: dict, args: list[str]) -> Effect:
    verb = next((arg for arg in args if not arg.startswith("-")), "push")
    if verb == "branch":
        return Effect(branch=U, index=U)
    if verb in {"apply", "pop"}:
        return Effect(index=U)  # they re-stage files added before the stash
    if verb in {"push", "save", "list", "show", "drop", "clear", "create", "store"}:
        return Effect()
    return Effect(index=U)


def submodule_effect(_action: dict, args: list[str]) -> Effect:
    """`submodule add [options] <repository> [<path>]` stages `.gitmodules` and the path; an option
    it does not know leaves the path unnamed."""
    words = list(args)
    while words and words[0].startswith("-"):
        words.pop(0)  # `git submodule --quiet add ...`
    if words[:1] != ["add"]:
        return Effect()
    operands: list[str] = []
    rest = iter(words[1:])
    for word in rest:
        if word in SUBMODULE_ADD_VALUES:
            next(rest, None)
        elif word.startswith("--") and word.partition("=")[0] in SUBMODULE_ADD_VALUES:
            continue
        elif word.startswith("-b") and len(word) > 2:
            continue  # `-bmain`
        elif word in SUBMODULE_ADD_FLAGS:
            continue
        elif word.startswith("-"):
            return Effect(paths=[".gitmodules", UNKNOWN_PATH], known=False)
        else:
            operands.append(word)
    if len(operands) > 1:
        path = operands[1]
    else:
        path = os.path.basename(operands[0].rstrip("/")).removesuffix(".git") if operands else ""
    return Effect(paths=[".gitmodules", path] if path else [".gitmodules"])


def symbolic_ref_effect(_action: dict, args: list[str]) -> Effect:
    """A write of HEAD (`symbolic-ref [-m <reason>] HEAD <ref>`, `-d HEAD`) moves the branch. Any two
    words with HEAD among them count, so a `-m` reason is never taken for the name."""
    operands = [arg for arg in args if not arg.startswith("-")]
    if any(arg in {"-d", "--delete"} for arg in args) or (len(operands) >= 2 and "HEAD" in operands):
        return Effect(branch=U)
    return Effect()


def update_ref_effect(_action: dict, args: list[str]) -> Effect:
    return Effect(branch=U) if any(arg in {"HEAD", "--stdin"} for arg in args) else Effect()


def remote_effect(_action: dict, args: list[str]) -> Effect:
    words = [arg for arg in args if not arg.startswith("-")]
    return Effect(destination=U) if words[:1] == ["rename"] else Effect()


def push_effect(_action: dict, args: list[str]) -> Effect:
    options, _operands, known = read_options("push", args)
    return Effect(destination=U if ("set-upstream" in options or not known) else N, known=known)


READERS = {
    "checkout": checkout_effect,
    "switch": lambda _action, _args: Effect(branch=U),
    "reset": reset_effect,
    "restore": restore_effect,
    "read-tree": read_tree_effect,
    "mv": mv_effect,
    "apply": apply_effect,
    "branch": branch_effect,
    "rebase": rebase_effect,
    "merge": merge_like("merge"),
    "pull": merge_like("pull"),
    "cherry-pick": merge_like("cherry-pick"),
    "revert": merge_like("revert"),
    "am": am_effect,
    "stash": stash_effect,
    "submodule": submodule_effect,
    "symbolic-ref": symbolic_ref_effect,
    "update-ref": update_ref_effect,
    "remote": remote_effect,
    "push": push_effect,
    "commit": lambda _action, _args: Effect(),
    "write-tree": lambda _action, _args: Effect(commits=YES),
    "bisect": lambda _action, _args: Effect(branch=U, index=U),
}


def effects(action: dict, args: list[str], names: frozenset | None) -> Effect:
    """The effects of one action (`args` are its own words). An unlisted git command is unknown
    for the branch and the index; a name git does not know (or a `!` alias) for all four."""
    subcommand = action.get("subcommand") or ""
    if action.get("effects_unknown"):
        return Effect(branch=U, index=U, destination=U, commits=U)
    if subcommand in READERS:
        return READERS[subcommand](action, args)
    if subcommand in NEUTRAL:
        return Effect()
    if names is not None and subcommand not in names:
        return Effect(branch=U, index=U, destination=U, commits=U)
    return Effect(branch=U, index=U)
