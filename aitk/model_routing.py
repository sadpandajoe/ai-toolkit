"""Validated model/effort routing and fail-closed provider CLI workers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable


PROVIDERS = {"codex", "claude"}
REASONING = {"standard", "deep"}
RESPONSIBILITIES = {"implementation", "review", "rca", "operations"}
SANDBOXES = {"read-only", "workspace-write"}
PERMISSION_MODES = {"plan", "acceptEdits", "dontAsk"}
DISALLOWED_TOOLS = {"Write", "Edit", "NotebookEdit"}
ROUTE_NAMES = {
    "implementation",
    "review",
    "deep-review",
    "rca",
    "deep-rca",
    "operations",
}
ROUTE_RESTRICTIONS = {
    "implementation": (
        "Implement only the bounded task contract.",
        "Do not commit, push, publish, or widen scope.",
    ),
    "review": (
        "Perform an independent read-only review.",
        "Do not edit files or mutate external state.",
    ),
    "deep-review": (
        "Perform an independent read-only architecture, security, adversarial, or cold review.",
        "Do not edit files or mutate external state.",
    ),
    "rca": (
        "Synthesize root cause from supplied evidence.",
        "Do not edit files, decide implementation scope, or mutate external state.",
    ),
    "deep-rca": (
        "Synthesize ambiguous, intermittent, history-dependent, or cross-system root cause from supplied evidence.",
        "Do not edit files, decide implementation scope, or mutate external state.",
    ),
    "operations": (
        "Collect read-only evidence, produce deterministic reports, or prepare already-authored API, ticket, or Playwright steps for parent execution.",
        "Do not perform external mutations, execute tests, design tests, diagnose failures, perform RCA, review, decide fixes, or modify product code.",
    ),
}
ROUTE_ERROR = "MODEL_ROUTE_INVALID"
UNAVAILABLE_ERROR = "MODEL_ROUTE_UNAVAILABLE"
PROMPT_LIMIT = 1024 * 1024
DEFAULT_TIMEOUT = 1800
PREFLIGHT_TIMEOUT = 15
BLOCKED_EXIT = 4
FAILED_EXIT = 5
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")
CODEX_SELECTOR = re.compile(r"gpt-[0-9]+\.[0-9]+(?:\.[0-9]+)?-sol")
CLAUDE_SELECTOR = re.compile(r"claude-(opus|fable|sonnet)-[0-9]+(?:-[0-9]+)*")
DISPATCH_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:automatically\s+)?"
    r"(?:ask|use)\b.*\b(?:agents?|subagents?|workers?|reviewers?)\b"
    r"|"
    r"\b(?:spawn(?:s|ed|ing)?|launch(?:es|ed|ing)?|dispatch(?:es|ed|ing)?|"
    r"delegat(?:e|es|ed|ing)|hand(?:s|ed|ing)?\s+off|send(?:s|ing)?|sent|"
    r"fan\s+out)\b.*\b(?:agents?|subagents?|workers?|reviewers?)\b"
    r")",
    re.IGNORECASE,
)
ROUTE_MARKER = re.compile(r"^<!-- aitk-model-route:([a-z0-9]+(?:[.-][a-z0-9]+)*) -->$")
EXEMPT_MARKER = re.compile(r"^<!-- aitk-model-route-exempt:(.+) -->$")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BACKTICK_MARKDOWN_PATH = re.compile(r"`([^`\n]+\.md(?:#[^`\n]+)?)`")

WORKER_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "findings", "verification"],
    "properties": {
        "status": {"enum": ["completed", "blocked", "failed"]},
        "summary": {"type": "string", "minLength": 1},
        "findings": {"type": "array", "items": {"type": "string"}},
        "verification": {"type": "array", "items": {"type": "string"}},
    },
}


class ModelRouteError(ValueError):
    """A model route is invalid or cannot be honored."""

    def __init__(self, message: str, code: str = ROUTE_ERROR) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ResolvedRoute:
    name: str
    boundary: str | None
    required_contracts: tuple[str, ...]
    provider: str
    family: str
    selector: str
    effort: str
    responsibility: str
    restrictions: tuple[str, ...]
    controls: dict[str, object]
    minimum_cli: str
    unscored: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "route": self.name,
            "boundary": self.boundary,
            "required_contracts": self.required_contracts,
            "unscored": self.unscored,
            "provider": self.provider,
            "family": self.family,
            "selector": self.selector,
            "effort": self.effort,
            "responsibility": self.responsibility,
            "controls": self.controls,
        }


def _load(path: Path) -> object:
    return json.loads(path.read_text())


def load_model_routing(root: Path) -> dict[str, object]:
    try:
        payload = _load(root / "interfaces/model-routing.json")
    except (OSError, json.JSONDecodeError) as error:
        raise ModelRouteError(
            "model routing manifest is unavailable or invalid"
        ) from error
    problems = _validate_payload(root, payload)
    if problems:
        raise ModelRouteError("; ".join(problems))
    assert isinstance(payload, dict)
    return payload


def _safe_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        return None
    target = root / path
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            return None
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
        resolved_target.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return path if resolved_target.is_file() else None


def _safe_dispatch_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        return None
    target = root / path
    if target.exists():
        return _safe_path(root, value)
    if (
        len(path.parts) >= 3
        and path.parts[0] == "extensions"
        and not (root / "extensions" / path.parts[1]).exists()
    ):
        return path
    return None


def _valid_lens_menu(root: Path, boundary: dict[str, object]) -> bool:
    """Check the declared reviewer menu against the boundary's fan-out flag.

    A fan-out boundary must name at least two distinct, existing reviewer lens
    documents; a single-entry menu is a fan-out with nothing to select between
    and is almost always a half-finished edit. A boundary that does not fan out
    must not carry a menu at all -- `resolve_route` rejects `--lens` there, so a
    menu would describe a selection nothing can make.
    """
    lenses = boundary.get("lenses")
    if not boundary.get("lens_fanout", False):
        return lenses is None
    if not isinstance(lenses, list) or len(lenses) < 2:
        return False
    if len(set(map(repr, lenses))) != len(lenses):
        return False
    for lens in lenses:
        if not isinstance(lens, str) or not lens.endswith(".md"):
            return False
        safe = _safe_path(root, lens)
        if safe is None or not _contract_dependency_allowed(safe):
            return False
    return True


def _lens_menu(boundary: dict[str, object]) -> tuple[str, ...]:
    """Return the boundary's declared reviewer menu, empty when it does not fan out."""
    lenses = boundary.get("lenses")
    return tuple(lenses) if isinstance(lenses, list) else ()


