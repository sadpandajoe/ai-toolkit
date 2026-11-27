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


def git_output(action: dict, args: list[str]) -> str | None:
    git_args, workdir = git_base(action)
    if workdir is None:
        return None
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
