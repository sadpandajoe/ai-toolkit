"""What the git guard's modules share: `Blocked`, `block`, and the helpers that run git
(`git_output`) and read its config pairs.

`git_guard` runs as `__main__`, so no module imports it: a second copy would carry a second
`Blocked` class."""

from __future__ import annotations

import os
import subprocess


SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&"}


class Blocked(Exception):
    pass


def block(message: str) -> Blocked:
    return Blocked(f"BLOCKED: {message}")


def is_git_executable(token: str) -> bool:
    """`git` or a path to it, whatever the case (`GIT` runs git on a case-insensitive filesystem)."""
    return token.lower() == "git" or ("/" in token and os.path.basename(token).lower() == "git")


def config_pair(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        return raw, ""
    key, value = raw.split("=", 1)
    return key, value


def git_base(action: dict) -> tuple[list[str], str | None]:
    git_args = ["git"]
    if action.get("git_dir"):
        git_args.append(f"--git-dir={action['git_dir']}")
    if action.get("work_tree"):
        git_args.append(f"--work-tree={action['work_tree']}")
    return git_args, action["workdir"]


GIT_OUTPUTS: dict[tuple, str | None] = {}  # one command's git queries, while `CACHING` is on
CACHING = [False]


def git_output(action: dict, args: list[str]) -> str | None:
    git_args, workdir = git_base(action)
    if workdir is None:
        return None
    key = (tuple(git_args + args), workdir, tuple(sorted(action.get("env", {}).items())))
    if CACHING[0] and key in GIT_OUTPUTS:
        return GIT_OUTPUTS[key]  # the same query in one command reads the same repository
    output = run_git(git_args + args, workdir, action.get("env", {}))
    if CACHING[0]:
        GIT_OUTPUTS[key] = output
    return output


def run_git(argv: list[str], workdir: str, extra_env: dict) -> str | None:
    env = os.environ.copy()
    env.update(extra_env)
    try:
        result = subprocess.run(
            argv,
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