def _route_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return {}
    return {
        str(item.get("name")): item
        for item in routes
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _validate_payload(root: Path, payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["model routing manifest must be an object"]
    if (
        set(payload)
        != {
            "version",
            "policy",
            "providers",
            "routes",
            "dispatch_boundaries",
            "dispatch_exemptions",
        }
        or type(payload.get("version")) is not int
        or payload.get("version") != 1
    ):
        return ["interfaces/model-routing.json does not match schema version 1"]
    problems: list[str] = []
    policy = payload.get("policy")
    if not isinstance(policy, dict) or set(policy) != {
        "efforts",
        "automatic_max",
        "fallback",
    }:
        problems.append("invalid model routing policy")
        efforts: object = None
    else:
        efforts = policy.get("efforts")
        if (
            efforts != {"standard": "high", "deep": "xhigh"}
            or policy.get("automatic_max") is not False
            or policy.get("fallback") != "forbidden"
        ):
            problems.append(
                "model routing policy must use high/xhigh with no max or fallback"
            )
    providers = payload.get("providers")
    if not isinstance(providers, dict) or set(providers) != PROVIDERS:
        problems.append("model routing providers must contain exactly codex and claude")
        providers = {}
    provider_models: dict[str, dict[str, str]] = {}
    expected_families = {"codex": {"sol"}, "claude": {"opus", "fable", "sonnet"}}
    selectors: set[str] = set()
    for provider in sorted(PROVIDERS):
        value = providers.get(provider) if isinstance(providers, dict) else None
        if not isinstance(value, dict) or set(value) != {"minimum_cli", "models"}:
            problems.append(f"{provider}: invalid model catalog")
            continue
        if not isinstance(value.get("minimum_cli"), str) or not re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+", str(value.get("minimum_cli"))
        ):
            problems.append(f"{provider}: invalid minimum CLI version")
        models = value.get("models")
        if not isinstance(models, dict) or set(models) != expected_families[provider]:
            problems.append(f"{provider}: model family coverage mismatch")
            continue
        provider_models[provider] = {}
        for family, model in models.items():
            if not isinstance(model, dict) or set(model) != {"selector"}:
                problems.append(f"{provider}/{family}: invalid model entry")
                continue
            selector = model.get("selector")
            if not isinstance(selector, str) or selector in selectors:
                problems.append(f"{provider}/{family}: invalid or duplicate selector")
                continue
            match = (
                CODEX_SELECTOR.fullmatch(selector)
                if provider == "codex"
                else CLAUDE_SELECTOR.fullmatch(selector)
            )
            if match is None or (provider == "claude" and match.group(1) != family):
                problems.append(f"{provider}/{family}: selector does not match family")
                continue
            selectors.add(selector)
            provider_models[provider][family] = selector

    routes = payload.get("routes")
    if not isinstance(routes, list):
        problems.append("model routes must be a list")
        routes = []
    seen_routes: set[str] = set()
    actual: dict[str, tuple[object, ...]] = {}
    for route in routes:
        if not isinstance(route, dict) or set(route) != {
            "name",
            "reasoning",
            "responsibility",
            "restrictions",
            "explicit_only",
            "providers",
        }:
            problems.append("invalid model route entry")
            continue
        name = route.get("name")
        reasoning = route.get("reasoning")
        responsibility = route.get("responsibility")
        restrictions = route.get("restrictions")
        explicit_only = route.get("explicit_only")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None
            or name in seen_routes
        ):
            problems.append(f"invalid or duplicate model route: {name}")
            continue
        seen_routes.add(name)
        if reasoning not in REASONING or responsibility not in RESPONSIBILITIES:
            problems.append(f"{name}: invalid reasoning or responsibility")
        if not isinstance(explicit_only, bool):
            problems.append(f"{name}: explicit_only must be boolean")
        if (
            not isinstance(restrictions, list)
            or not restrictions
            or any(not isinstance(item, str) or not item for item in restrictions)
        ):
            problems.append(f"{name}: restrictions must be nonempty strings")
        elif tuple(restrictions) != ROUTE_RESTRICTIONS.get(name):
            problems.append(f"{name}: responsibility restrictions do not match policy")
        mappings = route.get("providers")
        if not isinstance(mappings, dict) or set(mappings) != PROVIDERS:
            problems.append(f"{name}: provider mapping coverage mismatch")
            continue
        codex = mappings.get("codex")
        claude = mappings.get("claude")
        if (
            not isinstance(codex, dict)
            or set(codex) != {"model", "sandbox"}
            or codex.get("model") not in provider_models.get("codex", {})
            or codex.get("sandbox") not in SANDBOXES
        ):
            problems.append(f"{name}/codex: invalid route controls")
            continue
        if (
            not isinstance(claude, dict)
            or set(claude) != {"model", "permission_mode", "disallowed_tools"}
            or claude.get("model") not in provider_models.get("claude", {})
            or claude.get("permission_mode") not in PERMISSION_MODES
            or not isinstance(claude.get("disallowed_tools"), list)
            or any(
                not isinstance(item, str) or item not in DISALLOWED_TOOLS
                for item in claude.get("disallowed_tools", [])
            )
            or len(set(claude.get("disallowed_tools", [])))
            != len(claude.get("disallowed_tools", []))
        ):
            problems.append(f"{name}/claude: invalid route controls")
            continue
        actual[name] = (
            reasoning,
            responsibility,
            explicit_only,
            codex.get("model"),
            codex.get("sandbox"),
            claude.get("model"),
            claude.get("permission_mode"),
            tuple(claude.get("disallowed_tools", [])),
        )
    expected = {
        "implementation": (
            "standard",
            "implementation",
            False,
            "sol",
            "workspace-write",
            "opus",
            "acceptEdits",
            (),
        ),
        "review": (
            "standard",
            "review",
            False,
            "sol",
            "read-only",
            "opus",
            "plan",
            ("Write", "Edit", "NotebookEdit"),
        ),
        "deep-review": (
            "deep",
            "review",
            False,
            "sol",
            "read-only",
            "fable",
            "plan",
            ("Write", "Edit", "NotebookEdit"),
        ),
        "rca": (
            "standard",
            "rca",
            False,
            "sol",
            "read-only",
            "opus",
            "plan",
            ("Write", "Edit", "NotebookEdit"),
        ),
        "deep-rca": (
            "deep",
            "rca",
            False,
            "sol",
            "read-only",
            "fable",
            "plan",
            ("Write", "Edit", "NotebookEdit"),
        ),
        "operations": (
            "standard",
            "operations",
            False,
            "sol",
            "read-only",
            "sonnet",
            "dontAsk",
            ("Write", "Edit", "NotebookEdit"),
        ),
    }
    if seen_routes != ROUTE_NAMES or actual != expected:
        problems.append("model route vocabulary or invariant mapping mismatch")

    declared_routes = seen_routes
    boundaries = payload.get("dispatch_boundaries")
    if not isinstance(boundaries, list):
        problems.append("dispatch_boundaries must be a list")
        boundaries = []
    exemptions_value = payload.get("dispatch_exemptions")
    if not isinstance(exemptions_value, list):
        problems.append("dispatch_exemptions must be a list")
        exemptions_value = []
    seen_ids: set[str] = set()
    for boundary in boundaries:
        if (
            not isinstance(boundary, dict)
            or not {"id", "path", "count", "routes"} <= set(boundary)
            or not set(boundary)
            <= {"id", "path", "count", "routes", "unscored", "lens_fanout", "lenses"}
            or type(boundary.get("unscored", False)) is not bool
            or type(boundary.get("lens_fanout", False)) is not bool
        ):
            problems.append("invalid dispatch boundary entry")
            continue
        identifier = boundary.get("id")
        routes_value = boundary.get("routes")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", identifier) is None
            or identifier in seen_ids
            or type(boundary.get("count")) is not int
            or boundary.get("count") != 1
            or _safe_dispatch_path(root, boundary.get("path")) is None
            or not isinstance(routes_value, list)
            or not routes_value
            or any(
                not isinstance(route, str) or route not in declared_routes
                for route in routes_value
            )
            or len(set(routes_value)) != len(routes_value)
        ):
            problems.append(f"invalid dispatch boundary: {identifier}")
            continue
        # A fan-out boundary declares its reviewer menu here rather than leaving
        # it implicit in the dispatch prose. The span scan below still has to
        # agree with this list, but the manifest is what `resolve_route` checks
        # `--lens` against, so an omitted lens is a rejected dispatch instead of
        # a lane that quietly does not exist.
        if not _valid_lens_menu(root, boundary):
            problems.append(f"invalid dispatch boundary lens menu: {identifier}")
            continue
        for route_name in routes_value:
            route_item = _route_map(payload).get(route_name, {})
            responsibility = str(route_item.get("responsibility"))
            # Narrowing a fan-out span to one lens only happens on the review
            # route. A fan-out boundary on any other route would demand `--lens`
            # at dispatch, never scan its span, and drop the named lens without
            # a word -- reject the combination here rather than shipping it.
            if boundary.get("lens_fanout", False) and responsibility != "review":
                problems.append(f"lens_fanout boundary is not a review lane: {identifier}")
            try:
                # `lens` is deliberately omitted: check time verifies that the
                # unnarrowed union resolves, so every lens the span names is
                # reachable. Dispatch time is where exactly one gets selected.
                required_contracts = _required_contract_paths(
                    root,
                    str(boundary.get("path")),
                    responsibility,
                    identifier,
                    None,
                    _lens_menu(boundary),
                )
            except ModelRouteError as error:
                problems.append(str(error))
                continue
            if any(
                _safe_dispatch_path(root, contract) is None
                for contract in required_contracts
            ):
                problems.append(f"missing required boundary contract: {identifier}")
        seen_ids.add(identifier)
    seen_exemptions: set[tuple[str, str]] = set()
    for exemption in exemptions_value:
        if not isinstance(exemption, dict) or set(exemption) != {
            "path",
            "marker",
            "count",
        }:
            problems.append("invalid dispatch exemption entry")
            continue
        path_value, marker = exemption.get("path"), exemption.get("marker")
        identity = (str(path_value), str(marker))
        if (
            _safe_path(root, path_value) is None
            or not isinstance(marker, str)
            or not marker
            or type(exemption.get("count")) is not int
            or exemption.get("count") != 1
            or identity in seen_exemptions
        ):
            problems.append(f"invalid dispatch exemption: {identity}")
            continue
        seen_exemptions.add(identity)
    return problems


