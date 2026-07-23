"""Deterministic generation of provider-facing toolkit files."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from .workflows import (
    extension_manifest_path,
    manifest_path,
    validate_extension_workflows,
    validate_workflows,
)


PLACEHOLDER = "{{TOOLKIT_DIR}}"


@dataclass(frozen=True)
class BuildResult:
    written: int
    unchanged: int
    removed: list[Path]


def _target(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"generated destination escapes repository: {relative}")
    target = root / relative
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"generated destination has symlink ancestor: {current}")
    if target.is_symlink():
        raise ValueError(f"generated destination cannot be a symlink: {target}")
    return target


def expected_build(root: Path, include_pgm: bool = False) -> dict[Path, str]:
    """Return the complete generated file map without touching the filesystem."""
    root = root.resolve()
    if manifest_path(root).is_file():
        problems = validate_workflows(root)
        if include_pgm and extension_manifest_path(root, "pgm").is_file():
            problems.extend(validate_extension_workflows(root, "pgm"))
        if problems:
            raise ValueError("invalid workflow interface: " + "; ".join(problems))
    expected: dict[Path, str] = {}
    for config_name in ("CLAUDE.md", "AGENTS.md"):
        source = root / "config" / config_name
        if source.is_file():
            expected[Path("build/config") / config_name] = source.read_text().replace(
                PLACEHOLDER, str(root)
            )

    return expected


def compare_build(root: Path, include_pgm: bool = False) -> list[str]:
    """Describe deterministic build drift in stable path order."""
    root = root.resolve()
    expected = expected_build(root, include_pgm)
    differences: list[str] = []
    for relative, content in expected.items():
        target = _target(root, relative)
        if not target.exists():
            differences.append(f"missing: {relative.as_posix()}")
        elif target.read_text() != content:
            differences.append(f"different: {relative.as_posix()}")

    expected_paths = set(expected)
    generated_directories = [root / "build/config"]
    for directory in generated_directories:
        if not directory.is_dir():
            continue
        for target in sorted(directory.glob("*.md")):
            relative = target.relative_to(root)
            if relative not in expected_paths:
                differences.append(f"extra: {relative.as_posix()}")
    return sorted(differences)


def _write_if_changed(target: Path, content: str) -> bool:
    if target.exists() and target.read_text() == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def write_build(root: Path, include_pgm: bool = False) -> BuildResult:
    """Write the expected build and prune only stale generated Markdown files."""
    root = root.resolve()
    expected = expected_build(root, include_pgm)
    written = 0
    unchanged = 0
    for relative, content in expected.items():
        if _write_if_changed(_target(root, relative), content):
            written += 1
        else:
            unchanged += 1

    removed: list[Path] = []
    expected_paths = set(expected)
    generated_directories = [root / "build/config"]
    for directory in generated_directories:
        if not directory.is_dir():
            continue
        for target in sorted(directory.glob("*.md")):
            relative = target.relative_to(root)
            if relative not in expected_paths:
                _target(root, relative).unlink()
                removed.append(relative)
    return BuildResult(written=written, unchanged=unchanged, removed=removed)
