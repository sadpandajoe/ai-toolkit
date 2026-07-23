"""Strict validation for public skill, provider, and support interfaces."""

from __future__ import annotations

import json
from pathlib import Path
import re


CLASSIFICATIONS = {"public_router", "public_direct", "internal_support"}
CAPABILITIES = {
    "planning_boundary": True,
    "fresh_subagent": True,
    "parallel_fanout": True,
    "isolated_worktree": True,
    "context_reset": True,
    "recurrence": True,
    "independent_review": False,
    "routed_subagent": True,
}
FALLBACKS = {
    "sequential_execution",
    "self_enforced_read_only_planning",
    "manual_fresh_session",
    "manual_fresh_worktree",
    "manual_reinvocation",
    "skip_and_report_unavailable",
    "source_linked_model_run",
}


def _load(path: Path) -> object:
    return json.loads(path.read_text())


def _skill_name(path: Path) -> str | None:
    text = path.read_text()
    match = re.search(r"^name:\s*([^\s]+)\s*$", text, re.M)
    return match.group(1) if match else None


def _discovered_skills(root: Path) -> dict[str, str]:
    paths = sorted((root / "skills").glob("*/SKILL.md"))
    paths.extend(sorted((root / "extensions").glob("*/skills/*/SKILL.md")))
    discovered: dict[str, str] = {}
    for skill_file in paths:
        name = _skill_name(skill_file)
        if name:
            discovered[name] = skill_file.parent.relative_to(root).as_posix()
    return discovered


def load_skill_interfaces(root: Path) -> list[dict[str, str]]:
    payload = _load(root / "interfaces/skills.json")
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


def validate_skill_interfaces(root: Path) -> list[str]:
    try:
        entries = load_skill_interfaces(root)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    problems: list[str] = []
    declared: dict[str, str] = {}
    for entry in entries:
        name, path_value, classification = (
            entry["name"],
            entry["path"],
            entry["classification"],
        )
        path = Path(path_value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not (root / path / "SKILL.md").is_file()
        ):
            problems.append(f"{name}: invalid skill path {path_value}")
        elif _skill_name(root / path / "SKILL.md") != name:
            problems.append(f"{name}: path frontmatter name mismatch")
        adapter = root / path / "agents/openai.yaml"
        adapter_text = adapter.read_text() if adapter.is_file() else ""
        disabled = bool(
            re.search(r"^\s*allow_implicit_invocation:\s*false\s*$", adapter_text, re.M)
        )
        if classification == "internal_support" and not disabled:
            problems.append(
                f"{name}: internal skill must disable implicit Codex invocation"
            )
        if classification != "internal_support" and not adapter.is_file():
            problems.append(f"{name}: public skill is missing agents/openai.yaml")
        if classification != "internal_support" and disabled:
            problems.append(
                f"{name}: public skill cannot disable implicit Codex invocation"
            )
        declared[name] = path_value
    discovered = _discovered_skills(root)
    for name in sorted(set(discovered) - set(declared)):
        problems.append(f"unclassified skill: {name}")
    for name in sorted(set(declared) - set(discovered)):
        problems.append(f"declared skill is not discovered: {name}")
    for name in sorted(set(discovered) & set(declared)):
        if discovered[name] != declared[name]:
            problems.append(f"{name}: declared path does not match discovered path")
    return problems