def validate_model_routing(root: Path) -> list[str]:
    try:
        payload = _load(root / "interfaces/model-routing.json")
    except (OSError, json.JSONDecodeError) as error:
        return [str(error)]
    problems = _validate_payload(root, payload)
    if isinstance(payload, dict) and not problems:
        problems.extend(validate_selector_ownership(root, payload))
        problems.extend(validate_dispatch_boundaries(root, payload))
        problems.extend(validate_route_bindings(root))
        problems.extend(validate_legacy_route_prose(root))
    return problems


def validate_legacy_route_prose(root: Path) -> list[str]:
    paths = list((root / "skills/cherry-pick").rglob("*.md"))
    paths.append(root / "rules/orchestration.md")
    legacy = re.compile(
        r"\b(?:Standard|Heavy)-tier\b|"
        r"\b(?:standard|heavy) reasoning effort\b|"
        r"\bheavy effort\b",
        re.I,
    )
    problems: list[str] = []
    for path in sorted(set(paths)):
        if not path.is_file() or path.is_symlink():
            continue
        for number, line in _markdown_lines(path):
            gate_legacy = (
                path == root / "skills/cherry-pick/references/gate.md"
                and re.search(r"\b(?:Standard|Heavy)\b", line) is not None
            )
            if legacy.search(line) or gate_legacy:
                problems.append(
                    "legacy route vocabulary in authoritative cherry-pick prose: "
                    f"{path.relative_to(root)}:{number}"
                )
    return problems


def validate_route_bindings(root: Path) -> list[str]:
    try:
        payload = _load(root / "interfaces/providers.json")
    except (OSError, json.JSONDecodeError) as error:
        return [str(error)]
    if not isinstance(payload, dict) or not isinstance(payload.get("providers"), dict):
        return ["provider bindings unavailable for model routing"]
    problems: list[str] = []
    for provider in sorted(PROVIDERS):
        provider_value = payload["providers"].get(provider)
        bindings = (
            provider_value.get("bindings") if isinstance(provider_value, dict) else None
        )
        for capability in ("fresh_subagent", "independent_review", "routed_subagent"):
            binding = bindings.get(capability) if isinstance(bindings, dict) else None
            if not isinstance(binding, dict) or (
                binding.get("mode"),
                binding.get("fallback"),
            ) != ("fallback", "source_linked_model_run"):
                problems.append(
                    f"{provider}/{capability}: must use source_linked_model_run"
                )
    return problems


