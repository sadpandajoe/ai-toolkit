"""Non-destructive source-linked installation with one-level recovery."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import tomllib
import uuid

from .build import write_build
from .conformance import validate_contracts
from .interfaces import (
    load_skill_interfaces,
    validate_provider_interfaces,
    validate_skill_interfaces,
    validate_support_interface,
)
from .model_routing import validate_model_routing
from .workflows import (
    extension_manifest_path,
    load_workflows,
    validate_extension_workflows,
    validate_workflows,
)


BEGIN = "# >>> ai-toolkit managed guidance >>>"
END = "# <<< ai-toolkit managed guidance <<<"
LEDGER_VERSION = 1
FAILPOINT_ENV = "AITK_INSTALL_FAILPOINT"


class LifecycleError(RuntimeError):
    """A lifecycle operation refused unsafe or inconsistent state."""


@dataclass(frozen=True)
class InstallPaths:
    root: Path
    home: Path
    codex_home: Path
    agents_dir: Path

    @property
    def state_dir(self) -> Path:
        return self.home / ".ai-toolkit"

    @property
    def ledger(self) -> Path:
        return self.state_dir / "install-state.json"

    @property
    def backups(self) -> Path:
        return self.state_dir / "backups"


@dataclass(frozen=True)
class Target:
    name: str
    kind: str
    target: Path
    source: Path


@dataclass(frozen=True)
class LifecycleResult:
    operation: str
    status: str
    changed: tuple[str, ...]
    conflicts: tuple[str, ...]
    ledger: str

    @property
    def exit_code(self) -> int:
        return 0 if self.status in {"ok", "noop"} else 1

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "status": self.status,
            "changed": list(self.changed),
            "conflicts": list(self.conflicts),
            "ledger": self.ledger,
        }


@contextmanager
def _lifecycle_lock(paths: InstallPaths):
    lock_root = Path(tempfile.gettempdir()) / (
        f"ai-toolkit-lifecycle-locks-{os.getuid()}"
    )
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = lock_root.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or lock_root.is_symlink()
    ):
        raise LifecycleError("lifecycle lock directory is unsafe")
    os.chmod(lock_root, 0o700)
    # All lifecycle transactions use one user-scoped lock. Different option
    # tuples can still share a ledger, guidance target, or skill root, so a
    # tuple-keyed lock cannot safely detect every overlap.
    lock_path = lock_root / "lifecycle.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        lock_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.getuid()
            or lock_metadata.st_nlink != 1
        ):
            raise LifecycleError("lifecycle lock file is unsafe")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _serialized_lifecycle(function):
    @wraps(function)
    def wrapped(paths: InstallPaths, *args, **kwargs):
        try:
            _validate_source(paths.root)
            with _lifecycle_lock(paths):
                _validate_source(paths.root)
                return function(paths, *args, **kwargs)
        except (LifecycleError, OSError, TypeError, ValueError) as error:
            return LifecycleResult(
                function.__name__, "refused", (), (str(error),), str(paths.ledger)
            )

    return wrapped


def resolve_paths(
    root: Path,
    home: Path | None = None,
    codex_home: Path | None = None,
    agents_dir: Path | None = None,
) -> InstallPaths:
    root = root.resolve()
    selected_home = (home or Path.home()).expanduser().resolve()
    selected_codex = (
        (codex_home or Path(os.environ.get("CODEX_HOME", selected_home / ".codex")))
        .expanduser()
        .resolve()
    )
    selected_agents = (
        (agents_dir or Path(os.environ.get("AGENTS_DIR", selected_home / ".agents")))
        .expanduser()
        .resolve()
    )
    return InstallPaths(root, selected_home, selected_codex, selected_agents)


def _validate_source(root: Path) -> None:
    problems = validate_workflows(root)
    if extension_manifest_path(root, "pgm").is_file():
        problems.extend(validate_extension_workflows(root, "pgm"))
    problems.extend(validate_skill_interfaces(root))
    problems.extend(validate_provider_interfaces(root))
    problems.extend(validate_model_routing(root))
    problems.extend(validate_support_interface(root))
    problems.extend(validate_contracts(root))
    if problems:
        raise LifecycleError(
            "source interface validation failed: " + "; ".join(problems)
        )


def _product_version(root: Path) -> str:
    return str(
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    )


def _sha_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _read_text_exact(path: Path) -> str:
    """Decode UTF-8 without universal-newline translation."""
    return path.read_bytes().decode("utf-8")


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fail(point: str) -> None:
    if os.environ.get(FAILPOINT_ENV) == point:
        raise LifecycleError(f"injected installer failure at {point}")


def _public_skills(root: Path, with_pgm: bool) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for item in load_skill_interfaces(root):
        if item["classification"] not in {"public_router", "public_direct"}:
            continue
        if item["name"] == "pgm" and not with_pgm:
            continue
        result.append((item["name"], root / item["path"]))
    return sorted(result)


def desired_targets(paths: InstallPaths, with_pgm: bool) -> list[Target]:
    workflows = load_workflows(paths.root, include_pgm=with_pgm)
    result = [
        Target(
            "claude-guidance",
            "guidance",
            paths.home / ".claude/CLAUDE.md",
            paths.root / "build/config/CLAUDE.md",
        ),
        Target(
            "codex-guidance",
            "guidance",
            paths.codex_home / "AGENTS.md",
            paths.root / "build/config/AGENTS.md",
        ),
    ]
    result.extend(
        Target(
            f"command:{workflow.name}",
            "symlink",
            paths.home / ".claude/commands" / f"{workflow.name}.md",
            paths.root / "build/commands" / f"{workflow.name}.md",
        )
        for workflow in workflows
    )
    for name, source in _public_skills(paths.root, with_pgm):
        result.append(
            Target(
                f"claude-skill:{name}",
                "symlink",
                paths.home / ".claude/skills" / name,
                source,
            )
        )
        result.append(
            Target(
                f"agent-skill:{name}",
                "symlink",
                paths.agents_dir / "skills" / name,
                source,
            )
        )
    return sorted(result, key=lambda item: str(item.target))


def _legacy_targets(paths: InstallPaths) -> dict[Path, tuple[str, ...]]:
    result: dict[Path, tuple[str, ...]] = {}
    for item in load_skill_interfaces(paths.root):
        name = item["name"]
        relative = Path(item["path"])
        candidates = [relative.as_posix()]
        if name == "pgm":
            candidates.extend(
                ("extensions/pgm/skills/pgm", "extensions/pgm/skills/pgm-comms")
            )
            result[paths.codex_home / "skills/pgm-comms"] = tuple(candidates)
        result[paths.codex_home / "skills" / name] = tuple(candidates)
    return result


def _legacy_directories(paths: InstallPaths) -> dict[Path, tuple[str, ...]]:
    return {
        paths.home / ".claude/commands": ("build/commands",),
        paths.home / ".claude/skills": ("skills",),
        paths.agents_dir / "skills": ("skills",),
    }


def _managed_span(text: str) -> tuple[int, int] | None:
    starts = [
        match.start() for match in re.finditer(rf"(?m)^{re.escape(BEGIN)}\r?$", text)
    ]
    finishes = [
        match.end() for match in re.finditer(rf"(?m)^{re.escape(END)}\r?$", text)
    ]
    if not starts and not finishes:
        return None
    if len(starts) != 1 or len(finishes) != 1 or finishes[0] < starts[0]:
        raise LifecycleError("managed guidance markers are malformed or duplicated")
    finish = finishes[0]
    if finish < len(text) and text[finish] == "\n":
        finish += 1
    return starts[0], finish


def _strip_guidance(text: str, separator: str = "") -> str:
    span = _managed_span(text)
    if span is None:
        return text
    start, finish = span
    prefix = text[:start]
    if separator:
        if not prefix.endswith(separator):
            raise LifecycleError("managed guidance separator drifted")
        prefix = prefix[: -len(separator)]
    return prefix + text[finish:]


def _guidance_block(source: Path) -> str:
    body = _read_text_exact(source).rstrip("\n")
    return f"{BEGIN}\n{body}\n{END}\n"


def _merge_guidance(existing: str, source: Path) -> str:
    span = _managed_span(existing)
    if span is not None:
        start, finish = span
        return existing[:start] + _guidance_block(source) + existing[finish:]
    separator = (
        ""
        if not existing or existing.endswith("\n\n")
        else "\n"
        if existing.endswith("\n")
        else "\n\n"
    )
    return existing + separator + _guidance_block(source)


def _guidance_separator(existing: str) -> str:
    if not existing or existing.endswith("\n\n"):
        return ""
    return "\n" if existing.endswith("\n") else "\n\n"


def _block_hash(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    text = _read_text_exact(path)
    start = text.find(f"{BEGIN}\n")
    finish = text.find(f"{END}\n", start + len(BEGIN) + 1)
    if start < 0 or finish < 0:
        return None
    finish += len(END) + 1
    return _sha_bytes(text[start:finish].encode())


def _root_for_target(paths: InstallPaths, target: Path) -> Path:
    normalized = Path(os.path.normpath(str(target)))
    if not target.is_absolute() or normalized != target:
        raise LifecycleError(f"target is not normalized and absolute: {target}")
    candidates = [paths.home, paths.codex_home, paths.agents_dir]
    matches = [
        root for root in candidates if target == root or target.is_relative_to(root)
    ]
    if not matches:
        raise LifecycleError(f"target escapes selected roots: {target}")
    return max(matches, key=lambda value: len(value.parts))


def _reject_symlink_ancestors(paths: InstallPaths, target: Path) -> None:
    root = _root_for_target(paths, target)
    current = root
    relative = target.relative_to(root)
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise LifecycleError(f"symlink ancestor is not allowed: {current}")


def _created_parents(paths: InstallPaths, target: Path) -> list[Path]:
    _reject_symlink_ancestors(paths, target)
    root = _root_for_target(paths, target)
    missing: list[Path] = []
    current = target.parent
    while current != root and not current.exists():
        missing.append(current)
        current = current.parent
    if current == root and root != paths.home and not root.exists():
        missing.append(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        _fsync_dir(directory.parent)
    return missing


def _atomic_bytes(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        _fsync_dir(path.parent)
    elif path.is_dir():
        shutil.rmtree(path)
        _fsync_dir(path.parent)


def _tree_digest(path: Path) -> str:
    entries: list[str] = []
    for child in sorted(path.rglob("*")):
        relative = child.relative_to(path).as_posix()
        if child.is_symlink():
            entries.append(f"L {relative} {os.readlink(child)}")
        elif child.is_file():
            entries.append(
                f"F {relative} {_sha_file(child)} {stat.S_IMODE(child.stat().st_mode):o}"
            )
        elif child.is_dir():
            entries.append(f"D {relative} {stat.S_IMODE(child.stat().st_mode):o}")
    return _sha_bytes("\n".join(entries).encode())


def _snapshot(
    path: Path, backup_dir: Path | None = None, index: int = 0
) -> dict[str, object]:
    if path.is_symlink():
        return {
            "target": str(path),
            "state": "symlink",
            "link_target": os.readlink(path),
        }
    if path.is_file():
        data = path.read_bytes()
        result: dict[str, object] = {
            "target": str(path),
            "state": "file",
            "sha256": _sha_bytes(data),
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
        if backup_dir is not None:
            relative = Path("files") / f"{index:04d}"
            backup = backup_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            _atomic_bytes(backup, data, int(result["mode"]))
            result["backup"] = relative.as_posix()
        return result
    if path.is_dir():
        result = {
            "target": str(path),
            "state": "directory",
            "tree_hash": _tree_digest(path),
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
        if backup_dir is not None:
            relative = Path("directories") / f"{index:04d}"
            destination = backup_dir / relative
            shutil.copytree(path, destination, symlinks=True)
            _fsync_dir(destination.parent)
            result["backup"] = relative.as_posix()
        return result
    if path.exists():
        raise LifecycleError(f"managed target is not a file or symlink: {path}")
    return {"target": str(path), "state": "absent"}


def _snapshot_many(
    targets: list[Path], backup_dir: Path | None = None
) -> list[dict[str, object]]:
    return [
        _snapshot(path, backup_dir, index)
        for index, path in enumerate(sorted(set(targets)))
    ]


def _snapshot_matches(snapshot: dict[str, object]) -> bool:
    path = Path(str(snapshot["target"]))
    state = snapshot["state"]
    if state == "absent":
        return not os.path.lexists(path)
    if state == "symlink":
        return path.is_symlink() and os.readlink(path) == snapshot["link_target"]
    if state == "file":
        return (
            path.is_file()
            and not path.is_symlink()
            and _sha_file(path) == snapshot["sha256"]
            and stat.S_IMODE(path.stat().st_mode) == snapshot["mode"]
        )
    if state == "directory":
        return (
            path.is_dir()
            and not path.is_symlink()
            and _tree_digest(path) == snapshot["tree_hash"]
            and stat.S_IMODE(path.stat().st_mode) == snapshot["mode"]
        )
    return False


def _restore(snapshots: list[dict[str, object]], backup_dir: Path | None) -> None:
    for snapshot in snapshots:
        path = Path(str(snapshot["target"]))
        _remove(path)
        if snapshot["state"] == "absent":
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if snapshot["state"] == "symlink":
            path.symlink_to(str(snapshot["link_target"]))
            _fsync_dir(path.parent)
        elif snapshot["state"] == "file":
            if backup_dir is None or "backup" not in snapshot:
                raise LifecycleError(f"missing backup for {path}")
            backup = backup_dir / str(snapshot["backup"])
            if not backup.is_file() or _sha_file(backup) != snapshot["sha256"]:
                raise LifecycleError(f"corrupt backup for {path}")
            _atomic_bytes(path, backup.read_bytes(), int(snapshot["mode"]))
        elif snapshot["state"] == "directory":
            if backup_dir is None or "backup" not in snapshot:
                raise LifecycleError(f"missing directory backup for {path}")
            backup = backup_dir / str(snapshot["backup"])
            if not backup.is_dir() or _tree_digest(backup) != snapshot["tree_hash"]:
                raise LifecycleError(f"corrupt directory backup for {path}")
            shutil.copytree(backup, path, symlinks=True)
            os.chmod(path, int(snapshot["mode"]))
            _fsync_dir(path.parent)


def _prune_dirs(directories: list[str]) -> None:
    for value in sorted(
        {Path(item) for item in directories},
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if value.is_dir() and not value.is_symlink():
            try:
                value.rmdir()
            except OSError:
                continue
            _fsync_dir(value.parent)


def _write_ledger(paths: InstallPaths, payload: dict[str, object]) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    if paths.state_dir.is_symlink():
        raise LifecycleError(f"state directory cannot be a symlink: {paths.state_dir}")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".install-state.", dir=paths.state_dir
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fail("ledger-temp-written")
        os.replace(temporary, paths.ledger)
        os.chmod(paths.ledger, 0o600)
        _fsync_dir(paths.state_dir)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _load_ledger(paths: InstallPaths) -> dict[str, object] | None:
    if (
        paths.state_dir.is_symlink()
        or paths.ledger.is_symlink()
        or paths.backups.is_symlink()
    ):
        raise LifecycleError("install state paths cannot be symlinks")
    if not paths.ledger.exists():
        return None
    if stat.S_IMODE(paths.ledger.stat().st_mode) != 0o600:
        raise LifecycleError("install ledger mode must be 0600")
    payload = json.loads(paths.ledger.read_text())
    _validate_ledger(paths, payload)
    return payload


def _allowed_targets(paths: InstallPaths) -> set[str]:
    desired = desired_targets(paths, with_pgm=True)
    return (
        {str(item.target) for item in desired}
        | {str(path) for path in _legacy_targets(paths)}
        | {str(path) for path in _legacy_directories(paths)}
    )


def _allowed_records(paths: InstallPaths) -> dict[str, Target]:
    return {str(item.target): item for item in desired_targets(paths, with_pgm=True)}


def _allowed_owned_dirs(paths: InstallPaths) -> set[str]:
    result: set[str] = set()
    for item in desired_targets(paths, with_pgm=True):
        root = _root_for_target(paths, item.target)
        current = item.target.parent
        while current != root:
            result.add(str(current))
            current = current.parent
        if root != paths.home:
            result.add(str(root))
    return result


def _validate_backup_relative(value: object) -> None:
    if not isinstance(value, str):
        raise LifecycleError("ledger backup path must be relative")
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != "backups"
    ):
        raise LifecycleError(f"ledger backup path escapes state root: {value}")


def _validate_snapshot(
    paths: InstallPaths,
    value: object,
    *,
    backed_up: bool,
) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("target"), str):
        raise LifecycleError("invalid ledger snapshot")
    if value["target"] not in _allowed_targets(paths):
        raise LifecycleError(
            f"ledger target is outside managed inventory: {value['target']}"
        )
    target = Path(value["target"])
    _reject_symlink_ancestors(paths, target)
    state = value.get("state")
    if not isinstance(state, str) or state not in {
        "absent",
        "file",
        "symlink",
        "directory",
    }:
        raise LifecycleError("invalid ledger snapshot state")
    common = {"target", "state"}
    expected = {
        "absent": common,
        "symlink": common | {"link_target"},
        "file": common | {"sha256", "mode"},
        "directory": common | {"tree_hash", "mode"},
    }[str(state)]
    if backed_up and state in {"file", "directory"}:
        expected = expected | {"backup"}
    if set(value) != expected:
        raise LifecycleError("ledger snapshot fields do not match its state")
    if state == "symlink" and not isinstance(value.get("link_target"), str):
        raise LifecycleError("invalid ledger symlink snapshot")
    if state in {"file", "directory"}:
        digest = value.get("sha256" if state == "file" else "tree_hash")
        if not isinstance(digest, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", digest
        ):
            raise LifecycleError("invalid ledger snapshot digest")
        mode = value.get("mode")
        if (
            not isinstance(mode, int)
            or isinstance(mode, bool)
            or not 0 <= mode <= 0o777
        ):
            raise LifecycleError("invalid ledger snapshot mode")
    if "backup" in value:
        relative = Path(str(value["backup"]))
        expected_prefix = "files" if state == "file" else "directories"
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) != 2
            or relative.parts[0] != expected_prefix
        ):
            raise LifecycleError("snapshot backup escapes transaction")


def _validate_active(paths: InstallPaths, value: object, ledger_root: Path) -> None:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("kind"), str)
        or value.get("kind") not in {"guidance", "symlink"}
    ):
        raise LifecycleError("invalid active ownership record")
    common = {"name", "kind", "target", "source", "created"}
    expected = common | (
        {"link_target"}
        if value["kind"] == "symlink"
        else {"block_hash", "full_hash", "mode", "separator"}
    )
    if set(value) != expected:
        raise LifecycleError("active ownership fields do not match its kind")
    if not isinstance(value.get("name"), str) or not isinstance(
        value.get("created"), bool
    ):
        raise LifecycleError("invalid active ownership metadata")
    target = value.get("target")
    source = value.get("source")
    allowed = _allowed_records(paths)
    if not isinstance(target, str) or target not in allowed:
        raise LifecycleError(f"ledger target is outside managed inventory: {target}")
    expected_record = allowed[str(target)]
    if value["kind"] != expected_record.kind or value["name"] != expected_record.name:
        raise LifecycleError("ledger ownership kind or name does not match its target")
    if not isinstance(source, str):
        raise LifecycleError(f"ledger source escapes recorded toolkit root: {source}")
    try:
        relative_source = Path(source).relative_to(ledger_root)
    except ValueError as error:
        raise LifecycleError(
            f"ledger source escapes recorded toolkit root: {source}"
        ) from error
    expected_source = expected_record.source.relative_to(paths.root)
    if relative_source != expected_source:
        raise LifecycleError(f"ledger source is outside managed inventory: {source}")
    if value["kind"] == "symlink":
        if value.get("link_target") != source:
            raise LifecycleError("managed symlink source and link target differ")
    else:
        if value.get("separator") not in {"", "\n", "\n\n"}:
            raise LifecycleError("invalid managed guidance separator")
        if not all(
            isinstance(value.get(field), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", str(value[field]))
            for field in ("block_hash", "full_hash")
        ):
            raise LifecycleError("invalid managed guidance digest")
        mode = value.get("mode")
        if (
            not isinstance(mode, int)
            or isinstance(mode, bool)
            or not 0 <= mode <= 0o777
        ):
            raise LifecycleError("invalid managed guidance mode")
    _reject_symlink_ancestors(paths, Path(str(target)))


def _validate_ledger(paths: InstallPaths, payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("version") != LEDGER_VERSION:
        raise LifecycleError("install ledger must use schema version 1")
    expected = {
        "version",
        "status",
        "toolkit_version",
        "toolkit_root",
        "extensions",
        "active",
        "owned_dirs",
        "conflicts",
        "last_transaction",
    }
    if set(payload) != expected:
        raise LifecycleError("install ledger fields do not match schema version 1")
    if not isinstance(payload["status"], str) or payload["status"] not in {
        "installed",
        "uninstalled",
        "rolled_back",
    }:
        raise LifecycleError("invalid install ledger status")
    if (
        not isinstance(payload["toolkit_root"], str)
        or not Path(payload["toolkit_root"]).is_absolute()
        or Path(payload["toolkit_root"]).resolve(strict=False)
        != Path(payload["toolkit_root"])
    ):
        raise LifecycleError("invalid recorded toolkit root")
    ledger_root = Path(payload["toolkit_root"])
    if (
        not isinstance(payload["toolkit_version"], str)
        or not payload["toolkit_version"]
    ):
        raise LifecycleError("invalid recorded toolkit version")
    if (
        not isinstance(payload["extensions"], list)
        or any(item != "pgm" for item in payload["extensions"])
        or len(set(payload["extensions"])) != len(payload["extensions"])
    ):
        raise LifecycleError("invalid recorded extensions")
    if (
        not isinstance(payload["active"], list)
        or not isinstance(payload["owned_dirs"], list)
        or not isinstance(payload["conflicts"], list)
    ):
        raise LifecycleError("invalid install ledger collections")
    for item in payload["active"]:
        _validate_active(paths, item, ledger_root)
    if len({item["target"] for item in payload["active"]}) != len(payload["active"]):
        raise LifecycleError("duplicate active ownership target")
    allowed_owned_dirs = _allowed_owned_dirs(paths)
    for directory in payload["owned_dirs"]:
        if not isinstance(directory, str) or directory not in allowed_owned_dirs:
            raise LifecycleError("invalid owned directory")
    if len(set(payload["owned_dirs"])) != len(payload["owned_dirs"]):
        raise LifecycleError("duplicate owned directory")
    if any(not isinstance(item, str) for item in payload["conflicts"]):
        raise LifecycleError("invalid recorded conflict")
    transaction = payload["last_transaction"]
    if transaction is None:
        return
    transaction_fields = {
        "id",
        "operation",
        "before",
        "after",
        "before_active",
        "after_active",
        "before_owned_dirs",
        "after_owned_dirs",
        "before_toolkit_root",
        "after_toolkit_root",
        "before_toolkit_version",
        "after_toolkit_version",
        "before_extensions",
        "after_extensions",
        "backup_path",
        "rollback_status",
    }
    if not isinstance(transaction, dict) or set(transaction) != transaction_fields:
        raise LifecycleError("invalid last transaction")
    if not re.fullmatch(r"[0-9a-f]{32}", str(transaction["id"])):
        raise LifecycleError("invalid transaction id")
    if (
        not isinstance(transaction["operation"], str)
        or transaction["operation"] not in {"install", "upgrade", "uninstall"}
        or not isinstance(transaction["rollback_status"], str)
        or transaction["rollback_status"] not in {"available", "applied"}
    ):
        raise LifecycleError("invalid transaction state")
    _validate_backup_relative(transaction["backup_path"])
    expected_backup = f"backups/{transaction['id']}"
    if transaction["backup_path"] != expected_backup:
        raise LifecycleError("transaction backup path does not match id")
    transaction_backup = paths.state_dir / str(transaction["backup_path"])
    if transaction_backup.is_symlink():
        raise LifecycleError("transaction backup cannot be a symlink")
    roots: dict[str, Path] = {}
    for side in ("before", "after"):
        root_value = transaction[f"{side}_toolkit_root"]
        version_value = transaction[f"{side}_toolkit_version"]
        extension_value = transaction[f"{side}_extensions"]
        if (
            not isinstance(root_value, str)
            or not Path(root_value).is_absolute()
            or Path(root_value).resolve(strict=False) != Path(root_value)
        ):
            raise LifecycleError("invalid transaction toolkit root")
        if not isinstance(version_value, str) or not version_value:
            raise LifecycleError("invalid transaction toolkit version")
        if (
            not isinstance(extension_value, list)
            or any(item != "pgm" for item in extension_value)
            or len(set(extension_value)) != len(extension_value)
        ):
            raise LifecycleError("invalid transaction extensions")
        roots[side] = Path(root_value)
    for collection in ("before", "after"):
        if not isinstance(transaction[collection], list):
            raise LifecycleError("invalid transaction snapshots")
        for snapshot in transaction[collection]:
            _validate_snapshot(paths, snapshot, backed_up=collection == "before")
        targets = [item["target"] for item in transaction[collection]]
        if len(set(targets)) != len(targets):
            raise LifecycleError("duplicate transaction snapshot target")
    if {item["target"] for item in transaction["before"]} != {
        item["target"] for item in transaction["after"]
    }:
        raise LifecycleError("transaction snapshot inventories differ")
    backup_references = [
        item["backup"] for item in transaction["before"] if "backup" in item
    ]
    if len(set(backup_references)) != len(backup_references):
        raise LifecycleError("duplicate transaction backup material")
    for collection in ("before_active", "after_active"):
        if not isinstance(transaction[collection], list):
            raise LifecycleError("invalid transaction ownership")
        for item in transaction[collection]:
            side = "before" if collection == "before_active" else "after"
            _validate_active(paths, item, roots[side])
        if len({item["target"] for item in transaction[collection]}) != len(
            transaction[collection]
        ):
            raise LifecycleError("duplicate transaction ownership target")
    for collection in ("before_owned_dirs", "after_owned_dirs"):
        if not isinstance(transaction[collection], list):
            raise LifecycleError("invalid transaction owned directories")
        if any(
            not isinstance(item, str) or item not in allowed_owned_dirs
            for item in transaction[collection]
        ):
            raise LifecycleError(
                "transaction owned directory is outside managed inventory"
            )
        if len(set(transaction[collection])) != len(transaction[collection]):
            raise LifecycleError("duplicate transaction owned directory")
    side = "after" if transaction["rollback_status"] == "available" else "before"
    if (
        payload["toolkit_root"] != transaction[f"{side}_toolkit_root"]
        or payload["toolkit_version"] != transaction[f"{side}_toolkit_version"]
        or payload["extensions"] != transaction[f"{side}_extensions"]
        or payload["active"] != transaction[f"{side}_active"]
        or payload["owned_dirs"] != transaction[f"{side}_owned_dirs"]
    ):
        raise LifecycleError("ledger state does not match its last transaction")


def _record(
    target: Target, created: bool = False, separator: str = ""
) -> dict[str, object]:
    if target.kind == "symlink":
        return {
            "name": target.name,
            "kind": "symlink",
            "target": str(target.target),
            "source": str(target.source),
            "link_target": str(target.source),
            "created": created,
        }
    return {
        "name": target.name,
        "kind": "guidance",
        "target": str(target.target),
        "source": str(target.source),
        "block_hash": _sha_bytes(_guidance_block(target.source).encode()),
        "full_hash": _sha_file(target.target),
        "mode": stat.S_IMODE(target.target.stat().st_mode),
        "separator": separator,
        "created": created,
    }


def _active_matches(record: dict[str, object], full_guidance: bool = False) -> bool:
    path = Path(str(record["target"]))
    if record["kind"] == "symlink":
        return path.is_symlink() and os.readlink(path) == record["link_target"]
    if (
        not path.is_file()
        or path.is_symlink()
        or _block_hash(path) != record["block_hash"]
    ):
        return False
    return not full_guidance or _sha_file(path) == record["full_hash"]


def _legacy_owned(path: Path, suffixes: tuple[str, ...], roots: set[Path]) -> bool:
    if not path.is_symlink():
        return False
    raw = Path(os.readlink(path))
    resolved = (
        (path.parent / raw).resolve(strict=False)
        if not raw.is_absolute()
        else raw.resolve(strict=False)
    )
    for root in roots:
        for suffix in suffixes:
            candidate = root / suffix
            if raw == candidate or resolved == candidate.resolve(strict=False):
                return True
    return False


def _legacy_guidance_owned(path: Path, name: str, roots: set[Path]) -> bool:
    return _legacy_owned(
        path,
        (f"build/config/{name}", f"config/{name}"),
        roots,
    )


def _legacy_directory_owner(
    target: Path,
    directories: dict[Path, tuple[str, ...]],
    roots: set[Path],
) -> Path | None:
    for directory, suffixes in directories.items():
        if target != directory and not target.is_relative_to(directory):
            continue
        if _legacy_owned(directory, suffixes, roots):
            return directory
    return None


def _backup_transaction(
    paths: InstallPaths, identifier: str, targets: list[Path]
) -> tuple[Path, list[dict[str, object]]]:
    if paths.state_dir.is_symlink() or paths.backups.is_symlink():
        raise LifecycleError("install state paths cannot be symlinks")
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.state_dir, 0o700)
    paths.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.backups, 0o700)
    backup = paths.backups / identifier
    backup.mkdir(mode=0o700, exist_ok=False)
    _fsync_dir(backup.parent)
    before = _snapshot_many(targets, backup)
    _fsync_dir(backup)
    return backup, before


def _validate_backup_material(
    snapshots: list[dict[str, object]],
    backup_dir: Path,
) -> None:
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        raise LifecycleError("transaction backup is missing or unsafe")
    for snapshot in snapshots:
        if snapshot["state"] not in {"file", "directory"}:
            continue
        material = backup_dir / str(snapshot["backup"])
        if material.is_symlink():
            raise LifecycleError(f"backup material is unsafe: {material}")
        if snapshot["state"] == "file":
            if not material.is_file() or _sha_file(material) != snapshot["sha256"]:
                raise LifecycleError(f"corrupt backup for {snapshot['target']}")
        elif not material.is_dir() or _tree_digest(material) != snapshot["tree_hash"]:
            raise LifecycleError(f"corrupt directory backup for {snapshot['target']}")


def _cleanup_failed_backup(paths: InstallPaths, backup: Path) -> None:
    shutil.rmtree(backup, ignore_errors=True)
    if backup.parent.is_dir() and not backup.parent.is_symlink():
        _fsync_dir(backup.parent)
        try:
            backup.parent.rmdir()
        except OSError:
            return
        _fsync_dir(backup.parent.parent)
        try:
            backup.parent.parent.rmdir()
        except OSError:
            return
        _fsync_dir(backup.parent.parent.parent)


def _old_ledger_bytes(paths: InstallPaths) -> tuple[bytes | None, int | None]:
    if not paths.ledger.is_file():
        return None, None
    return paths.ledger.read_bytes(), paths.ledger.stat().st_mtime_ns


def _restore_old_ledger(
    paths: InstallPaths, value: bytes | None, mtime: int | None
) -> None:
    if value is None:
        _remove(paths.ledger)
        return
    _atomic_bytes(paths.ledger, value, 0o600)
    if mtime is not None:
        os.utime(paths.ledger, ns=(mtime, mtime))
        _fsync_dir(paths.state_dir)


def _orphan_backups(
    paths: InstallPaths, ledger: dict[str, object] | None
) -> list[Path]:
    if not paths.backups.is_dir():
        return []
    keep: Path | None = None
    if ledger and isinstance(ledger.get("last_transaction"), dict):
        keep = paths.state_dir / str(ledger["last_transaction"]["backup_path"])
    entries = list(paths.backups.iterdir())
    unsafe = [path for path in entries if path.is_symlink()]
    if unsafe:
        raise LifecycleError(f"orphan backup cannot be a symlink: {unsafe[0]}")
    return [path for path in entries if path.is_dir() and path != keep]


def cleanup_orphan_backups(
    paths: InstallPaths, ledger: dict[str, object] | None
) -> list[str]:
    changed: list[str] = []
    for orphan in _orphan_backups(paths, ledger):
        shutil.rmtree(orphan)
        _fsync_dir(orphan.parent)
        changed.append(str(orphan))
    return changed


@_serialized_lifecycle
def install(paths: InstallPaths, with_pgm: bool = False) -> LifecycleResult:
    operation = "install"
    # Validate every write-driving source interface and the existing ownership
    # ledger before generating adapters or touching installation targets.
    load_workflows(paths.root, include_pgm=with_pgm)
    load_skill_interfaces(paths.root)
    try:
        ledger = _load_ledger(paths)
    except (
        LifecycleError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        return LifecycleResult(
            operation, "refused", (), (str(error),), str(paths.ledger)
        )
    write_build(paths.root, include_pgm=with_pgm)
    changed = cleanup_orphan_backups(paths, ledger)
    desired = desired_targets(paths, with_pgm)
    desired_by_path = {str(item.target): item for item in desired}
    active = list(ledger.get("active", [])) if ledger else []
    active_by_path = {str(item["target"]): item for item in active}
    ownership_created = {
        str(target.target): (
            bool(active_by_path[str(target.target)]["created"])
            if str(target.target) in active_by_path
            else not os.path.lexists(target.target)
        )
        for target in desired
    }
    old_roots = {paths.root}
    if ledger:
        old_roots.add(Path(str(ledger["toolkit_root"])))

    conflicts: list[str] = []
    mutations: list[tuple[str, Target | Path]] = []
    guidance_separators: dict[str, str] = {}
    legacy_directories = _legacy_directories(paths)
    migrating_directories = {
        directory
        for directory, suffixes in legacy_directories.items()
        if _legacy_owned(directory, suffixes, old_roots)
    }
    mutations.extend(
        ("migrate-dir", directory) for directory in sorted(migrating_directories)
    )
    for target in desired:
        legacy_parent = _legacy_directory_owner(
            target.target, legacy_directories, old_roots
        )
        if legacy_parent is None:
            _reject_symlink_ancestors(paths, target.target)
        current_record = active_by_path.get(str(target.target))
        if target.kind == "symlink":
            if legacy_parent is not None:
                mutations.append(("write", target))
                continue
            if target.target.is_symlink() and os.readlink(target.target) == str(
                target.source
            ):
                continue
            if current_record and _active_matches(current_record):
                mutations.append(("write", target))
            elif not os.path.lexists(target.target):
                mutations.append(("write", target))
            else:
                conflicts.append(f"conflict preserved: {target.target}")
        else:
            if current_record and current_record.get("kind") == "guidance":
                guidance_separators[str(target.target)] = str(
                    current_record["separator"]
                )
            elif target.target.is_file() and not target.target.is_symlink():
                current_text = _read_text_exact(target.target)
                guidance_separators[str(target.target)] = (
                    ""
                    if _managed_span(current_text) is not None
                    else _guidance_separator(current_text)
                )
            else:
                guidance_separators[str(target.target)] = ""
            if target.target.is_symlink():
                if _legacy_guidance_owned(
                    target.target,
                    target.source.name,
                    old_roots,
                ):
                    mutations.append(("write", target))
                else:
                    conflicts.append(f"conflict preserved: {target.target}")
            elif target.target.exists() and not target.target.is_file():
                conflicts.append(f"conflict preserved: {target.target}")
            else:
                existing = (
                    _read_text_exact(target.target) if target.target.is_file() else ""
                )
                if _merge_guidance(existing, target.source) != existing:
                    mutations.append(("write", target))

    for record in active:
        if str(record["target"]) in desired_by_path:
            continue
        if not _active_matches(record):
            conflicts.append(f"managed drift preserved: {record['target']}")
        else:
            mutations.append(("remove", Path(str(record["target"]))))

    for path, suffixes in _legacy_targets(paths).items():
        if _legacy_owned(path, suffixes, old_roots):
            mutations.append(("remove", path))

    extensions = ["pgm"] if with_pgm else []
    desired_noop = (
        ledger is not None
        and ledger.get("status") in {"installed", "rolled_back"}
        and ledger.get("extensions") == extensions
        and ledger.get("toolkit_root") == str(paths.root)
        and ledger.get("toolkit_version") == _product_version(paths.root)
        and not mutations
        and not conflicts
        and all(_active_matches(item) for item in active)
    )
    if desired_noop:
        return LifecycleResult(operation, "noop", tuple(changed), (), str(paths.ledger))
    if not mutations and conflicts and not active:
        return LifecycleResult(
            operation, "refused", tuple(changed), tuple(conflicts), str(paths.ledger)
        )

    affected: list[Path] = []
    for _, item in mutations:
        path = item.target if isinstance(item, Target) else item
        if any(
            path != directory and path.is_relative_to(directory)
            for directory in migrating_directories
        ):
            continue
        affected.append(path)
    identifier = uuid.uuid4().hex
    old_ledger, old_mtime = _old_ledger_bytes(paths)
    old_owned_dirs = list(ledger.get("owned_dirs", [])) if ledger else []
    created_dirs: list[str] = []
    backup: Path | None = None
    committed = False
    try:
        backup, before = _backup_transaction(paths, identifier, affected)
        _fail("backup-created")
        for action, item in mutations:
            target_path = item.target if isinstance(item, Target) else item
            if action == "migrate-dir":
                _remove(target_path)
                target_path.mkdir(parents=True, exist_ok=False)
                _fsync_dir(target_path.parent)
                created_dirs.append(str(target_path))
                changed.append(str(target_path))
                _fail("link-mutated")
                continue
            created_dirs.extend(
                str(path) for path in _created_parents(paths, target_path)
            )
            if action == "remove":
                record = active_by_path.get(str(target_path))
                if record and record["kind"] == "guidance":
                    stripped = _strip_guidance(
                        _read_text_exact(target_path), str(record.get("separator", ""))
                    )
                    if stripped or not bool(record["created"]):
                        _atomic_bytes(
                            target_path,
                            stripped.encode(),
                            int(record.get("mode", 0o644)),
                        )
                    else:
                        _remove(target_path)
                    _fail("guidance-mutated")
                else:
                    _remove(target_path)
                    _fail("link-mutated")
                changed.append(str(target_path))
                continue
            assert isinstance(item, Target)
            if item.kind == "symlink":
                _remove(item.target)
                item.target.symlink_to(item.source)
                _fsync_dir(item.target.parent)
                _fail("link-mutated")
            else:
                existing = (
                    _read_text_exact(item.target)
                    if item.target.is_file() and not item.target.is_symlink()
                    else ""
                )
                mode = (
                    stat.S_IMODE(item.target.stat().st_mode)
                    if item.target.is_file() and not item.target.is_symlink()
                    else 0o644
                )
                _remove(item.target)
                _atomic_bytes(
                    item.target, _merge_guidance(existing, item.source).encode(), mode
                )
                _fail("guidance-mutated")
            changed.append(str(item.target))

        new_active: list[dict[str, object]] = []
        for target in desired:
            if (
                target.target.is_symlink()
                and target.kind == "symlink"
                and os.readlink(target.target) == str(target.source)
            ):
                new_active.append(
                    _record(target, created=ownership_created[str(target.target)])
                )
            elif (
                target.kind == "guidance"
                and target.target.is_file()
                and _block_hash(target.target)
                == _sha_bytes(_guidance_block(target.source).encode())
            ):
                new_active.append(
                    _record(
                        target,
                        created=ownership_created[str(target.target)],
                        separator=guidance_separators[str(target.target)],
                    )
                )
        for record in active:
            if str(record["target"]) not in desired_by_path and os.path.lexists(
                str(record["target"])
            ):
                new_active.append(record)
        after = _snapshot_many(affected)
        operation = "upgrade" if ledger and ledger.get("active") else "install"
        new_owned = sorted(set(old_owned_dirs) | set(created_dirs))
        payload: dict[str, object] = {
            "version": LEDGER_VERSION,
            "status": "installed",
            "toolkit_version": _product_version(paths.root),
            "toolkit_root": str(paths.root),
            "extensions": extensions,
            "active": new_active,
            "owned_dirs": new_owned,
            "conflicts": conflicts,
            "last_transaction": {
                "id": identifier,
                "operation": operation,
                "before": before,
                "after": after,
                "before_active": active,
                "after_active": new_active,
                "before_owned_dirs": old_owned_dirs,
                "after_owned_dirs": new_owned,
                "before_toolkit_root": str(ledger["toolkit_root"])
                if ledger
                else str(paths.root),
                "after_toolkit_root": str(paths.root),
                "before_toolkit_version": str(ledger["toolkit_version"])
                if ledger
                else _product_version(paths.root),
                "after_toolkit_version": _product_version(paths.root),
                "before_extensions": list(ledger["extensions"]) if ledger else [],
                "after_extensions": extensions,
                "backup_path": f"backups/{identifier}",
                "rollback_status": "available",
            },
        }
        _write_ledger(paths, payload)
        committed = True
        _fail("ledger-replaced")
        previous = None
        if ledger and isinstance(ledger.get("last_transaction"), dict):
            previous = paths.state_dir / str(ledger["last_transaction"]["backup_path"])
        if previous and previous != backup and previous.is_dir():
            _fail("backup-prune")
            shutil.rmtree(previous)
            _fsync_dir(previous.parent)
    except Exception as error:
        if not committed and backup is not None:
            try:
                _restore(before, backup)
                _prune_dirs(created_dirs)
                _restore_old_ledger(paths, old_ledger, old_mtime)
            finally:
                _cleanup_failed_backup(paths, backup)
        return LifecycleResult(
            operation,
            "drift" if committed else "refused",
            tuple(changed),
            tuple(conflicts + [str(error)]),
            str(paths.ledger),
        )
    return LifecycleResult(
        operation,
        "drift" if conflicts else "ok",
        tuple(changed),
        tuple(conflicts),
        str(paths.ledger),
    )


@_serialized_lifecycle
def uninstall(paths: InstallPaths) -> LifecycleResult:
    operation = "uninstall"
    try:
        ledger = _load_ledger(paths)
    except (
        LifecycleError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        return LifecycleResult(
            operation, "refused", (), (str(error),), str(paths.ledger)
        )
    if ledger is None or not ledger.get("active"):
        return LifecycleResult(
            operation,
            "noop",
            tuple(cleanup_orphan_backups(paths, ledger)),
            (),
            str(paths.ledger),
        )
    active = list(ledger["active"])
    drift = [
        f"managed drift: {item['target']}"
        for item in active
        if not _active_matches(item)
    ]
    if drift:
        return LifecycleResult(
            operation, "refused", (), tuple(drift), str(paths.ledger)
        )
    cleanup_orphan_backups(paths, ledger)
    targets = [Path(str(item["target"])) for item in active]
    identifier = uuid.uuid4().hex
    old_ledger, old_mtime = _old_ledger_bytes(paths)
    backup: Path | None = None
    committed = False
    changed: list[str] = []
    try:
        backup, before = _backup_transaction(paths, identifier, targets)
        _fail("backup-created")
        for item in active:
            target = Path(str(item["target"]))
            if item["kind"] == "guidance":
                stripped = _strip_guidance(
                    _read_text_exact(target), str(item.get("separator", ""))
                )
                if stripped or not bool(item["created"]):
                    _atomic_bytes(
                        target, stripped.encode(), int(item.get("mode", 0o644))
                    )
                else:
                    _remove(target)
                _fail("guidance-mutated")
            else:
                _remove(target)
                _fail("link-mutated")
            changed.append(str(target))
        _prune_dirs(list(ledger["owned_dirs"]))
        after = _snapshot_many(targets)
        payload = {
            "version": LEDGER_VERSION,
            "status": "uninstalled",
            "toolkit_version": _product_version(paths.root),
            "toolkit_root": str(paths.root),
            "extensions": [],
            "active": [],
            "owned_dirs": [],
            "conflicts": [],
            "last_transaction": {
                "id": identifier,
                "operation": "uninstall",
                "before": before,
                "after": after,
                "before_active": active,
                "after_active": [],
                "before_owned_dirs": list(ledger["owned_dirs"]),
                "after_owned_dirs": [],
                "before_toolkit_root": str(ledger["toolkit_root"]),
                "after_toolkit_root": str(paths.root),
                "before_toolkit_version": str(ledger["toolkit_version"]),
                "after_toolkit_version": _product_version(paths.root),
                "before_extensions": list(ledger["extensions"]),
                "after_extensions": [],
                "backup_path": f"backups/{identifier}",
                "rollback_status": "available",
            },
        }
        _write_ledger(paths, payload)
        committed = True
        _fail("ledger-replaced")
        previous = ledger.get("last_transaction")
        if isinstance(previous, dict):
            old_backup = paths.state_dir / str(previous["backup_path"])
            if old_backup != backup and old_backup.is_dir():
                _fail("backup-prune")
                shutil.rmtree(old_backup)
                _fsync_dir(old_backup.parent)
    except Exception as error:
        if not committed and backup is not None:
            try:
                _restore(before, backup)
                _restore_old_ledger(paths, old_ledger, old_mtime)
            finally:
                _cleanup_failed_backup(paths, backup)
        return LifecycleResult(
            operation,
            "drift" if committed else "refused",
            tuple(changed),
            (str(error),),
            str(paths.ledger),
        )
    return LifecycleResult(operation, "ok", tuple(changed), (), str(paths.ledger))


@_serialized_lifecycle
def rollback(paths: InstallPaths) -> LifecycleResult:
    operation = "rollback"
    try:
        ledger = _load_ledger(paths)
    except (
        LifecycleError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        return LifecycleResult(
            operation, "refused", (), (str(error),), str(paths.ledger)
        )
    if ledger is None or not isinstance(ledger.get("last_transaction"), dict):
        return LifecycleResult(
            operation,
            "refused",
            (),
            ("no transaction is available to roll back",),
            str(paths.ledger),
        )
    transaction = ledger["last_transaction"]
    if transaction["rollback_status"] != "available":
        return LifecycleResult(
            operation,
            "refused",
            (),
            ("last transaction was already rolled back",),
            str(paths.ledger),
        )
    before = transaction["before"]
    after = transaction["after"]
    if not all(_snapshot_matches(item) for item in after):
        return LifecycleResult(
            operation,
            "refused",
            (),
            ("current state does not match the transaction after-state",),
            str(paths.ledger),
        )
    backup = paths.state_dir / str(transaction["backup_path"])
    try:
        _validate_backup_material(before, backup)
    except LifecycleError as error:
        return LifecycleResult(
            operation, "refused", (), (str(error),), str(paths.ledger)
        )
    rollback_backup = paths.backups / f".rollback-{transaction['id']}"
    changed: list[str] = []
    current: list[dict[str, object]] = []
    try:
        rollback_backup.mkdir(parents=True, exist_ok=False)
        current = _snapshot_many(
            [Path(str(item["target"])) for item in after], rollback_backup
        )
        _restore(before, backup)
        _prune_dirs(
            [
                item
                for item in transaction["after_owned_dirs"]
                if item not in transaction["before_owned_dirs"]
            ]
        )
        _fail("rollback-restored")
        transaction["rollback_status"] = "applied"
        ledger["status"] = "rolled_back"
        ledger["active"] = transaction["before_active"]
        ledger["owned_dirs"] = transaction["before_owned_dirs"]
        ledger["toolkit_root"] = transaction["before_toolkit_root"]
        ledger["toolkit_version"] = transaction["before_toolkit_version"]
        ledger["extensions"] = transaction["before_extensions"]
        _write_ledger(paths, ledger)
        changed = [str(item["target"]) for item in before]
    except Exception as error:
        if current:
            _restore(current, rollback_backup)
        return LifecycleResult(
            operation, "refused", tuple(changed), (str(error),), str(paths.ledger)
        )
    finally:
        shutil.rmtree(rollback_backup, ignore_errors=True)
    return LifecycleResult(operation, "ok", tuple(changed), (), str(paths.ledger))


def inspect_install(paths: InstallPaths, with_pgm: bool = False) -> tuple[str, ...]:
    """Return read-only installed-state diagnostics; never repairs state."""
    try:
        ledger = _load_ledger(paths)
    except (
        LifecycleError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        return (f"FAIL: {error}",)
    if ledger is None:
        return ("DRIFT: install ledger is missing",)
    findings: list[str] = []
    if ledger["toolkit_root"] != str(paths.root):
        findings.append(
            "DRIFT: installed artifacts point to another toolkit checkout; run install to retarget them"
        )
    if ledger["toolkit_version"] != _product_version(paths.root):
        findings.append(
            "DRIFT: installed toolkit version differs from this checkout; run install to upgrade it"
        )
    if stat.S_IMODE(paths.ledger.stat().st_mode) != 0o600:
        findings.append("FAIL: install ledger mode must be 0600")
    for record in ledger["active"]:
        if not _active_matches(record):
            findings.append(f"FAIL: managed artifact mismatch: {record['target']}")
    for conflict in ledger["conflicts"]:
        findings.append(f"DRIFT: {conflict}")
    if with_pgm and "pgm" not in ledger["extensions"]:
        findings.append("DRIFT: optional PGM extension is not active")
    try:
        orphans = _orphan_backups(paths, ledger)
    except LifecycleError as error:
        findings.append(f"FAIL: {error}")
    else:
        for orphan in orphans:
            findings.append(
                f"DRIFT: orphan backup requires lifecycle cleanup: {orphan}"
            )
    roots = {paths.root, Path(str(ledger["toolkit_root"]))}
    for path, suffixes in _legacy_targets(paths).items():
        if _legacy_owned(path, suffixes, roots):
            findings.append(
                f"DRIFT: legacy Codex skill link requires migration: {path}"
            )
    if not findings:
        findings.append("PASS: installed artifacts match the ownership ledger")
    return tuple(findings)