def validate_provider_interfaces(root: Path) -> list[str]:
    try:
        payload = _load(root / "interfaces/providers.json")
    except (OSError, json.JSONDecodeError) as error:
        return [str(error)]
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "capabilities", "providers"}
        or payload.get("version") != 1
    ):
        return [
            "interfaces/providers.json must contain exactly version 1, capabilities, and providers"
        ]
    capabilities = payload.get("capabilities")
    providers = payload.get("providers")
    problems: list[str] = []
    try:
        guidance = _load(root / "interfaces/guidance.json")
    except (OSError, json.JSONDecodeError) as error:
        return [f"unable to load interfaces/guidance.json: {error}"]
    if (
        not isinstance(guidance, dict)
        or set(guidance) != {"version", "always_on_rules"}
        or guidance.get("version") != 1
        or not isinstance(guidance.get("always_on_rules"), list)
        or not guidance["always_on_rules"]
        or any(not isinstance(item, str) for item in guidance["always_on_rules"])
        or len(guidance["always_on_rules"]) != len(set(guidance["always_on_rules"]))
    ):
        return ["interfaces/guidance.json does not match schema version 1"]
    always_on_rules: list[str] = guidance["always_on_rules"]
    for rule in always_on_rules:
        path = Path(rule)
        if path.is_absolute() or ".." in path.parts or not (root / path).is_file():
            problems.append(f"always-on guidance rule is missing or unsafe: {rule}")
    declared: dict[str, bool] = {}
    if not isinstance(capabilities, list):
        problems.append("provider capabilities must be a list")
    else:
        for item in capabilities:
            if (
                not isinstance(item, dict)
                or set(item) != {"name", "required"}
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("required"), bool)
            ):
                problems.append("invalid provider capability declaration")
                continue
            if item["name"] in declared:
                problems.append(f"duplicate provider capability: {item['name']}")
            declared[item["name"]] = item["required"]
    if declared != CAPABILITIES:
        problems.append(
            "provider capability vocabulary does not match the version-1 contract"
        )
    if not isinstance(providers, dict) or set(providers) != {"claude", "codex"}:
        problems.append("providers must contain exactly claude and codex")
        return problems
    for provider, value in providers.items():
        if (
            not isinstance(value, dict)
            or set(value) != {"bindings"}
            or not isinstance(value.get("bindings"), dict)
        ):
            problems.append(f"{provider}: invalid bindings container")
            continue
        bindings = value["bindings"]
        if set(bindings) != set(CAPABILITIES):
            problems.append(f"{provider}: capability binding coverage mismatch")
        for capability, binding in bindings.items():
            if (
                capability not in CAPABILITIES
                or not isinstance(binding, dict)
                or set(binding) != {"mode", "document", "fallback"}
            ):
                problems.append(f"{provider}/{capability}: invalid binding shape")
                continue
            mode, document, fallback = (
                binding["mode"],
                binding["document"],
                binding["fallback"],
            )
            if not isinstance(mode, str) or mode not in {
                "native",
                "fallback",
                "unsupported",
            }:
                problems.append(f"{provider}/{capability}: invalid binding mode")
            if not isinstance(document, str):
                problems.append(
                    f"{provider}/{capability}: binding document must be a path"
                )
            else:
                path = Path(document)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not (root / path).is_file()
                ):
                    problems.append(
                        f"{provider}/{capability}: missing or unsafe binding document"
                    )
                elif f"`{capability}`" not in (root / path).read_text():
                    problems.append(
                        f"{provider}/{capability}: binding document omits the capability"
                    )
            if mode == "native" and fallback is not None:
                problems.append(
                    f"{provider}/{capability}: native binding cannot declare fallback"
                )
            if mode == "fallback" and (
                not isinstance(fallback, str) or fallback not in FALLBACKS
            ):
                problems.append(f"{provider}/{capability}: unapproved fallback")
            if mode == "unsupported" and CAPABILITIES.get(capability, True):
                problems.append(
                    f"{provider}/{capability}: required capability cannot be unsupported"
                )
            if mode == "unsupported" and fallback is not None:
                problems.append(
                    f"{provider}/{capability}: unsupported binding cannot declare fallback"
                )
        template = root / (
            "config/CLAUDE.md" if provider == "claude" else "config/AGENTS.md"
        )
        expected_binding = f"{{{{TOOLKIT_DIR}}}}/config/providers/{provider}.md"
        template_text = template.read_text() if template.is_file() else ""
        if expected_binding not in template_text:
            problems.append(
                f"{provider}: installed guidance does not load its provider binding"
            )
        for rule in always_on_rules:
            expected_rule = f"{{{{TOOLKIT_DIR}}}}/{rule}"
            if expected_rule not in template_text:
                problems.append(
                    f"{provider}: installed guidance omits always-on rule {rule}"
                )
    return problems


def validate_support_interface(root: Path) -> list[str]:
    path = root / "interfaces/support.json"
    try:
        payload = _load(path)
    except (OSError, json.JSONDecodeError) as error:
        return [str(error)]
    expected_keys = {
        "version",
        "python",
        "operating_systems",
        "shell",
        "providers",
        "distributions",
        "extensions",
        "extension_distributions",
        "environment_gated",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload.get("version") != 1
    ):
        return ["interfaces/support.json does not match schema version 1"]
    expected = {
        "python": {"minimum": "3.11", "maximum": "3.14"},
        "operating_systems": ["macos-latest", "ubuntu-latest"],
        "shell": "posix-sh",
        "providers": ["claude", "codex"],
        "distributions": ["source-linked", "codex-plugin"],
        "extensions": ["pgm"],
        "extension_distributions": {"pgm": ["source-linked"]},
        "environment_gated": [
            "live-provider-invocation",
            "authenticated-apis",
            "hook-trust-ui",
        ],
    }
    return [
        f"support matrix mismatch: {key}"
        for key, value in expected.items()
        if payload.get(key) != value
    ]