def validate_selector_ownership(root: Path, payload: dict[str, object]) -> list[str]:
    del payload
    paths = [
        path
        for name in ("README.md", "CHANGELOG.md", "pyproject.toml")
        if (path := root / name).is_file()
    ]
    authored_roots = (
        ".codex-plugin",
        "aitk",
        "bin",
        "config",
        "docs",
        "extensions",
        "hooks",
        "interfaces",
        "rules",
        "scripts",
        "skills",
    )
    suffixes = {".json", ".md", ".py", ".sh", ".toml", ".yaml", ".yml"}
    for name in authored_roots:
        base = root / name
        if base.is_file():
            paths.append(base)
        elif base.is_dir():
            paths.extend(path for path in base.rglob("*") if path.suffix in suffixes)
    problems: list[str] = []
    for path in sorted(set(paths)):
        if not path.is_file() or path.is_symlink():
            continue
        if path in {
            root / "interfaces/model-routing.json",
            root / "aitk/pricing.py",
            root / "scripts/optimize-cost.py",
            root / "scripts/show-cost.py",
        }:
            # Pricing is an independent historical registry, not route selection.
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if CODEX_SELECTOR.search(text) or CLAUDE_SELECTOR.search(text):
            problems.append(
                f"volatile model selector copied outside manifest: {path.relative_to(root)}"
            )
    return problems


def _markdown_lines(path: Path) -> list[tuple[int, str]]:
    return _markdown_content_lines(path.read_text())


def _markdown_content_lines(text: str) -> list[tuple[int, str]]:
    """Return numbered Markdown lines outside frontmatter and fenced blocks."""
    result: list[tuple[int, str]] = []
    fence_character: str | None = None
    fence_length = 0
    frontmatter = False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if number == 1 and stripped == "---":
            frontmatter = True
            continue
        if frontmatter:
            if stripped == "---":
                frontmatter = False
            continue
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence_character is not None:
            if (
                fence is not None
                and fence.group(1)[0] == fence_character
                and len(fence.group(1)) >= fence_length
            ):
                fence_character = None
                fence_length = 0
            continue
        if fence is not None:
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue
        result.append((number, line))
    return result


def validate_dispatch_boundaries(root: Path, payload: dict[str, object]) -> list[str]:
    declared = {
        item["id"]: item
        for item in payload["dispatch_boundaries"]
        if (root / item["path"]).is_file()
    }
    exemptions = {
        (item["path"], item["marker"]): item for item in payload["dispatch_exemptions"]
    }
    route_counts: dict[tuple[str, str], int] = {}
    exemption_counts: dict[tuple[str, str], int] = {}
    used_route_markers: set[tuple[str, str]] = set()
    used_exemption_markers: set[tuple[str, str]] = set()
    problems: list[str] = []
    paths = list((root / "skills").glob("**/*.md"))
    paths.extend((root / "extensions").glob("*/skills/**/*.md"))
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            problems.append(f"dispatch scan refuses symlink: {relative}")
            continue
        if not path.is_file():
            continue
        previous_nonblank: tuple[int, str] | None = None
        for number, line in _markdown_lines(path):
            stripped = line.strip()
            route_marker = ROUTE_MARKER.fullmatch(stripped)
            exemption_marker = EXEMPT_MARKER.fullmatch(stripped)
            if route_marker is not None:
                key = (relative, route_marker.group(1))
                route_counts[key] = route_counts.get(key, 0) + 1
            elif exemption_marker is not None:
                key = (relative, exemption_marker.group(1))
                exemption_counts[key] = exemption_counts.get(key, 0) + 1
            elif not stripped.startswith("#") and DISPATCH_PATTERN.search(line):
                prior = previous_nonblank[1].strip() if previous_nonblank else ""
                prior_route = ROUTE_MARKER.fullmatch(prior)
                prior_exemption = EXEMPT_MARKER.fullmatch(prior)
                if prior_route is not None:
                    used_route_markers.add((relative, prior_route.group(1)))
                elif prior_exemption is not None:
                    used_exemption_markers.add((relative, prior_exemption.group(1)))
                else:
                    problems.append(
                        f"unmarked model dispatch boundary: {relative}:{number}"
                    )
            if stripped:
                previous_nonblank = (number, line)
    for (path_value, identifier), count in sorted(route_counts.items()):
        item = declared.get(identifier)
        if item is None or item["path"] != path_value or count != 1:
            problems.append(
                f"unknown, misplaced, or duplicate route marker: {path_value}/{identifier}"
            )
    for identifier, item in sorted(declared.items()):
        if route_counts.get((item["path"], identifier), 0) != 1:
            problems.append(f"missing route marker: {item['path']}/{identifier}")
        elif (item["path"], identifier) not in used_route_markers:
            problems.append(
                f"route marker does not precede a dispatch: {item['path']}/{identifier}"
            )
    for key, count in sorted(exemption_counts.items()):
        if key not in exemptions or count != 1:
            problems.append(
                f"unknown, misplaced, or duplicate route exemption: {key[0]}/{key[1]}"
            )
    for key in sorted(exemptions):
        if exemption_counts.get(key, 0) != 1:
            problems.append(f"missing route exemption: {key[0]}/{key[1]}")
        elif key not in used_exemption_markers:
            problems.append(
                f"route exemption does not precede a dispatch: {key[0]}/{key[1]}"
            )
    problems.extend(_lens_menu_problems(root, declared))
    return problems


def _span_link_targets(root: Path, boundary: dict[str, object]) -> set[str]:
    """Resolve the Markdown links inside one boundary's marker span."""
    source = root / str(boundary["path"])
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    targets: set[str] = set()
    span = _marker_span_text(content, str(boundary["id"]))
    for match in MARKDOWN_LINK.finditer(span):
        target = match.group(1).strip().strip("<>").split("#", 1)[0]
        if not target or "://" in target:
            continue
        try:
            relative = (source.parent / target).resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        targets.add(relative.as_posix())
    return targets


def _lens_menu_problems(root: Path, declared: dict[str, dict[str, object]]) -> list[str]:
    """Report drift between declared reviewer menus and the dispatch prose.

    Both directions matter and they fail differently. A lens the manifest names
    but the span does not link cannot be dispatched -- `_contract_closure` fails
    closed on it, but only when someone happens to select it. A lens the span
    links but the manifest omits is worse and quieter: narrowing skips it, so it
    rides into *every* worker's closure as a shared dependency and each reviewer
    runs under two lens contracts at once. Neither shows up in a passing route
    resolution, so both are caught here instead.
    """
    problems: list[str] = []
    every_lens = {
        lens
        for boundary in declared.values()
        for lens in _lens_menu(boundary)
    }
    for identifier, boundary in sorted(declared.items()):
        menu = set(_lens_menu(boundary))
        if not menu:
            continue
        linked = _span_link_targets(root, boundary)
        for missing in sorted(menu - linked):
            problems.append(
                f"declared lens is not linked in the dispatch span: "
                f"{identifier}/{missing}"
            )
        for undeclared in sorted((linked & every_lens) - menu):
            problems.append(
                f"reviewer lens linked in the dispatch span but not declared: "
                f"{identifier}/{undeclared}"
            )
    return problems


