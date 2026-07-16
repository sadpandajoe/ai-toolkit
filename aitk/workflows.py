"""Canonical workflow manifest and provider adapter generation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Workflow:
    name: str
    summary: str
    arguments: str
    rules: tuple[str, ...]
    triggers: tuple[str, ...]
    owner_skill: str
    execution_class: str
    reference_root: Path = Path("skills/workflows/references")

    @property
    def reference(self) -> Path:
        return self.reference_root / f"{self.name}.md"


def manifest_path(root: Path) -> Path:
    return root / "interfaces/workflows.json"


def extension_manifest_path(root: Path, extension: str) -> Path:
    return root / "extensions" / extension / "interfaces/workflows.json"


def _load_manifest(path: Path) -> list[Workflow]:
    payload = json.loads(path.read_text())
    expected = {"version", "skill", "reference_root", "workflows"}
    if (
        set(payload) != expected
        or payload.get("version") != 1
        or not isinstance(payload.get("workflows"), list)
    ):
        raise ValueError(
            f"{path} must contain exactly version 1, skill, reference_root, and workflows"
        )
    owner_skill = payload.get("skill")
    reference_value = payload.get("reference_root")
    if not isinstance(owner_skill, str) or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", owner_skill
    ):
        raise ValueError(f"{path}: invalid owner skill")
    if not isinstance(reference_value, str):
        raise ValueError(f"{path}: reference_root must be a string")
    reference_root = Path(reference_value)
    if reference_root.is_absolute() or ".." in reference_root.parts:
        raise ValueError(f"{path}: reference_root must stay inside the repository")
    workflows: list[Workflow] = []
    for item in payload["workflows"]:
        expected_item = {
            "name",
            "summary",
            "arguments",
            "rules",
            "triggers",
            "execution_class",
        }
        if not isinstance(item, dict) or set(item) != expected_item:
            raise ValueError(
                f"{path}: every workflow must contain exactly {sorted(expected_item)}"
            )
        name = item["name"]
        summary = item["summary"]
        arguments = item["arguments"]
        rules = item["rules"]
        triggers = item["triggers"]
        execution_class = item["execution_class"]
        if (
            not isinstance(name, str)
            or not isinstance(summary, str)
            or not isinstance(arguments, str)
            or not isinstance(execution_class, str)
            or not isinstance(rules, list)
            or not all(isinstance(rule, str) for rule in rules)
            or len(rules) != len(set(rules))
            or not isinstance(triggers, list)
            or not all(isinstance(trigger, str) for trigger in triggers)
            or len(triggers) != len(set(triggers))
        ):
            raise ValueError(
                f"{path}: workflow fields have invalid types or duplicates"
            )
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None:
            raise ValueError(f"{path}: unsafe workflow name {name!r}")
        for rule in rules:
            rule_path = Path(rule)
            if not rule or rule_path.is_absolute() or ".." in rule_path.parts:
                raise ValueError(f"{path}: unsafe workflow rule path {rule!r}")
        workflows.append(
            Workflow(
                name=name,
                summary=summary,
                arguments=arguments,
                rules=tuple(rules),
                triggers=tuple(triggers),
                owner_skill=owner_skill,
                execution_class=execution_class,
                reference_root=reference_root,
            )
        )
    return workflows


def load_extension_workflows(root: Path, extension: str) -> list[Workflow]:
    return _load_manifest(extension_manifest_path(root, extension))


def load_workflows(root: Path, include_pgm: bool = False) -> list[Workflow]:
    workflows = _load_manifest(manifest_path(root))
    if include_pgm and extension_manifest_path(root, "pgm").is_file():
        workflows.extend(load_extension_workflows(root, "pgm"))
    return workflows


def _adapter(workflow: Workflow) -> str:
    lines = [
        "---",
        f"description: {json.dumps(workflow.summary)}",
    ]
    if workflow.arguments:
        lines.append(f"argument-hint: {json.dumps(workflow.arguments)}")
    lines.extend(["---", f"# /{workflow.name}", ""])
    lines.extend(f"@{{{{TOOLKIT_DIR}}}}/{rule}" for rule in workflow.rules)
    lines.append(f"@{{{{TOOLKIT_DIR}}}}/{workflow.reference.as_posix()}")
    return "\n".join(lines) + "\n"


def command_adapters(root: Path) -> dict[Path, str]:
    return {
        Path("commands") / f"{workflow.name}.md": _adapter(workflow)
        for workflow in load_workflows(root)
    }


def extension_command_adapters(root: Path, extension: str) -> dict[Path, str]:
    return {
        Path("extensions") / extension / "commands" / f"{workflow.name}.md": _adapter(
            workflow
        )
        for workflow in load_extension_workflows(root, extension)
    }


def _validate_workflows(
    root: Path, workflows: list[Workflow], reject_orphans: bool
) -> list[str]:
    problems: list[str] = []
    names: set[str] = set()
    for workflow in workflows:
        if workflow.name in names:
            problems.append(f"duplicate workflow name: {workflow.name}")
        names.add(workflow.name)
        if not workflow.summary.strip():
            problems.append(f"{workflow.name}: missing summary")
        if workflow.execution_class not in {"single_run", "durable"}:
            problems.append(
                f"{workflow.name}: invalid execution_class {workflow.execution_class}"
            )
        if not workflow.triggers:
            problems.append(f"{workflow.name}: missing routing triggers")
        if not (root / workflow.reference).is_file():
            problems.append(f"{workflow.name}: missing {workflow.reference.as_posix()}")
        for rule in workflow.rules:
            if not (root / rule).is_file():
                problems.append(f"{workflow.name}: missing {rule}")

    if reject_orphans and workflows:
        reference_dir = root / workflows[0].reference_root
        references = (
            {path.stem for path in reference_dir.glob("*.md")}
            if reference_dir.is_dir()
            else set()
        )
        for orphan in sorted(references - names):
            problems.append(f"unregistered workflow reference: {orphan}")
    return problems


def validate_workflows(root: Path) -> list[str]:
    try:
        workflows = load_workflows(root)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    return _validate_workflows(root, workflows, reject_orphans=True)


def validate_extension_workflows(root: Path, extension: str) -> list[str]:
    try:
        workflows = load_extension_workflows(root, extension)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    # Extension reference roots may also hold explicitly linked support material
    # (for example PGM audience formatting) that is not itself a workflow.
    problems = _validate_workflows(root, workflows, reject_orphans=False)
    try:
        core_names = {workflow.name for workflow in load_workflows(root)}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        problems.append(str(error))
    else:
        for duplicate in sorted(core_names & {workflow.name for workflow in workflows}):
            problems.append(
                f"extension workflow collides with core workflow: {duplicate}"
            )
    return problems
