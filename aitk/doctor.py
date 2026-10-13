"""Repository health checks for portable AI Toolkit content.

`doctor` checks what a reader would trip over: Markdown links, SKILL.md
frontmatter, and the routing manifest with its marker bijection. It also keeps
the personal-path and secret-output scans, and `--installed` reports the
installed ownership ledger while the installer remains the install path.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from pathlib import Path

from .installer import InstallPaths, inspect_install
from .routing_manifest import validate_model_routing


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    message: str
    details: tuple[str, ...] = ()


CONTENT_DIRECTORIES = ("config", "docs", "extensions", "rules", "skills")
IGNORED_TREE_PARTS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}


def _ignored(root: Path, path: Path) -> bool:
    return any(part in IGNORED_TREE_PARTS for part in path.relative_to(root).parts)


def _markdown_files(root: Path) -> list[Path]:
    files = [root / "README.md"] if (root / "README.md").is_file() else []
    for name in CONTENT_DIRECTORIES:
        directory = root / name
        if directory.is_dir():
            files.extend(
                source
                for source in sorted(directory.rglob("*.md"))
                if not _ignored(root, source)
            )
    return files


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def _skill_descriptions(root: Path) -> Finding:
    """Frontmatter shape is required; the "Use when / Do NOT use" routing is advice.

    A description without both routing halves still loads, so it is reported in
    the details of a passing finding rather than failing `check`.
    """
    problems: list[str] = []
    advice: list[str] = []
    skills = list((root / "skills").glob("*/SKILL.md"))
    skills.extend((root / "extensions").glob("*/skills/*/SKILL.md"))
    for skill in sorted(skills):
        metadata = _frontmatter(skill.read_text())
        description = metadata.get("description", "")
        if not metadata.get("name"):
            problems.append(f"{skill.relative_to(root)}: missing name")
        unexpected = sorted(set(metadata) - {"name", "description"})
        if unexpected:
            problems.append(
                f"{skill.relative_to(root)}: provider-specific fields {', '.join(unexpected)}"
            )
        if (
            not re.search(r"\bUse (?:when|for|to)\b", description, re.I)
            or "Do NOT use" not in description
        ):
            advice.append(
                f"advisory: {skill.relative_to(root)}: description lacks positive and negative routing"
            )
    status = "DRIFT" if problems else "PASS"
    return Finding(
        "skill-descriptions", status, "Skill descriptions", tuple(problems + advice)
    )


def _markdown_links(root: Path) -> Finding:
    problems: list[str] = []
    link_pattern = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")
    for source in _markdown_files(root):
        text = source.read_text()
        for match in link_pattern.finditer(text):
            raw_target = match.group(1).split("#", 1)[0].strip()
            if raw_target.startswith("<"):
                continue
            target = raw_target.strip("<>")
            if (
                not target
                or "://" in target
                or target.startswith(("#", "/", "mailto:"))
            ):
                continue
            if "{{" in target or "<" in target:
                continue
            if not (source.parent / target).exists():
                problems.append(f"{source.relative_to(root)} -> {target}")
    status = "FAIL" if problems else "PASS"
    return Finding("markdown-links", status, "Markdown links", tuple(problems))


def _personal_paths(root: Path) -> Finding:
    problems: list[str] = []
    pattern = re.compile(r"/(?:Users|home)/[^/\s`]+/")
    for source in _markdown_files(root):
        if pattern.search(source.read_text()):
            problems.append(str(source.relative_to(root)))
    status = "FAIL" if problems else "PASS"
    return Finding("personal-paths", status, "Personal absolute paths", tuple(problems))


def _secret_output(root: Path) -> Finding:
    problems: list[str] = []
    shell_sink = re.compile(
        r"\b(?:echo|printf)\b[^\n]*\$\{?[A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET|API_KEY)\b",
        re.I,
    )
    tracing = re.compile(r"(?m)^\s*set\s+-[^\n#]*x")
    for source in list(root.rglob("*.md")) + list(root.rglob("*.sh")):
        if _ignored(root, source):
            continue
        text = source.read_text()
        if shell_sink.search(text) or tracing.search(text):
            problems.append(str(source.relative_to(root)))
    secret_name = re.compile(r"(?:^|_)(?:password|token|secret|api_key)$", re.I)
    for source in root.rglob("*.py"):
        if _ignored(root, source):
            continue
        try:
            tree = ast.parse(source.read_text())
        except SyntaxError:
            continue

        def contains_secret(node: ast.AST) -> bool:
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and secret_name.search(child.id):
                    return True
                if isinstance(child, ast.Subscript):
                    value = child.slice
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        if secret_name.search(value.value):
                            return True
            return False

        unsafe = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and contains_secret(node):
                unsafe = True
                break
            if not isinstance(node, ast.Call):
                continue
            is_print = isinstance(node.func, ast.Name) and node.func.id == "print"
            is_log = (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"logging", "logger", "log"}
            )
            if (is_print or is_log) and contains_secret(node):
                unsafe = True
                break
        if unsafe:
            problems.append(str(source.relative_to(root)))
    status = "FAIL" if problems else "PASS"
    return Finding(
        "secret-output", status, "Secret-safe diagnostics", tuple(sorted(set(problems)))
    )


def run_doctor(
    root: Path,
    installed_paths: InstallPaths | None = None,
    with_pgm: bool = False,
) -> list[Finding]:
    """Run deterministic repository checks and return structured findings."""
    root = root.resolve()
    findings = [
        _skill_descriptions(root),
        _markdown_links(root),
        _personal_paths(root),
        _secret_output(root),
    ]
    if (root / "interfaces/model-routing.json").is_file():
        problems = validate_model_routing(root)
        findings.append(
            Finding(
                "model-routing",
                "FAIL" if problems else "PASS",
                "Model and effort routing",
                tuple(problems),
            )
        )
    if installed_paths is not None:
        details = inspect_install(installed_paths, with_pgm=with_pgm)
        statuses = [item.split(":", 1)[0] for item in details]
        status = (
            "FAIL" if "FAIL" in statuses else "DRIFT" if "DRIFT" in statuses else "PASS"
        )
        findings.append(
            Finding(
                "installed-state",
                status,
                "Installed ownership ledger",
                tuple(item.split(":", 1)[1].strip() for item in details),
            )
        )
    return findings