def resolve_route(
    root: Path,
    route: str,
    provider: str,
    boundary: str | None = None,
    lens: str | None = None,
) -> ResolvedRoute:
    payload = load_model_routing(root)
    if provider not in PROVIDERS:
        raise ModelRouteError(f"unknown provider: {provider}")
    item = _route_map(payload).get(route)
    if item is None:
        raise ModelRouteError(f"unknown or nonspawnable route: {route}")
    if boundary is not None:
        boundary_item = next(
            (
                candidate
                for candidate in payload["dispatch_boundaries"]
                if candidate["id"] == boundary
            ),
            None,
        )
        if boundary_item is None:
            raise ModelRouteError(f"unknown dispatch boundary: {boundary}")
        if route not in boundary_item["routes"]:
            raise ModelRouteError(f"{route} is not allowed at boundary {boundary}")
        # A fan-out boundary dispatches one worker per selected lens. Resolving
        # it without naming the lens would hand that worker the whole menu, so
        # require the selection rather than defaulting to the union. The guard
        # runs both ways: a boundary that does not fan out has no menu to
        # narrow, and its span names ordinary dependencies rather than lenses,
        # so accepting `--lens` there would silently drop every span dependency
        # the flag does not match -- the same quiet-shrink failure the fan-out
        # requirement exists to prevent.
        fans_out = boundary_item.get("lens_fanout", False)
        menu = _lens_menu(boundary_item)
        if fans_out and lens is None:
            raise ModelRouteError(
                f"boundary {boundary} fans out over reviewer lenses; "
                "pass --lens to select exactly one"
            )
        if lens is not None and not fans_out:
            raise ModelRouteError(
                f"boundary {boundary} does not fan out over reviewer lenses; "
                "--lens is not accepted here"
            )
        if lens is not None and lens not in menu:
            raise ModelRouteError(
                f"lens {lens} is not named at boundary {boundary}; "
                f"declared lenses: {', '.join(menu)}"
            )
        required_contracts = _required_contract_paths(
            root,
            boundary_item["path"],
            str(item["responsibility"]),
            boundary,
            lens,
            menu,
        )
        unscored = bool(boundary_item.get("unscored", False))
    else:
        required_contracts = ()
        unscored = False
    mapping = item["providers"][provider]
    family = mapping["model"]
    provider_config = payload["providers"][provider]
    return ResolvedRoute(
        name=route,
        boundary=boundary,
        required_contracts=required_contracts,
        provider=provider,
        family=family,
        selector=provider_config["models"][family]["selector"],
        effort=payload["policy"]["efforts"][item["reasoning"]],
        responsibility=item["responsibility"],
        restrictions=tuple(item["restrictions"]),
        controls=dict(mapping),
        minimum_cli=provider_config["minimum_cli"],
        unscored=unscored,
    )


def _contracts(root: Path, values: tuple[str, ...]) -> tuple[tuple[str, str, str], ...]:
    if not values:
        raise ModelRouteError("model-run requires at least one inline contract")
    result: list[tuple[str, str, str]] = []
    seen: set[Path] = set()
    total = 0
    for value in values:
        safe = _safe_path(root, value)
        if safe is None:
            raise ModelRouteError(f"unsafe or missing contract file: {value}")
        if safe in seen:
            continue
        seen.add(safe)
        try:
            content = (root / safe).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ModelRouteError(
                f"contract file could not be read: {value}"
            ) from error
        total += len(content.encode("utf-8"))
        if total > PROMPT_LIMIT:
            raise ModelRouteError("inline contracts exceed 1 MiB")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        result.append((safe.as_posix(), digest, content))
    return tuple(result)


