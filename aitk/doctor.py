"""Repository health checks for portable AI Toolkit content."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import re
from pathlib import Path
import subprocess

from .build import compare_build
from .conformance import validate_contracts
from .interfaces import (
    validate_provider_interfaces,
    validate_skill_interfaces,
    validate_support_interface,
)
from .installer import InstallPaths, inspect_install
from .workflows import (
    extension_manifest_path,
    manifest_path,
    validate_extension_workflows,
    validate_workflows,
)


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    message: str
    details: tuple[str, ...] = ()


CONTENT_DIRECTORIES = ("commands", "config", "docs", "extensions", "rules", "skills")
IGNORED_TREE_PARTS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}
STATE_FILES = (
    "PROJECT.md",
    "PROJECT_ARCHIVE.md",
    "PLAN.md",
    "WATCH.md",
    "CHERRY_PICK.md",
    "CI_FIX.md",
)
PROVIDER_PATTERNS = (
    ("provider template import", re.compile(r"@\{\{TOOLKIT_DIR\}\}")),
    ("EnterPlanMode", re.compile(r"\bEnterPlanMode\b")),
    ("ExitPlanMode", re.compile(r"\bExitPlanMode\b")),
    ("Claude task primitive", re.compile(r"\bTask(?:Create|List|Update)\b")),
    ("provider worktree primitive", re.compile(r"\bEnterWorktree\b")),
    ("provider agent call", re.compile(r"\bAgent\s*\(")),
    (
        "provider workflow runtime",
        re.compile(r"^\s*(?:phase|parallel|agent)\s*\(", re.M),
    ),
    ("provider workflow tool", re.compile(r"\bWorkflow\s+(?:tool|call)\b")),
    (
        "provider lifecycle command",
        re.compile(r"/(?:clear|compact|schedule|loop|goal)\b"),
    ),
    ("Claude model tier", re.compile(r"\bmodel:\s*(?:haiku|sonnet|opus)\b", re.I)),
    ("Claude skill directory", re.compile(r"\bCLAUDE_SKILL_DIR\b")),
    ("Claude plugin cache", re.compile(r"\.claude/plugins/cache/")),
)


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
    problems: list[str] = []
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
            problems.append(
                f"{skill.relative_to(root)}: description lacks positive and negative routing"
            )
    status = "DRIFT" if problems else "PASS"
    return Finding("skill-descriptions", status, "Skill descriptions", tuple(problems))


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


def _provider_portability(root: Path) -> Finding:
    problems: list[str] = []
    directories = [root / "rules", root / "skills"]
    directories.extend((root / "extensions").glob("*/rules"))
    directories.extend((root / "extensions").glob("*/skills"))
    for directory in directories:
        if not directory.is_dir():
            continue
        for source in sorted(directory.rglob("*.md")):
            if _ignored(root, source):
                continue
            text = source.read_text()
            for label, pattern in PROVIDER_PATTERNS:
                if pattern.search(text):
                    problems.append(f"{source.relative_to(root)}: {label}")
    status = "FAIL" if problems else "PASS"
    return Finding(
        "provider-portability", status, "Provider portability", tuple(problems)
    )


def _canonical_ownership(root: Path) -> Finding:
    problems: list[str] = []
    patterns = (
        re.compile(r"commands/[a-z0-9_-]+\.md"),
        re.compile(r"\b(?:the\s+)?command\s+(?:owns|is the source of truth)", re.I),
    )
    for directory in (root / "rules", root / "skills"):
        if not directory.is_dir():
            continue
        for source in sorted(directory.rglob("*.md")):
            if _ignored(root, source):
                continue
            text = source.read_text()
            if any(pattern.search(text) for pattern in patterns):
                problems.append(str(source.relative_to(root)))
    return Finding(
        "canonical-ownership",
        "FAIL" if problems else "PASS",
        "Canonical workflow ownership",
        tuple(problems),
    )


def _source_imports(root: Path) -> Finding:
    problems: list[str] = []
    pattern = re.compile(r"^@\{\{TOOLKIT_DIR\}\}/([^\s#]+)", re.M)
    for source in _markdown_files(root):
        for target in pattern.findall(source.read_text()):
            if not (root / target).exists():
                problems.append(f"{source.relative_to(root)} -> {target}")
    status = "FAIL" if problems else "PASS"
    return Finding("source-imports", status, "Source imports", tuple(problems))


def _readme_inventory(root: Path) -> Finding:
    readme = (root / "README.md").read_text() if (root / "README.md").is_file() else ""
    problems: list[str] = []
    for directory_name in ("commands", "rules"):
        directory = root / directory_name
        if directory.is_dir():
            for source in sorted(directory.glob("*.md")):
                relative = source.relative_to(root).as_posix()
                if (
                    relative not in readme
                    and source.name not in readme
                    and f"/{source.stem}" not in readme
                ):
                    problems.append(relative)
    skills = root / "skills"
    if skills.is_dir():
        for source in sorted(skills.glob("*/SKILL.md")):
            relative = source.parent.relative_to(root).as_posix() + "/"
            if relative not in readme and source.parent.name not in readme:
                problems.append(relative)
    status = "DRIFT" if problems else "PASS"
    return Finding("readme-inventory", status, "README inventory", tuple(problems))


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


def _state_protection(root: Path) -> Finding:
    gitignore = (
        (root / ".gitignore").read_text() if (root / ".gitignore").is_file() else ""
    )
    hook_path = root / "hooks/prevent-project-commit.sh"
    hook = hook_path.read_text() if hook_path.is_file() else ""
    problems = [
        name for name in STATE_FILES if name not in gitignore or name not in hook
    ]
    status = "FAIL" if problems else "PASS"
    return Finding(
        "state-protection", status, "Local state protection", tuple(problems)
    )


def _build_freshness(root: Path) -> Finding:
    extension_names = (
        {path.name for path in (root / "extensions/pgm/commands").glob("*.md")}
        if (root / "extensions/pgm/commands").is_dir()
        else set()
    )
    include_pgm = any(
        (root / "build/commands" / name).is_file() for name in extension_names
    )
    try:
        problems = compare_build(root, include_pgm=include_pgm)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return Finding(
            "build-freshness",
            "FAIL",
            "Generated build freshness",
            (str(error),),
        )
    status = "DRIFT" if problems else "PASS"
    return Finding(
        "build-freshness", status, "Generated build freshness", tuple(problems)
    )


def _provider_package(root: Path) -> Finding:
    manifest_path = root / ".codex-plugin/plugin.json"
    if not manifest_path.is_file():
        return Finding(
            "provider-package",
            "DRIFT",
            "Provider package",
            ("missing .codex-plugin/plugin.json",),
        )
    problems: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as error:
        return Finding(
            "provider-package",
            "FAIL",
            "Provider package",
            (f"invalid plugin JSON: {error}",),
        )
    if not isinstance(manifest, dict):
        return Finding(
            "provider-package",
            "FAIL",
            "Provider package",
            ("plugin manifest must be a JSON object",),
        )
    if manifest.get("name") != "ai-toolkit":
        problems.append("plugin name must be ai-toolkit")
    if not re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", str(manifest.get("version", ""))
    ):
        problems.append("plugin version must be semantic")
    if manifest.get("skills") != "./skills/":
        problems.append("plugin must package ./skills/")
    hooks_path = root / "hooks/hooks.json"
    if not hooks_path.is_file():
        problems.append("missing hooks/hooks.json")
    else:
        try:
            hooks = json.loads(hooks_path.read_text())
            commands = [
                hook.get("command", "")
                for groups in hooks.get("hooks", {}).values()
                for group in groups
                for hook in group.get("hooks", [])
            ]
            if not commands or any(
                "$PLUGIN_ROOT/" not in command for command in commands
            ):
                problems.append(
                    "plugin hooks must resolve scripts through $PLUGIN_ROOT"
                )
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            problems.append(f"invalid hooks JSON: {error}")
    if not (root / "config/AGENTS.md").is_file():
        problems.append("missing Codex guidance template config/AGENTS.md")
    status = "FAIL" if problems else "PASS"
    return Finding("provider-package", status, "Provider package", tuple(problems))


def _syntax(root: Path) -> list[Finding]:
    shell_problems: list[str] = []
    for source in sorted(root.rglob("*.sh")):
        if _ignored(root, source):
            continue
        result = subprocess.run(
            ["bash", "-n", str(source)], capture_output=True, text=True, check=False
        )
        if result.returncode:
            shell_problems.append(
                f"{source.relative_to(root)}: {result.stderr.strip()}"
            )
    for source in (
        root / "install.sh",
        root / "extensions/pgm/install.sh",
        root / "bin/aitk",
    ):
        if not source.is_file():
            continue
        result = subprocess.run(
            ["/bin/sh", "-n", str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            shell_problems.append(
                f"{source.relative_to(root)} (POSIX sh): {result.stderr.strip()}"
            )
    python_problems: list[str] = []
    for source in sorted(root.rglob("*.py")):
        if _ignored(root, source):
            continue
        try:
            ast.parse(source.read_text(), filename=str(source))
        except SyntaxError as error:
            python_problems.append(
                f"{source.relative_to(root)}:{error.lineno}: {error.msg}"
            )
    return [
        Finding(
            "shell-syntax",
            "FAIL" if shell_problems else "PASS",
            "Shell syntax",
            tuple(shell_problems),
        ),
        Finding(
            "python-syntax",
            "FAIL" if python_problems else "PASS",
            "Python syntax",
            tuple(python_problems),
        ),
    ]


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
        _provider_portability(root),
        _canonical_ownership(root),
        _source_imports(root),
        _readme_inventory(root),
        _personal_paths(root),
        _secret_output(root),
        _state_protection(root),
        _build_freshness(root),
    ]
    if (root / ".codex-plugin").exists():
        findings.append(_provider_package(root))
    for filename, check, message, validator in (
        (
            "skills.json",
            "skill-interfaces",
            "Public and internal skill classification",
            validate_skill_interfaces,
        ),
        (
            "providers.json",
            "provider-interfaces",
            "Provider capability bindings",
            validate_provider_interfaces,
        ),
        (
            "support.json",
            "support-interface",
            "Supported release matrix",
            validate_support_interface,
        ),
    ):
        if not (root / "interfaces" / filename).is_file():
            continue
        problems = validator(root)
        findings.append(
            Finding(check, "FAIL" if problems else "PASS", message, tuple(problems))
        )
    if manifest_path(root).is_file():
        workflow_problems = validate_workflows(root)
        findings.append(
            Finding(
                "workflow-interfaces",
                "FAIL" if workflow_problems else "PASS",
                "Canonical workflow interfaces",
                tuple(workflow_problems),
            )
        )
        contract_problems = validate_contracts(root)
        findings.append(
            Finding(
                "behavior-conformance",
                "FAIL" if contract_problems else "PASS",
                "Workflow behavior and resume contracts",
                tuple(contract_problems),
            )
        )
    if extension_manifest_path(root, "pgm").is_file():
        extension_problems = validate_extension_workflows(root, "pgm")
        findings.append(
            Finding(
                "pgm-workflow-interfaces",
                "FAIL" if extension_problems else "PASS",
                "Optional PGM workflow interfaces",
                tuple(extension_problems),
            )
        )
    findings.extend(_syntax(root))
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
