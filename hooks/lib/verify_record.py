"""What a passing check ran on: the record `scripts/verify.py` writes and the
git guard reads before `gh pr create`.

A record names the commit the check started from (`base`) and the exact
content that differed from it in the working tree (`changes`: path to blob id,
or `None` for a deletion). The guard accepts a PR when `git diff --raw base
HEAD` shows exactly those changes. So a check run before the commit counts once
the commit holds exactly what was tested, a check run after a clean commit
counts as is, and any edit in between does not. Local notes and `.ai-toolkit/`
(the caller's `skip`) never count on either side.

Nothing here writes inside `.git` (no objects, no index, no lock), because
Codex keeps `.git` read-only in its sandbox: blob ids come from `git
hash-object` without `-w`, git runs with `--no-optional-locks`, and records
live in `<top level>/.ai-toolkit/verify.json`, which the git guard keeps out of
commits. Standard library only: the guard runs it standalone.

Known limits (a tripwire, not proof): a mode-only change (`chmod +x`) is not
compared, and the record says what ran, not that it was the right check.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from typing import Callable

RECORD = Path(".ai-toolkit") / "verify.json"
KEEP = 20
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
TIMEOUT_SECONDS = 15
LEVELS = ("strong", "partial")

Skip = Callable[[str], bool]


def git(cwd: str, *args: str, data: bytes | None = None) -> str | None:
    """Run git in `cwd`; stdout, or None when it fails."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", *args],
            cwd=cwd,
            input=data,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            **({} if data is not None else {"stdin": subprocess.DEVNULL}),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "surrogateescape")


def toplevel(cwd: str) -> str | None:
    out = git(cwd, "rev-parse", "--show-toplevel")
    return out.strip() if out else None


def commit(top: str, ref: str = "HEAD") -> str | None:
    out = git(top, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out.strip() if out else None


def blob_id(top: str, path: str) -> str | None:
    """The id git would store for `path` as it is on disk; None if it is gone."""
    full = Path(top, path)
    if full.is_symlink():
        out = git(top, "hash-object", "--stdin", data=os.fsencode(os.readlink(full)))
    elif full.is_file():
        out = git(top, "hash-object", "--", path)
    elif full.is_dir():
        out = git(str(full), "rev-parse", "HEAD")  # a submodule: its checked-out commit
    else:
        return None
    return out.strip() if out else "unreadable"


def _paths(out: str | None) -> list[str]:
    return [path for path in (out or "").split("\0") if path]


def worktree_changes(top: str, base: str, skip: Skip) -> dict[str, str | None] | None:
    """Every path whose working-tree content differs from `base`, with its blob id."""
    tracked = git(top, "diff", "--name-only", "--no-renames", "-z", base, "--")
    untracked = git(top, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or untracked is None:
        return None
    changes: dict[str, str | None] = {}
    # An untracked nested repository lists as `dir/`; only an explicit `git add` commits it.
    nested = {path for path in _paths(untracked) if path.endswith("/")}
    for path in sorted((set(_paths(tracked)) | set(_paths(untracked))) - nested):
        if not skip(path):
            changes[path] = blob_id(top, path)
    return changes


def tracked(top: str, paths: set[str]) -> set[str]:
    """The subset of `paths` git tracks."""
    if not paths:
        return set()
    out = git(top, "--literal-pathspecs", "ls-files", "-z", "--", *sorted(paths))
    return set(_paths(out)) & paths


def committed_changes(top: str, base: str, target: str, skip: Skip) -> dict[str, str | None] | None:
    """Every path that differs between `base` and `target`, with its blob id in `target`."""
    out = git(top, "diff", "--raw", "--no-renames", "--no-abbrev", "-z", base, target, "--")
    if out is None:
        return None
    fields = out.split("\0")
    changes: dict[str, str | None] = {}
    for header, path in zip(fields[0::2], fields[1::2]):
        parts = header.split()
        if len(parts) < 5 or not path or skip(path):
            continue
        changes[path] = None if parts[4].startswith("D") else parts[3]
    return changes


def load(top: str) -> list[dict]:
    try:
        data = json.loads((Path(top) / RECORD).read_text())
    except (OSError, ValueError):
        return []
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return []
    return [
        r for r in records
        if isinstance(r, dict)
        and isinstance(r.get("base"), str)
        and isinstance(r.get("changes"), dict)
        and isinstance(r.get("command"), str)
        and isinstance(r.get("exit"), int)
    ]


def append(top: str, record: dict) -> Path:
    path = Path(top) / RECORD
    path.parent.mkdir(exist_ok=True)
    records = (load(top) + [record])[-KEEP:]
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"records": records}, indent=1) + "\n")
    os.replace(temporary, path)
    return path


def new_record(base: str, changes: dict, command: str, exit_code: int, level: str, left_to_ci: str, stable: bool) -> dict:
    return {
        "base": base,
        "changes": changes,
        "command": command,
        "exit": exit_code,
        "level": level,
        "left_to_ci": left_to_ci,
        "stable": stable,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def describe_mismatch(tested: dict, committed: dict | None) -> str:
    if committed is None:
        return "its starting commit is no longer in this repository"
    parts = []
    only_tested = sorted(set(tested) - set(committed))
    only_committed = sorted(set(committed) - set(tested))
    differ = sorted(p for p in set(tested) & set(committed) if tested[p] != committed[p])
    for label, paths in (
        ("tested but not in the commit", only_tested),
        ("in the commit but not tested", only_committed),
        ("changed since the run", differ),
    ):
        if paths:
            shown = ", ".join(paths[:5]) + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
            parts.append(f"{label}: {shown}")
    return "; ".join(parts)


def verdict(top: str, target: str, skip: Skip) -> tuple[bool, str, dict | None]:
    """Whether `target` has a passing record: (ok, reason when not, the record)."""
    records = load(top)
    if not records:
        return False, "no check has been recorded in this checkout", None
    matching = []
    cache: dict[str, dict | None] = {}
    for record in records:
        base = record["base"]
        if base not in cache:
            cache[base] = committed_changes(top, base, target, skip)
        if cache[base] is not None and cache[base] == record["changes"]:
            matching.append(record)
    if not matching:
        newest = records[-1]
        mismatch = describe_mismatch(newest["changes"], cache.get(newest["base"]))
        return False, f"no recorded check ran on this tree (the newest record differs: {mismatch})", None
    newest_per_command: dict[str, dict] = {}
    for record in matching:
        newest_per_command[record["command"]] = record
    for record in newest_per_command.values():
        if record["exit"] != 0:
            return False, f"the newest run of `{record['command']}` on this tree failed (exit {record['exit']})", None
        if record.get("stable") is False:
            return False, f"`{record['command']}` changed files while it ran, so it did not check this tree", None
    return True, "", matching[-1]