def _required_contract_paths(
    root: Path,
    boundary_path: str,
    responsibility: str,
    boundary_id: str,
    lens: str | None = None,
    lens_menu: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Derive the exact inline contract closure for one dispatch boundary."""
    path = Path(boundary_path)
    parts = path.parts
    if len(parts) >= 2 and parts[0] == "skills":
        owner = Path("skills") / parts[1] / "SKILL.md"
    elif len(parts) >= 4 and parts[0] == "extensions" and parts[2] == "skills":
        owner = Path(*parts[:4]) / "SKILL.md"
    else:
        raise ModelRouteError(f"dispatch boundary has no skill owner: {boundary_path}")
    review_umbrella = "skills/review/SKILL.md"
    route_contract = {
        "implementation": "skills/implement-change/SKILL.md",
        # The review umbrella is the discipline contract for shipped-code
        # review, and the predicate here is ownership, not discipline: only a
        # boundary the review skill itself owns gets it. That is deliberately
        # blunt. It keeps the reviewer-lens table and Code-judo dispatch rules
        # away from the QA, PM, plan-review, and cherry-pick scope-leak lanes
        # that ride the review *route* without grading code -- but it also
        # drops the umbrella from code-review lanes another skill owns
        # (`workflows.review-code-*`, `workflows.review-pr-fresh`,
        # `workflows.adversarial-*`). Those stay correct because each reaches
        # the contracts it needs through its own span: the orchestration
        # references and the adversarial lens name their grading contracts in
        # their own Required Context. Adding a review-owned boundary is safe;
        # adding a code-review boundary under another owner means checking that
        # its span or Required Context still names the grading contracts.
        "review": review_umbrella if owner.as_posix() == review_umbrella else owner.as_posix(),
        "rca": "skills/debug/SKILL.md",
        "operations": owner.as_posix(),
    }.get(responsibility)
    if route_contract is None:
        raise ModelRouteError(f"unknown contract responsibility: {responsibility}")
    values = (
        "rules/model-assignment.md",
        # Every lane on the review route stops the same way, whatever it grades.
        # This used to ride in on the review umbrella's Required Context, which
        # is why the umbrella had to be injected everywhere; seeding it here is
        # what let the umbrella narrow to the lanes that actually own it. The
        # seed stays scoped to the review route: stop-rules is a review/fix-loop
        # contract that directs the worker to emit a Review Gate and cites
        # severity and review-gate, none of which reach an implementation, RCA,
        # or operations closure -- shipping it there would hand those workers
        # instructions pointing at documents they do not have.
        *(("rules/stop-rules.md",) if responsibility == "review" else ()),
        owner.as_posix(),
        route_contract,
        path.as_posix(),
    )
    return _contract_closure(
        root,
        tuple(dict.fromkeys(values)),
        path.as_posix(),
        responsibility,
        boundary_id,
        lens,
        lens_menu,
    )


def _contract_closure(
    root: Path,
    seeds: tuple[str, ...],
    boundary_path: str,
    responsibility: str,
    boundary_id: str,
    lens: str | None = None,
    lens_menu: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Follow required and review-lens Markdown dependencies in stable order."""
    root = root.resolve()
    queued = list(seeds)
    result: list[str] = []
    seen: set[str] = set()
    while queued:
        value = queued.pop(0)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) > 256:
            raise ModelRouteError("inline contract closure exceeds 256 files")
        source = root / value
        if not source.is_file() or source.is_symlink():
            continue
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ModelRouteError(
                f"contract dependency could not be read: {value}"
            ) from error
        if source.name == "SKILL.md":
            for sibling_name in ("rules.md", "lessons.md", "gotchas.md"):
                sibling = source.with_name(sibling_name)
                if sibling.is_file() and not sibling.is_symlink():
                    sibling_value = sibling.relative_to(root).as_posix()
                    if sibling_value not in seen and sibling_value not in queued:
                        queued.append(sibling_value)
        if value == boundary_path:
            # The boundary document must carry its own marker. Without this the
            # span scan below returns nothing, the closure silently shrinks to
            # the seed contracts, and `resolve_route` still hands the caller a
            # launchable route -- `validate_dispatch_boundaries` catches the
            # same defect, but only at check time, never on the dispatch path.
            if not _marker_present(content, boundary_id):
                raise ModelRouteError(
                    f"missing route marker: {boundary_path}/{boundary_id}"
                )
        # Reviewer lanes need the lens references named at their own dispatch
        # site, but a boundary document usually declares several lanes. Scan the
        # marker's own section only, so one lane never inherits another lane's
        # lenses; the Required Context section is unioned in because a lens file
        # keeps its shared rules there, outside any marker span.
        scan_span = value == boundary_path and responsibility == "review"
        span_text = _marker_span_text(content, boundary_id) if scan_span else ""
        context_text = _required_context_text(content)
        candidates: list[tuple[str, bool, bool]] = []
        for text, from_span in ((span_text, True), (context_text, False)):
            candidates.extend(
                (match.group(1), True, from_span)
                for match in MARKDOWN_LINK.finditer(text)
            )
            candidates.extend(
                (match.group(1), False, from_span)
                for match in BACKTICK_MARKDOWN_PATH.finditer(text)
            )
        # A fan-out marker names every lens the orchestrator may pick from, but
        # one dispatch launches exactly one lens. Without this filter each worker
        # is handed all eight sibling reviewer contracts and reviews under
        # conflicting instructions.
        #
        # The menu is the manifest's declared `lenses` list, not "whatever the
        # span links to". Only a span link that the manifest names as a lens of
        # *this* boundary is narrowed away; every other span link stays in the
        # closure as an ordinary shared dependency. Required Context is likewise
        # never narrowed -- it holds the boundary document's own shared rules.
        # `validate_dispatch_boundaries` keeps the two in step, so a lens the
        # doc gained but the manifest did not is a check-time failure rather
        # than a contract silently demoted to a dependency of all eight workers.
        menu = frozenset(lens_menu)
        lens_selected = False
        for raw_target, is_link, from_span in candidates:
            target_text = raw_target.strip().strip("<>").split("#", 1)[0]
            if (
                not target_text
                or "://" in target_text
                or target_text.startswith("mailto:")
            ):
                continue
            if source.name == "SKILL.md" and target_text in {
                "rules.md",
                "lessons.md",
                "gotchas.md",
            }:
                continue
            target_path = Path(target_text)
            if not is_link and len(target_path.parts) == 1:
                continue
            if is_link:
                possible = (source.parent / target_path,)
            else:
                root_relative = [root / target_path]
                if len(target_path.parts) >= 2:
                    root_relative.append(root / "skills" / target_path)
                root_relative.append(source.parent / target_path)
                possible = tuple(root_relative)
            for candidate in possible:
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(root)
                except (OSError, ValueError):
                    continue
                if not _contract_dependency_allowed(relative):
                    continue
                if (
                    resolved.is_file()
                    and not resolved.is_symlink()
                    and resolved.suffix == ".md"
                ):
                    relative_text = relative.as_posix()
                    if from_span and is_link and relative_text in menu:
                        if lens is not None and relative_text != lens:
                            break
                        lens_selected = True
                    if relative_text not in seen and relative_text not in queued:
                        queued.append(relative_text)
                    break
            else:
                allowed_paths = []
                for candidate in possible:
                    try:
                        relative = candidate.resolve().relative_to(root)
                    except (OSError, ValueError):
                        continue
                    if _contract_dependency_allowed(relative):
                        allowed_paths.append(relative.as_posix())
                if allowed_paths:
                    raise ModelRouteError(
                        f"missing contract dependency from {value}: {target_text}"
                    )
        # Fail closed: `resolve_route` already rejects a lens outside the
        # declared menu, so reaching here means the menu named a lens the
        # dispatch prose does not link. Returning the unnarrowed closure would
        # reintroduce exactly the leak the filter exists to stop.
        if lens is not None and scan_span and not lens_selected:
            raise ModelRouteError(
                f"lens {lens} is not named at boundary {boundary_id}"
            )
    return tuple(result)


def _marker_present(content: str, boundary_id: str) -> bool:
    """Report whether a boundary document carries its own route marker."""
    return any(
        (match := ROUTE_MARKER.fullmatch(line.strip())) is not None
        and match.group(1) == boundary_id
        for _, line in _markdown_content_lines(content)
    )


def _marker_span_text(content: str, boundary_id: str) -> str:
    """Return the dispatch prose owned by one route marker.

    The span runs from the marker to the next route/exemption marker or the next
    Markdown heading, whichever comes first. Headings and markers inside fenced
    examples are documentation, not span structure, so the scan runs over
    fence-stripped lines. A boundary whose marker is missing contributes nothing
    here; callers on the dispatch path check `_marker_present` first so a missing
    marker fails closed instead of silently shrinking the closure.
    """
    selected: list[str] = []
    in_span = False
    for _, line in _markdown_content_lines(content):
        stripped = line.strip()
        route_marker = ROUTE_MARKER.fullmatch(stripped)
        if route_marker is not None:
            in_span = route_marker.group(1) == boundary_id
            continue
        if in_span and (
            EXEMPT_MARKER.fullmatch(stripped) is not None or stripped.startswith("#")
        ):
            break
        if in_span:
            selected.append(line)
    return "\n".join(selected)


def _required_context_text(content: str) -> str:
    lines = content.splitlines()
    selected: list[str] = []
    in_required_section = False
    for line in lines:
        if line.startswith("## Required Context"):
            in_required_section = True
            selected.append(line)
            continue
        if in_required_section and line.startswith("## "):
            in_required_section = False
        if in_required_section or re.search(r"\b(?:Read before|Findings use)\b", line):
            selected.append(line)
    return "\n".join(selected)


