"""Canonical workflow manifest loading.

Also the router's data: each workflow's contract from
`interfaces/contracts.json`, the skill manifest in `interfaces/skills.json`,
and the skills a reference links to, which `bin/aitk list --details --json`
prints. Loading fails on a malformed manifest; nothing else re-validates it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class WorkflowDependency:
    name: str
    resource: Path


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
    # A command-only entry runs one `bin/aitk` command and has no reference.
    command: str = ""

    @property
    def reference(self) -> Path:
        return self.reference_root / f"{self.name}.md"


COMMAND_PATTERN = re.compile(r"bin/aitk [a-z]+(?:-[a-z]+)*(?: [^\n]*)?")


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
        if not isinstance(item, dict) or set(item) - {"command"} != expected_item:
            raise ValueError(
                f"{path}: every workflow must contain exactly {sorted(expected_item)}"
                " and, for a command-only entry, command"
            )
        command = item.get("command", "")
        if "command" in item and (
            not isinstance(command, str) or COMMAND_PATTERN.fullmatch(command) is None
        ):
            raise ValueError(
                f"{path}: {item.get('name')!r} command must be one `bin/aitk <subcommand>` line"
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
        if any(workflow.name == name for workflow in workflows):
            raise ValueError(f"{path}: duplicate workflow name {name}")
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
                command=command,
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


CLASSIFICATIONS = {"public_router", "public_direct", "internal_support"}


def load_skill_interfaces(root: Path) -> list[dict[str, str]]:
    """Read interfaces/skills.json; a malformed or unsafe entry raises."""
    payload = json.loads((root / "interfaces/skills.json").read_text())
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "skills"}
        or payload.get("version") != 1
        or not isinstance(payload.get("skills"), list)
    ):
        raise ValueError(
            "interfaces/skills.json must contain exactly version 1 and skills"
        )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in payload["skills"]:
        if not isinstance(entry, dict) or set(entry) != {
            "name",
            "path",
            "classification",
        }:
            raise ValueError(
                "every skill interface must contain exactly name, path, and classification"
            )
        name = entry["name"]
        path_value = entry["path"]
        classification = entry["classification"]
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None
            or name in seen
        ):
            raise ValueError(f"invalid or duplicate skill name: {name}")
        if not isinstance(classification, str) or classification not in CLASSIFICATIONS:
            raise ValueError(f"{name}: invalid skill classification {classification}")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"{name}: invalid skill path {path_value}")
        path = Path(path_value)
        if path.is_absolute() or ".." in path.parts or path == Path("."):
            raise ValueError(f"{name}: unsafe skill path {path_value}")
        seen.add(name)
        result.append(entry)
    return result


def _skill_roots(repository: Path) -> list[tuple[Path, str]]:
    """Each skill's resolved directory and name from interfaces/skills.json, deepest first."""
    roots = [
        ((repository / entry["path"]).resolve(strict=False), entry["name"])
        for entry in load_skill_interfaces(repository)
    ]
    return sorted(roots, key=lambda item: len(item[0].parts), reverse=True)


def workflow_dependency_resources(
    root: Path, workflow: Workflow
) -> tuple[WorkflowDependency, ...]:
    """Resolve every exact linked skill resource through the skill manifest."""
    if workflow.command:
        return ()
    repository = root.resolve()
    reference = (repository / workflow.reference).resolve(strict=False)
    if not reference.is_relative_to(repository) or not reference.is_file():
        raise ValueError(f"{workflow.name}: workflow reference is missing or unsafe")
    skill_roots = _skill_roots(repository)
    dependencies: set[tuple[str, Path]] = set()
    for raw in re.findall(r"(?<!!)\[[^]]*\]\(([^)]+)\)", reference.read_text()):
        target_value = raw.split("#", 1)[0].strip().strip("<>")
        if (
            not target_value
            or "://" in target_value
            or target_value.startswith(("#", "/", "mailto:"))
        ):
            continue
        target = (reference.parent / target_value).resolve(strict=False)
        if not target.is_relative_to(repository):
            raise ValueError(f"{workflow.name}: dependency link escapes repository")
        skill_scoped = "skills" in target.relative_to(repository).parts
        if not target.is_file():
            raise ValueError(
                f"{workflow.name}: dependency link target is missing or not a file: {target_value}"
            )
        matched = next(
            (
                name
                for skill_root, name in skill_roots
                if target == skill_root or target.is_relative_to(skill_root)
            ),
            None,
        )
        if skill_scoped and matched is None:
            raise ValueError(
                f"{workflow.name}: dependency link is not classified: {target_value}"
            )
        if matched is not None and matched != workflow.owner_skill:
            dependencies.add((matched, target.relative_to(repository)))

    unfenced = re.sub(r"(?ms)^```.*?^```\s*$", "", reference.read_text())
    inline_tokens = set(re.findall(r"(?<!`)`([^`\n]+)`(?!`)", unfenced))
    for skill_root, name in skill_roots:
        if name == workflow.owner_skill:
            continue
        for inline_reference in inline_tokens:
            suffix: str | None = None
            if inline_reference == name and "-" in name:
                suffix = "SKILL.md"
            elif inline_reference in {
                f"{name}/",
                f"skills/{name}",
                f"skills/{name}/",
            }:
                suffix = "SKILL.md"
            elif inline_reference.startswith(f"{name}/"):
                suffix = inline_reference[len(name) + 1 :]
            elif inline_reference.startswith(f"skills/{name}/"):
                suffix = inline_reference[len(f"skills/{name}/") :]
            if suffix is None:
                continue
            if not suffix or suffix.endswith("/"):
                suffix += "SKILL.md"
            if re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", suffix) is None:
                continue
            resource = (skill_root / suffix).resolve(strict=False)
            if not resource.is_relative_to(skill_root) or not resource.is_file():
                raise ValueError(
                    f"{workflow.name}: named skill resource is missing or unsafe: {inline_reference}"
                )
            dependencies.add((name, resource.relative_to(repository)))
    return tuple(
        WorkflowDependency(name=name, resource=resource)
        for name, resource in sorted(
            dependencies, key=lambda item: (item[0], item[1].as_posix())
        )
    )


def workflow_dependencies(root: Path, workflow: Workflow) -> tuple[str, ...]:
    """Return stable logical skill names required by a workflow."""
    return tuple(
        sorted(
            {
                dependency.name
                for dependency in workflow_dependency_resources(root, workflow)
            }
        )
    )


def load_contract_document(root: Path) -> dict[str, object]:
    """Load the strict version-2 contract document."""
    path = root / "interfaces/contracts.json"
    payload = json.loads(path.read_text())
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "vocabularies", "contracts"}
        or payload.get("version") != 2
    ):
        raise ValueError(
            "interfaces/contracts.json must use version 2 with exactly vocabularies and contracts; version 1 is no longer supported"
        )
    if not isinstance(payload.get("vocabularies"), dict) or not isinstance(
        payload.get("contracts"), list
    ):
        raise ValueError("interfaces/contracts.json has invalid version-2 containers")
    return payload


def contracts_by_name(root: Path) -> dict[str, dict[str, object]]:
    payload = load_contract_document(root)
    contracts: dict[str, dict[str, object]] = {}
    for value in payload["contracts"]:  # type: ignore[index]
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            raise ValueError("every workflow contract must be an object with a name")
        name = value["name"]
        if name in contracts:
            raise ValueError(f"duplicate workflow contract: {name}")
        contracts[name] = value
    return contracts
