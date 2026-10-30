#!/usr/bin/env python3
"""Repository checks that need no toolkit runtime.

Run from anywhere: `python3 scripts/check.py`. It fails on what a reader or an
installed plugin would trip over:

- markdown links that do not resolve;
- SKILL.md frontmatter other than exactly `name` and `description`;
- plugin manifests that do not parse or name a path that does not exist,
  and hook commands that name a missing script;
- personal absolute paths in shipped markdown;
- secrets echoed by shell or printed by Python.

Exit 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIRECTORIES = ("config", "docs", "extensions", "rules", "skills")
IGNORED_PARTS = {".git", ".venv", "build", "dist", "node_modules", "site-packages", "venv", "__pycache__"}
PLUGIN_MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/marketplace.json")


def ignored(root: Path, path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.relative_to(root).parts)


def markdown_files(root: Path) -> list[Path]:
    files = [root / name for name in ("README.md", "AGENTS.md") if (root / name).is_file()]
    for name in CONTENT_DIRECTORIES:
        directory = root / name
        if directory.is_dir():
            files.extend(path for path in sorted(directory.rglob("*.md")) if not ignored(root, path))
    return files


def frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def check_skill_frontmatter(root: Path) -> list[str]:
    problems = []
    skills = sorted([*root.glob("skills/*/SKILL.md"), *root.glob("extensions/*/skills/*/SKILL.md")])
    for skill in skills:
        name = skill.relative_to(root)
        fields = frontmatter(skill.read_text())
        if fields is None:
            problems.append(f"{name}: no frontmatter")
            continue
        if set(fields) != {"name", "description"}:
            problems.append(f"{name}: fields are {sorted(fields)}, want ['description', 'name']")
        elif not fields["name"] or not fields["description"]:
            problems.append(f"{name}: empty name or description")
    return problems


def check_markdown_links(root: Path) -> list[str]:
    problems = []
    link = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")
    for source in markdown_files(root):
        for match in link.finditer(source.read_text()):
            target = match.group(1).split("#", 1)[0].strip()
            if (
                not target
                or target.startswith(("<", "#", "/", "mailto:"))
                or "://" in target
                or "{{" in target
            ):
                continue
            if not (source.parent / target).exists():
                problems.append(f"{source.relative_to(root)} -> {target}")
    return problems


def manifest_paths(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("./") else []
    if isinstance(value, list):
        return [path for item in value for path in manifest_paths(item)]
    return []


def check_plugin_manifests(root: Path) -> list[str]:
    problems = []
    for relative in PLUGIN_MANIFESTS:
        path = root / relative
        if not path.is_file():
            problems.append(f"{relative}: missing")
            continue
        try:
            manifest = json.loads(path.read_text())
        except ValueError as error:
            problems.append(f"{relative}: not JSON ({error})")
            continue
        for key in ("skills", "agents", "hooks"):
            for declared in manifest_paths(manifest.get(key)):
                if not (root / declared).exists():
                    problems.append(f"{relative}: {key} path {declared} does not exist")
    hooks = root / "hooks" / "hooks.json"
    if hooks.is_file():
        for script in sorted(set(re.findall(r"hooks/[\w.-]+\.sh", hooks.read_text()))):
            if not (root / script).is_file():
                problems.append(f"hooks/hooks.json: {script} does not exist")
    return problems


def check_personal_paths(root: Path) -> list[str]:
    pattern = re.compile(r"/(?:Users|home)/[^/\s`]+/")
    return [str(path.relative_to(root)) for path in markdown_files(root) if pattern.search(path.read_text())]


SECRET_NAME = re.compile(r"(?:^|_)(?:password|token|secret|api_key)$", re.I)


def mentions_secret(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and SECRET_NAME.search(child.id):
            return True
        if (
            isinstance(child, ast.Subscript)
            and isinstance(child.slice, ast.Constant)
            and isinstance(child.slice.value, str)
            and SECRET_NAME.search(child.slice.value)
        ):
            return True
    return False


def python_leaks_secret(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and mentions_secret(node):
            return True
        if not isinstance(node, ast.Call):
            continue
        is_print = isinstance(node.func, ast.Name) and node.func.id == "print"
        is_log = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"logging", "logger", "log"}
        )
        if (is_print or is_log) and mentions_secret(node):
            return True
    return False


def check_secret_output(root: Path) -> list[str]:
    problems = set()
    shell_sink = re.compile(r"\b(?:echo|printf)\b[^\n]*\$\{?[A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET|API_KEY)\b", re.I)
    tracing = re.compile(r"(?m)^\s*set\s+-[^\n#]*x")
    for source in [*root.rglob("*.md"), *root.rglob("*.sh")]:
        if not ignored(root, source):
            text = source.read_text()
            if shell_sink.search(text) or tracing.search(text):
                problems.add(str(source.relative_to(root)))
    for source in root.rglob("*.py"):
        if ignored(root, source):
            continue
        try:
            tree = ast.parse(source.read_text())
        except SyntaxError:
            continue
        if python_leaks_secret(tree):
            problems.add(str(source.relative_to(root)))
    return sorted(problems)


CHECKS = (
    ("skill frontmatter", check_skill_frontmatter),
    ("markdown links", check_markdown_links),
    ("plugin manifests", check_plugin_manifests),
    ("personal paths", check_personal_paths),
    ("secret output", check_secret_output),
)


def main(root: Path = ROOT) -> int:
    failed = False
    for label, check in CHECKS:
        problems = check(root)
        print(f"{'FAIL' if problems else 'PASS'}  {label}")
        for problem in problems:
            print(f"      {problem}")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT))