def _contract_dependency_allowed(path: Path) -> bool:
    if not path.parts:
        return False
    if path.parts[0] in {"rules", "skills"}:
        return True
    return (
        len(path.parts) >= 4
        and path.parts[0] == "extensions"
        and path.parts[2] == "skills"
    )


def worker_prompt(
    route: ResolvedRoute,
    prompt: str,
    contracts: tuple[tuple[str, str, str], ...],
    workspace: Path | None = None,
) -> str:
    restrictions = json.dumps(route.restrictions, separators=(",", ":"))
    prefix = (
        "AI_TOOLKIT_MODEL_ROUTE_V1\n"
        f"route={route.name}\nboundary={route.boundary}\n"
        f"provider={route.provider}\nfamily={route.family}\n"
        f"selector={route.selector}\neffort={route.effort}\n"
        f"responsibility={route.responsibility}\nrestrictions={restrictions}\n"
        f"workspace={workspace if workspace is not None else '<caller-workspace>'}\n"
        "INLINE_CONTRACTS_BEGIN\n"
    )
    contract_text = ""
    for path, digest, content in contracts:
        contract_text += f"CONTRACT path={path} sha256={digest}\n{content}"
        if not contract_text.endswith("\n"):
            contract_text += "\n"
        contract_text += "CONTRACT_END\n"
    task = prompt + ("" if prompt.endswith("\n") else "\n")
    return (
        prefix
        + contract_text
        + "INLINE_CONTRACTS_END\nTASK_BEGIN\n"
        + task
        + "TASK_END\n"
    )


def _valid_worker(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"status", "summary", "findings", "verification"}
        and value.get("status") in {"completed", "blocked", "failed"}
        and isinstance(value.get("summary"), str)
        and bool(value.get("summary"))
        and all(
            isinstance(value.get(key), list)
            and all(isinstance(item, str) for item in value[key])
            for key in ("findings", "verification")
        )
    )


def parse_codex_output(output: str, last_message: str) -> dict[str, object]:
    for line in output.splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ModelRouteError("invalid Codex event", UNAVAILABLE_ERROR)
        event_type = value.get("type")
        if event_type == "error" or (
            isinstance(event_type, str) and event_type.endswith(".failed")
        ):
            raise ModelRouteError("Codex returned an error event", UNAVAILABLE_ERROR)
    terminal = json.loads(last_message)
    if not _valid_worker(terminal):
        raise ModelRouteError(
            "Codex did not return one valid worker result", UNAVAILABLE_ERROR
        )
    return terminal


def parse_claude_output(output: str) -> dict[str, object]:
    value = json.loads(output)
    if (
        not isinstance(value, dict)
        or value.get("type") != "result"
        or value.get("subtype") != "success"
        or value.get("is_error") is not False
        or not _valid_worker(value.get("structured_output"))
    ):
        raise ModelRouteError(
            "Claude did not return one valid worker result", UNAVAILABLE_ERROR
        )
    return value["structured_output"]


def _version_tuple(value: str) -> tuple[int, int, int, int]:
    match = VERSION_PATTERN.search(value)
    if match is None:
        raise ModelRouteError(
            "provider CLI version could not be parsed", UNAVAILABLE_ERROR
        )
    token = match.group(0)
    core = token.split("-", 1)[0].split("+", 1)[0]
    major, minor, patch = (int(item) for item in core.split("."))
    stable = 0 if "-" in token else 1
    return major, minor, patch, stable


def _required_flags(route: ResolvedRoute) -> tuple[str, ...]:
    if route.provider == "codex":
        return (
            "--ephemeral",
            "--strict-config",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable",
            "--model",
            "--config",
            "--sandbox",
            "--cd",
            "--add-dir",
            "--output-schema",
            "--output-last-message",
            "--json",
        )
    flags = [
        "--print",
        "--no-session-persistence",
        "--safe-mode",
        "--strict-mcp-config",
        "--mcp-config",
        "--model",
        "--effort",
        "--permission-mode",
        "--json-schema",
        "--output-format",
        "--tools",
    ]
    if route.controls.get("disallowed_tools"):
        flags.append("--disallowedTools")
    return tuple(flags)


def _has_flag(help_text: str, flag: str) -> bool:
    return (
        re.search(rf"(?:^|\s){re.escape(flag)}(?=\s|[=,\[]|$)", help_text) is not None
    )


def _preflight(
    route: ResolvedRoute,
    executable: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    version = run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        timeout=PREFLIGHT_TIMEOUT,
        check=False,
    )
    version_text = version.stdout + version.stderr
    if version.returncode or _version_tuple(version_text) < _version_tuple(
        route.minimum_cli
    ):
        raise ModelRouteError(
            f"{route.provider} CLI does not meet minimum {route.minimum_cli}",
            UNAVAILABLE_ERROR,
        )
    help_argv = (
        [executable, "exec", "--help"]
        if route.provider == "codex"
        else [executable, "--help"]
    )
    help_result = run(
        help_argv,
        text=True,
        capture_output=True,
        timeout=PREFLIGHT_TIMEOUT,
        check=False,
    )
    help_text = help_result.stdout + help_result.stderr
    if help_result.returncode or any(
        not _has_flag(help_text, flag) for flag in _required_flags(route)
    ):
        raise ModelRouteError(
            f"{route.provider} CLI lacks required routing flags", UNAVAILABLE_ERROR
        )


def _argv(
    route: ResolvedRoute,
    executable: str,
    workspace: Path,
    schema: str,
    output_path: str | None = None,
    isolated_project_root: Path | str | None = None,
) -> list[str]:
    if route.provider == "codex":
        project_root = isolated_project_root or "<isolated-project-root>"
        return [
            executable,
            "exec",
            "--ephemeral",
            "--strict-config",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable",
            "hooks",
            "--model",
            route.selector,
            "--config",
            f'model_reasoning_effort="{route.effort}"',
            "--config",
            "mcp_servers={}",
            "--config",
            "project_doc_max_bytes=0",
            "--sandbox",
            str(route.controls["sandbox"]),
            "--cd",
            str(project_root),
            "--add-dir",
            str(workspace),
            "--output-schema",
            schema,
            "--output-last-message",
            output_path or "<last-message-path>",
            "--json",
            "-",
        ]
    result = [
        executable,
        "--print",
        "--no-session-persistence",
        "--safe-mode",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers": {}}',
        "--model",
        route.selector,
        "--effort",
        route.effort,
        "--permission-mode",
        str(route.controls["permission_mode"]),
    ]
    tools = route.controls.get("disallowed_tools", [])
    if tools:
        result.extend(["--disallowedTools", *tools])
    available_tools = (
        ["Read", "Grep", "Glob", "Edit", "Write"]
        if route.responsibility == "implementation"
        else ["Read", "Grep", "Glob"]
    )
    result.extend(["--tools", *available_tools])
    result.extend(["--json-schema", schema, "--output-format", "json"])
    return result


