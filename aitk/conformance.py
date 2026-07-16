"""Behavioral contracts and deterministic workflow routing."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .interfaces import load_skill_interfaces
from .workflows import Workflow, load_workflows


@dataclass(frozen=True)
class RouteMatch:
    workflow: Workflow
    trigger: str
    score: tuple[int, int]


@dataclass(frozen=True)
class WorkflowDependency:
    name: str
    resource: Path


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _ordered_tokens_match(trigger: str, request: str) -> bool:
    request_tokens = iter(request.split())
    return all(
        any(token == candidate for candidate in request_tokens)
        for token in trigger.split()
    )


def route_workflow(
    root: Path, request: str, include_pgm: bool = False
) -> RouteMatch | None:
    explicit = re.match(
        r"^\s*\$(workflows|pgm)\s+([a-z0-9]+(?:-[a-z0-9]+)*)\b", request, re.I
    )
    if explicit:
        owner, name = explicit.groups()
        for workflow in load_workflows(root, include_pgm=include_pgm):
            if workflow.owner_skill == owner.lower() and workflow.name == name.lower():
                return RouteMatch(
                    workflow=workflow,
                    trigger=f"${owner.lower()} {name.lower()}",
                    score=(10_000, 10_000),
                )
        return None
    normalized = _normalize(request)
    matches: list[RouteMatch] = []
    for workflow in load_workflows(root, include_pgm=include_pgm):
        for trigger in workflow.triggers:
            normalized_trigger = _normalize(trigger)
            if normalized_trigger and _ordered_tokens_match(
                normalized_trigger, normalized
            ):
                matches.append(
                    RouteMatch(
                        workflow=workflow,
                        trigger=trigger,
                        score=(
                            len(normalized_trigger.split()),
                            len(normalized_trigger),
                        ),
                    )
                )
    if not matches:
        return None
    ordered = sorted(
        matches, key=lambda match: (match.score, match.workflow.name), reverse=True
    )
    best = ordered[0]
    if any(
        match.workflow.name != best.workflow.name and match.score == best.score
        for match in ordered[1:]
    ):
        return None
    return best


def workflow_dependency_resources(
    root: Path, workflow: Workflow
) -> tuple[WorkflowDependency, ...]:
    """Resolve every exact linked skill resource through the skill manifest."""
    repository = root.resolve()
    reference = (repository / workflow.reference).resolve(strict=False)
    if not reference.is_relative_to(repository) or not reference.is_file():
        raise ValueError(f"{workflow.name}: workflow reference is missing or unsafe")
    skill_roots = sorted(
        (
            ((repository / entry["path"]).resolve(strict=False), entry["name"])
            for entry in load_skill_interfaces(repository)
        ),
        key=lambda item: len(item[0].parts),
        reverse=True,
    )
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


CONTRACT_KEYS = {
    "name",
    "effect",
    "authorization",
    "state",
    "resumable",
    "phases",
    "transitions",
    "checkpoint",
    "resume_from",
    "idempotency_keys",
    "verification",
    "reporting",
    "required_sections",
    "forbidden_actions",
}
VOCABULARIES = {
    "gates": {
        "publish-explicit",
        "destructive-confirmation",
        "production-refusal",
        "failed-preflight-stop",
        "verification",
        "review",
        "pii-scrub",
    },
    "evidence": {
        "targeted-tests",
        "repository-gate",
        "external-check",
        "manual-evidence",
        "static-validation",
        "not-applicable",
    },
    "policies": {
        "publish-without-authorization",
        "destructive-without-confirmation",
        "production-mutation",
        "secret-output",
        "effect-after-failed-preflight",
        "duplicate-effect",
    },
}


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


def contract_digest(contract: dict[str, object]) -> str:
    canonical = json.dumps(
        contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _unique_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(value) == len(set(value))
    )


EFFECTS = {"read_only", "local_mutation", "git_mutation", "external_effect"}
EFFECTFUL_EXECUTABLE = re.compile(
    r"(?m)^\s*(?:\$\s+)?(?:"
    r"git\s+(?:add|commit|push|merge|rebase)\b|"
    r"(?:rm|mv)\s+|"
    r"gh\s+pr\s+(?:create|comment|review|merge)\b|"
    r"curl\b[^\n]*\s-X\s*(?:POST|PUT|PATCH|DELETE)\b|"
    r"(?:Path\([^\n]+\)|[A-Za-z_][A-Za-z0-9_.]*)\."
    r"(?:write_text|write_bytes|unlink|rename|mkdir|rmdir)\s*\(|"
    r"(?:os|shutil)\.replace\s*\(|Path\([^\n]+\)\.replace\s*\(|"
    r"open\([^\n]+[, ]\s*['\"](?:w|a|x|r\+|w\+|a\+)"
    r")"
)


def _executable_surfaces(root: Path, reference: Path) -> tuple[tuple[str, str], ...]:
    """Return bounded executable text from fenced blocks and named scripts."""
    text = reference.read_text()
    surfaces: list[tuple[str, str]] = []
    executable_languages = {
        "",
        "bash",
        "console",
        "py",
        "python",
        "sh",
        "shell",
        "zsh",
    }
    for index, match in enumerate(
        re.finditer(r"(?ms)^```([^\n`]*)\n(.*?)^```\s*$", text), start=1
    ):
        language_value = match.group(1).strip()
        language = language_value.split(maxsplit=1)[0].lower() if language_value else ""
        if language in executable_languages:
            surfaces.append((f"{reference.name}:fence-{index}", match.group(2)))

    script_values = set(
        re.findall(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_./<>-]+\.(?:py|sh))\b", text)
    )
    repository = root.resolve()
    for raw in sorted(script_values):
        normalized = raw.replace("<toolkit-root>/", "")
        candidate = Path(normalized)
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        paths = (repository / candidate, reference.parent / candidate)
        script = next((path for path in paths if path.is_file()), None)
        if script is None or not script.resolve().is_relative_to(repository):
            continue
        surfaces.append((str(script.relative_to(repository)), script.read_text()))
    return tuple(surfaces)


def _validate_durable_runtime(root: Path) -> list[str]:
    problems: list[str] = []
    rule = root / "rules/durable-workflows.md"
    if not rule.is_file():
        return ["durable runtime rule is missing"]
    text = rule.read_text()
    for phrase in (
        "checkpoint init",
        "checkpoint advance",
        "checkpoint reserve",
        "checkpoint apply",
        "provider_idempotency",
        "artifact_lookup",
        "manual_stop",
        "Complete the contract's authorization and preflight gates before any effect.",
        "never retry blindly",
    ):
        if phrase not in text:
            problems.append(
                f"durable runtime rule is missing semantic clause: {phrase}"
            )

    template = root / "skills/reporting/templates/workflow-checkpoint.md"
    if not template.is_file():
        return problems + ["canonical checkpoint template is missing"]
    content = template.read_text()
    begin = "<!-- aitk-checkpoint:v1 -->"
    end = "<!-- /aitk-checkpoint -->"
    if content.count(begin) != 1 or content.count(end) != 1:
        return problems + ["canonical checkpoint template must contain one marker pair"]
    try:
        body = content.split(begin + "\n", 1)[1].split("\n" + end, 1)[0]
        rendered = (
            body.replace("{{workflow}}", "workflow")
            .replace("{{contract_digest}}", "sha256:" + "0" * 64)
            .replace("{{phase}}", "phase")
        )
        payload = json.loads(rendered)
    except (IndexError, json.JSONDecodeError) as error:
        return problems + [f"canonical checkpoint template is malformed: {error}"]
    expected = {
        "schema_version": 1,
        "workflow": "workflow",
        "contract_schema_version": 2,
        "contract_digest": "sha256:" + "0" * 64,
        "phase": "phase",
        "generation": 0,
        "effects": [],
    }
    if payload != expected:
        problems.append("canonical checkpoint template fields do not match schema v1")
    if (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        != rendered
    ):
        problems.append("canonical checkpoint template JSON is not canonical")
    return problems


def _validate_contract(
    root: Path,
    name: str,
    contract: dict[str, object],
    execution_class: str,
    reference: Path,
    rules: tuple[str, ...],
    vocabularies: dict[str, set[str]],
) -> list[str]:
    problems: list[str] = []
    if set(contract) != CONTRACT_KEYS:
        missing = sorted(CONTRACT_KEYS - set(contract))
        extra = sorted(set(contract) - CONTRACT_KEYS)
        problems.append(f"{name}: contract keys missing={missing} extra={extra}")
        return problems

    effect = contract["effect"]
    if not isinstance(effect, str) or effect not in EFFECTS:
        problems.append(f"{name}: invalid effect {effect}")
    else:
        markers = re.findall(
            r"(?m)^## Effect Boundary\s*$\n\nEffect: `([^`]+)`\.\s*$",
            reference.read_text(),
        )
        if markers != [effect]:
            problems.append(
                f"{name}: effect boundary marker does not match its contract"
            )
        if effect == "read_only":
            for label, surface in _executable_surfaces(root, reference):
                if EFFECTFUL_EXECUTABLE.search(surface):
                    problems.append(
                        f"{name}: read-only executable surface is effectful: {label}"
                    )

    authorization = contract["authorization"]
    if not isinstance(authorization, dict) or set(authorization) != {"mode", "gates"}:
        problems.append(f"{name}: authorization must contain exactly mode and gates")
    else:
        mode = authorization["mode"]
        gates = authorization["gates"]
        if not isinstance(mode, str) or mode not in {"none", "invocation", "explicit"}:
            problems.append(f"{name}: invalid authorization mode {mode}")
        if not _unique_strings(gates) or any(
            gate not in vocabularies["gates"] for gate in gates
        ):
            problems.append(f"{name}: invalid authorization gates")
        if effect != "read_only" and mode == "none":
            problems.append(
                f"{name}: mutating/effectful contract requires authorization"
            )
        if effect == "read_only" and mode != "none":
            problems.append(
                f"{name}: read-only contract must use authorization mode none"
            )
        if effect == "external_effect":
            marker = re.search(
                r"(?m)^Authorization mode: `(none|invocation|explicit)`\.",
                reference.read_text(),
            )
            if marker is None or marker.group(1) != mode:
                problems.append(
                    f"{name}: external-effect authorization marker does not match its contract"
                )

    state = contract["state"]
    artifacts: list[object] = []
    if (
        not isinstance(state, dict)
        or set(state) != {"artifacts"}
        or not isinstance(state.get("artifacts"), list)
    ):
        problems.append(f"{name}: state must contain exactly an artifacts list")
    else:
        artifacts = state["artifacts"]
        if not _unique_strings(artifacts) or any(
            not _safe_relative(value) for value in artifacts
        ):
            problems.append(
                f"{name}: state artifacts must be unique repository-relative paths"
            )

    phases = contract["phases"]
    transitions = contract["transitions"]
    resume_from = contract["resume_from"]
    if (
        not _unique_strings(phases)
        or not phases
        or any(phase.startswith("$") for phase in phases)
    ):
        problems.append(f"{name}: phases must be unique non-sentinel strings")
        phases = []
    if not _unique_strings(resume_from) or any(
        phase not in phases for phase in resume_from
    ):
        problems.append(f"{name}: resume_from contains invalid phases")
        resume_from = []
    edges: list[tuple[str, str]] = []
    allowed_nodes = set(phases) | {"$start", "$terminal"}
    if not isinstance(transitions, list):
        problems.append(f"{name}: transitions must be a list")
    else:
        for edge in transitions:
            if not isinstance(edge, dict) or set(edge) != {"from", "to"}:
                problems.append(f"{name}: transition must contain exactly from and to")
                continue
            source, target = edge["from"], edge["to"]
            if (
                not isinstance(source, str)
                or not isinstance(target, str)
                or source not in allowed_nodes
                or target not in allowed_nodes
                or source == "$terminal"
                or target == "$start"
            ):
                problems.append(f"{name}: illegal transition {source!r} -> {target!r}")
                continue
            edges.append((source, target))
    if len(edges) != len(set(edges)):
        problems.append(f"{name}: transition graph contains duplicate edges")
    reachable = {"$start"}
    changed = True
    while changed:
        changed = False
        for source, target in edges:
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    if set(phases) - reachable or "$terminal" not in reachable:
        problems.append(f"{name}: transition graph has unreachable phase or terminal")

    resumable = contract["resumable"]
    checkpoint = contract["checkpoint"]
    if not isinstance(resumable, bool):
        problems.append(f"{name}: resumable must be boolean")
    elif execution_class == "durable":
        if not resumable or set(resume_from) != set(phases):
            problems.append(f"{name}: durable workflow must resume from every phase")
        if not isinstance(checkpoint, dict) or set(checkpoint) != {
            "template",
            "artifact",
        }:
            problems.append(
                f"{name}: durable checkpoint must contain template and artifact"
            )
        else:
            template, artifact = checkpoint["template"], checkpoint["artifact"]
            if not _safe_relative(template) or not (root / str(template)).is_file():
                problems.append(f"{name}: checkpoint template is missing or unsafe")
            if artifact not in artifacts:
                problems.append(f"{name}: checkpoint artifact must be a state artifact")
            if (
                template != "skills/reporting/templates/workflow-checkpoint.md"
                or artifact != "PROJECT.md"
            ):
                problems.append(
                    f"{name}: durable workflow must use the canonical checkpoint template and PROJECT.md artifact"
                )
        if "rules/durable-workflows.md" not in rules:
            problems.append(
                f"{name}: durable workflow must load rules/durable-workflows.md"
            )
        reference_text = reference.read_text()
        if (
            "## Durable Runtime Contract" not in reference_text
            or re.search(r"bin/aitk\s+checkpoint", reference_text) is None
            or f"`{name}`" not in reference_text
        ):
            problems.append(
                f"{name}: durable reference is missing its runtime contract binding"
            )
        if "extensions/pgm/rules/pgm.md" in rules and (
            "pgm-preflight" not in reference_text
            or re.search(
                r"stop before collection\s+with zero report\s+effects",
                reference_text,
            )
            is None
        ):
            problems.append(
                f"{name}: PGM reference is missing its fail-closed preflight boundary"
            )
    elif execution_class == "single_run":
        expected_edges = [
            {"from": "$start", "to": "run"},
            {"from": "run", "to": "$terminal"},
        ]
        if (
            resumable
            or checkpoint is not None
            or resume_from
            or phases != ["run"]
            or transitions != expected_edges
        ):
            problems.append(
                f"{name}: single_run contract must use the canonical run graph"
            )
    else:
        problems.append(f"{name}: unknown execution class {execution_class}")

    keys = contract["idempotency_keys"]
    if not isinstance(keys, list):
        problems.append(f"{name}: idempotency_keys must be a list")
    else:
        seen: set[str] = set()
        for item in keys:
            if not isinstance(item, dict) or set(item) != {"key", "strategy"}:
                problems.append(f"{name}: invalid idempotency key object")
                continue
            key = item["key"]
            strategy = item["strategy"]
            if not isinstance(key, str) or not key:
                problems.append(f"{name}: invalid idempotency key or strategy")
                continue
            if (
                not isinstance(strategy, str)
                or key in seen
                or strategy
                not in {
                    "artifact_lookup",
                    "provider_idempotency",
                    "manual_stop",
                }
            ):
                problems.append(f"{name}: invalid idempotency key or strategy")
            seen.add(key)
        if effect != "read_only" and not keys:
            problems.append(
                f"{name}: mutating/effectful contract requires an idempotency key"
            )
        if effect == "read_only" and keys:
            problems.append(f"{name}: read-only contract cannot declare effect keys")
        strategies = {
            item.get("strategy")
            for item in keys
            if isinstance(item, dict) and isinstance(item.get("strategy"), str)
        }
        if (
            execution_class == "durable"
            and effect in {"local_mutation", "git_mutation"}
            and "artifact_lookup" not in strategies
        ):
            problems.append(
                f"{name}: durable local/git mutation requires artifact_lookup reconciliation"
            )
        if (
            execution_class == "durable"
            and effect == "external_effect"
            and not strategies.intersection({"provider_idempotency", "manual_stop"})
        ):
            problems.append(
                f"{name}: durable external effect requires provider or manual reconciliation"
            )

    verification = contract["verification"]
    if not isinstance(verification, dict) or set(verification) != {
        "strength",
        "evidence",
    }:
        problems.append(f"{name}: verification must contain strength and evidence")
    else:
        evidence = verification["evidence"]
        if (
            not isinstance(verification["strength"], str)
            or verification["strength"] not in {"none", "targeted", "full", "external"}
            or not _unique_strings(evidence)
            or any(item not in vocabularies["evidence"] for item in evidence)
        ):
            problems.append(f"{name}: invalid verification contract")

    reporting = contract["reporting"]
    if not isinstance(reporting, dict) or set(reporting) != {
        "terminal_record",
        "required_gates",
    }:
        problems.append(
            f"{name}: reporting must contain terminal_record and required_gates"
        )
    else:
        terminal = reporting["terminal_record"]
        gates = reporting["required_gates"]
        if terminal is not None and not _safe_relative(terminal):
            problems.append(f"{name}: unsafe terminal record")
        if not _unique_strings(gates) or any(
            gate not in vocabularies["gates"] for gate in gates
        ):
            problems.append(f"{name}: invalid reporting gates")

    sections = contract["required_sections"]
    policies = contract["forbidden_actions"]
    if not _unique_strings(sections) or any(not item for item in sections):
        problems.append(f"{name}: required_sections must be unique strings")
    else:
        headings = {
            match.group(1).strip()
            for match in re.finditer(
                r"^#{1,6}\s+(.+?)\s*$", reference.read_text(), re.M
            )
        }
        for section in sections:
            if section not in headings:
                problems.append(f"{name}: missing required section {section}")
    if not _unique_strings(policies) or any(
        policy not in vocabularies["policies"] for policy in policies
    ):
        problems.append(f"{name}: invalid forbidden_actions")
    elif effect != "read_only" and not {"duplicate-effect", "secret-output"}.issubset(
        policies
    ):
        problems.append(
            f"{name}: mutating/effectful contract must forbid duplicate effects and secret output"
        )
    if (
        isinstance(authorization, dict)
        and isinstance(authorization.get("gates"), list)
        and isinstance(policies, list)
    ):
        policy_by_gate = {
            "publish-explicit": "publish-without-authorization",
            "destructive-confirmation": "destructive-without-confirmation",
            "production-refusal": "production-mutation",
            "failed-preflight-stop": "effect-after-failed-preflight",
        }
        for gate, policy in policy_by_gate.items():
            if gate in authorization["gates"] and policy not in policies:
                problems.append(
                    f"{name}: gate {gate} requires forbidden action {policy}"
                )
    return problems


def validate_contracts(root: Path) -> list[str]:
    try:
        payload = load_contract_document(root)
        workflows = {
            workflow.name: workflow
            for workflow in load_workflows(root, include_pgm=True)
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [f"unable to load workflow contracts: {error}"]
    problems: list[str] = _validate_durable_runtime(root)
    raw_vocabularies = payload["vocabularies"]
    if set(raw_vocabularies) != set(VOCABULARIES):
        problems.append(
            "contract vocabularies must contain exactly gates, evidence, and policies"
        )
        return problems
    vocabularies: dict[str, set[str]] = {}
    for name, expected in VOCABULARIES.items():
        values = raw_vocabularies[name]
        if not _unique_strings(values) or set(values) != expected:
            problems.append(f"contract vocabulary {name} does not match schema v2")
        else:
            vocabularies[name] = set(values)
    if len(vocabularies) != len(VOCABULARIES):
        return problems

    seen: set[str] = set()
    for contract in payload["contracts"]:
        if not isinstance(contract, dict) or not isinstance(contract.get("name"), str):
            problems.append("contract must be an object with a string name")
            continue
        name = contract["name"]
        if name in seen:
            problems.append(f"duplicate workflow contract: {name}")
            continue
        seen.add(name)
        workflow = workflows.get(name)
        if workflow is None:
            problems.append(f"contract references unknown workflow: {name}")
            continue
        problems.extend(
            _validate_contract(
                root,
                name,
                contract,
                workflow.execution_class,
                root / workflow.reference,
                workflow.rules,
                vocabularies,
            )
        )
        try:
            workflow_dependencies(root, workflow)
        except (OSError, TypeError, ValueError) as error:
            problems.append(f"{name}: invalid workflow dependency: {error}")
    for missing in sorted(set(workflows) - seen):
        problems.append(f"missing workflow contract: {missing}")
    return problems