def _outer(
    route: ResolvedRoute,
    *,
    dry_run: bool,
    started: bool,
    exit_code: int | None,
    argv: list[str] | None,
    result: dict[str, object] | None,
    error: str | None,
) -> dict[str, object]:
    return {
        "command": "model-run",
        "dry_run": dry_run,
        "route": route.name,
        "boundary": route.boundary,
        "provider": route.provider,
        "request": {
            "family": route.family,
            "selector": route.selector,
            "effort": route.effort,
        },
        "transport": {"started": started, "exit_code": exit_code},
        "argv": argv,
        "result": result,
        "error": None
        if error is None
        else {"code": UNAVAILABLE_ERROR, "message": error},
    }


def run_model(
    root: Path,
    route_name: str,
    provider: str,
    boundary: str,
    prompt_path: Path,
    cwd: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    lens: str | None = None,
) -> tuple[int, dict[str, object]]:
    if not boundary:
        raise ModelRouteError("model-run requires a dispatch boundary")
    route = resolve_route(root, route_name, provider, boundary, lens)
    if not route.required_contracts:
        raise ModelRouteError("dispatch boundary has no required contracts")
    contracts = _contracts(root, route.required_contracts)
    if timeout_seconds <= 0:
        raise ModelRouteError("timeout must be positive")
    try:
        invalid_prompt = (
            prompt_path.is_symlink()
            or not prompt_path.is_file()
            or prompt_path.stat().st_size > PROMPT_LIMIT
        )
    except OSError as error:
        raise ModelRouteError("prompt file could not be inspected") from error
    if invalid_prompt:
        raise ModelRouteError("prompt file must be a regular file no larger than 1 MiB")
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ModelRouteError("prompt file must be UTF-8") from error
    except OSError as error:
        raise ModelRouteError("prompt file could not be read") from error
    try:
        selected_cwd = (cwd or Path.cwd()).resolve()
    except OSError as error:
        raise ModelRouteError("cwd could not be resolved") from error
    if not selected_cwd.is_dir():
        raise ModelRouteError("cwd must be an existing directory")
    executable = shutil.which(provider)
    if executable is None:
        return 3, _outer(
            route,
            dry_run=dry_run,
            started=False,
            exit_code=None,
            argv=None,
            result=None,
            error=f"{provider} executable not found",
        )
    try:
        _preflight(route, executable, runner)
    except (ModelRouteError, OSError, subprocess.TimeoutExpired) as error:
        return 3, _outer(
            route,
            dry_run=dry_run,
            started=False,
            exit_code=None,
            argv=None,
            result=None,
            error=str(error),
        )
    schema_json = json.dumps(WORKER_SCHEMA, separators=(",", ":"), sort_keys=True)
    if dry_run:
        schema_value = "<schema-path>" if provider == "codex" else schema_json
        argv = _argv(
            route,
            "<provider-executable>",
            selected_cwd,
            schema_value,
            "<last-message-path>" if provider == "codex" else None,
        )
        return 0, _outer(
            route,
            dry_run=True,
            started=False,
            exit_code=None,
            argv=argv,
            result=None,
            error=None,
        )
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        try:
            if provider == "codex":
                temporary = tempfile.TemporaryDirectory(prefix="aitk-model-route-")
                schema_path = Path(temporary.name) / "worker-schema.json"
                schema_path.write_text(schema_json)
                os.chmod(schema_path, 0o600)
                schema_value = str(schema_path)
                last_message_path = Path(temporary.name) / "last-message.json"
            else:
                schema_value = schema_json
                last_message_path = None
        except OSError:
            return 3, _outer(
                route,
                dry_run=False,
                started=False,
                exit_code=None,
                argv=None,
                result=None,
                error="worker schema could not be prepared",
            )
        argv = _argv(
            route,
            executable,
            selected_cwd,
            schema_value,
            str(last_message_path) if last_message_path is not None else None,
            Path(temporary.name) if provider == "codex" and temporary else None,
        )
        process_cwd = (
            Path(temporary.name) if provider == "codex" and temporary else selected_cwd
        )
        try:
            process = runner(
                argv,
                input=worker_prompt(route, prompt, contracts, selected_cwd),
                cwd=process_cwd,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except OSError as error:
            return 3, _outer(
                route,
                dry_run=False,
                started=False,
                exit_code=None,
                argv=None,
                result=None,
                error=str(error),
            )
        except subprocess.TimeoutExpired as error:
            return 3, _outer(
                route,
                dry_run=False,
                started=True,
                exit_code=None,
                argv=None,
                result=None,
                error=str(error),
            )
        if process.returncode:
            return 3, _outer(
                route,
                dry_run=False,
                started=True,
                exit_code=process.returncode,
                argv=None,
                result=None,
                error="provider process failed",
            )
        try:
            if provider == "codex":
                if last_message_path is None or not last_message_path.is_file():
                    raise ModelRouteError(
                        "Codex did not write its final response", UNAVAILABLE_ERROR
                    )
                try:
                    last_message = last_message_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as error:
                    raise ModelRouteError(
                        "Codex final result could not be read", UNAVAILABLE_ERROR
                    ) from error
                result = parse_codex_output(process.stdout, last_message)
            else:
                result = parse_claude_output(process.stdout)
            # An unscored lane emits proposals, not severity-graded findings.
            # Anything it puts in `findings` is treated as a scored finding by
            # every downstream consumer, so a non-empty array is a contract
            # violation rather than a formatting slip -- fail the run instead of
            # letting it enter the fix queue.
            if route.unscored and result["findings"]:
                raise ModelRouteError(
                    f"unscored boundary {route.boundary} returned "
                    f"{len(result['findings'])} findings; this lane must return "
                    "an empty findings array"
                )
        except (ModelRouteError, json.JSONDecodeError) as error:
            return 3, _outer(
                route,
                dry_run=False,
                started=True,
                exit_code=0,
                argv=None,
                result=None,
                error=str(error),
            )
        result_exit = {
            "completed": 0,
            "blocked": BLOCKED_EXIT,
            "failed": FAILED_EXIT,
        }[result["status"]]
        return result_exit, _outer(
            route,
            dry_run=False,
            started=True,
            exit_code=0,
            argv=None,
            result=result,
            error=None,
        )
    finally:
        if temporary is not None:
            temporary.cleanup()
