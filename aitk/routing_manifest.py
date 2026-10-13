"""Loading and validating the routing manifest, fail-closed.

Everything that answers "is this manifest, and the documents it points at,
internally consistent" lives here: payload shape, per-route write controls and
tool boxes, per-lane contract lists, parent-only contracts kept out of workers,
the manifest's own lens floors, and the marker bijection. The route table
itself (families, efforts, restrictions, boundary allowlists) lives only in
`interfaces/model-routing.json`. These checks are the reason the resolver can
be small -- by the time a route resolves, the data it reads has already been
proven well-formed. The fence-aware route marker
scan lives here too, since the marker inventory is the only thing the routing
layer still reads out of Markdown.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from aitk.routing_policy import (
    CRITIC_EXCLUDED_CONTRACTS,
    DISALLOWED_TOOLS,
    LENS_DOMAINS,
    ModelRouteError,
    PARENT_ONLY_CONTRACTS,
    PERMISSION_MODES,
    PROJECT_FILE_INSTRUCTION,
    PROVIDERS,
    REASONING,
    RESPONSIBILITIES,
    ROUTE_CONTROLS,
    ROUTE_MARKER,
    ROUTE_TOOLS,
    SANDBOXES,
    TOOL_ENTRY,
    SUMMARY_FORMS,
    _boundary_contracts,
    _lens_domain,
    _lens_floors,
    _lens_menu,
    _lens_routes,
    _load,
    _route_map,
    _safe_dispatch_path,
    _safe_path,
)
from aitk.routing_closure import _required_contract_paths

# Efforts a route may pin. `max` runs only on an explicit user ask, recorded in
# the envelope, so it is never a route default.
ROUTE_EFFORTS = ("low", "medium", "high", "xhigh")


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


def _route_markers(text: str) -> list[str]:
    """Every route marker id in a document, in order, skipping fenced examples."""
    return [
        match.group(1)
        for _, line in _markdown_content_lines(text)
        if (match := ROUTE_MARKER.fullmatch(line.strip())) is not None
    ]


def _require_route_marker(root: Path, boundary_path: str, boundary_id: str) -> None:
    """Fail closed on a boundary document that no longer dispatches this lane.

    The document is the parent's procedure and nothing in it is inlined, but it
    must still carry this lane's route marker. Loading the manifest checks it
    for every boundary, so `resolve_route` never hands back a launchable route
    for a lane the prose no longer dispatches; `validate_dispatch_boundaries`
    adds the reverse direction (no stray or duplicate marker) at check time.
    """
    source = root / boundary_path
    if not source.is_file() or source.is_symlink():
        # An optional extension that is not installed has no document to read;
        # `_safe_dispatch_path` already decided that is acceptable.
        return
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ModelRouteError(
            f"boundary document could not be read: {boundary_path}"
        ) from error
    if boundary_id not in _route_markers(content):
        raise ModelRouteError(f"missing route marker: {boundary_path}/{boundary_id}")


def _contract_dependency_allowed(path: Path) -> bool:
    if not path.parts:
        return False
    if path.parts[0] in {"rules", "skills"}:
        return True
    # Provider-neutral specialist contracts (reviewer, RCA, plan validator) are
    # inlined into cross-provider workers the same way a skill reference is.
    if len(path.parts) == 3 and path.parts[:2] == ("agents", "specialists"):
        return True
    return (
        len(path.parts) >= 4
        and path.parts[0] == "extensions"
        and path.parts[2] == "skills"
    )


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


def _valid_lens_menu(root: Path, boundary: dict[str, object]) -> bool:
    """Check the declared reviewer menu, which is what makes a boundary fan out.

    A boundary with a menu must name at least two distinct, existing reviewer
    lens documents; a single-entry menu is a fan-out with nothing to select
    between and is almost always a half-finished edit. It must also declare the
    domain it grades, because a menu is the one place a lens is selected by name
    and a dual-use lens has no other signal for which vocabulary to answer in.

    A boundary with no menu is fine -- it simply does not fan out, and
    `resolve_route` rejects `--lens` there. It may still declare a domain: a lane
    that applies its lenses itself grades the same artefact a fan-out would.
    """
    lenses = boundary.get("lenses")
    if lenses is None:
        return True
    if not isinstance(lenses, list) or len(lenses) < 2:
        return False
    if _lens_domain(boundary) is None:
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


def _valid_boundary_contracts(root: Path, boundary: dict[str, object]) -> bool:
    """Check the lane's contract list: present, non-empty, distinct Markdown paths.

    Every boundary declares its worker's contracts; nothing is inherited from the
    boundary document any more, so a lane without a list would dispatch a worker
    with no instructions at all. A listed file that does not exist is reported
    separately, as a missing boundary contract, once the closure is derived.
    """
    contracts = boundary.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return False
    if len(set(map(repr, contracts))) != len(contracts):
        return False
    for contract in contracts:
        if not isinstance(contract, str) or not contract.endswith(".md"):
            return False
        path = Path(contract)
        if path.is_absolute() or ".." in path.parts:
            return False
        if not _contract_dependency_allowed(path):
            return False
        if (root / path).exists() and _safe_path(root, contract) is None:
            return False
    return True


def _worker_contract_problems(
    root: Path,
    identifier: str,
    responsibility: str,
    closure: tuple[str, ...],
) -> list[str]:
    """Reject a closure that hands a worker the parent's own instructions.

    Every worker is refused the routing policy and the handoff rules: they tell
    the reader how to dispatch and brief workers. A critic (any review-route
    lane: reviewer, second family, verifier, deep lens, plan validator,
    adversarial lens) is also refused the parent's review procedure and the gate
    rules, and any file that tells it to read `PROJECT.md` first, because each
    of those carries the parent's view of the work into a lane whose value is
    that it does not have one.
    """
    excluded = (
        CRITIC_EXCLUDED_CONTRACTS if responsibility == "review" else PARENT_ONLY_CONTRACTS
    )
    problems = [
        f"boundary {identifier} hands its worker a parent-only contract: {contract}"
        for contract in closure
        if contract in excluded
    ]
    if responsibility == "review":
        for contract in closure:
            source = root / contract
            if not source.is_file() or source.is_symlink():
                continue
            try:
                text = source.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if PROJECT_FILE_INSTRUCTION.search(text):
                problems.append(
                    f"boundary {identifier} hands a critic a contract that sends it "
                    f"to PROJECT.md: {contract}"
                )
    return problems


def _lens_route_problems(
    payload: dict[str, object],
    declared_routes: set[str],
    menu_owners: dict[str, list[tuple[str, tuple[str, ...]]]],
) -> list[str]:
    """Check that every declared route floor is satisfiable where its lens is offered.

    A floor that no boundary can honour is worse than no floor: the lens is on
    the menu, so an orchestrator picks it, and every dispatch then fails at
    resolve time. Catching it here keeps the failure at check time. The floors
    themselves are data in the manifest.
    """
    floors = payload.get("lens_routes")
    if not isinstance(floors, dict):
        return ["lens_routes must be an object"]
    if not floors:
        return ["lens_routes must not be empty"]
    problems: list[str] = []
    for lens, allowed in floors.items():
        if (
            not isinstance(lens, str)
            or not isinstance(allowed, list)
            or not allowed
            # Element type first, and only then the duplicate and membership
            # checks. `set(allowed)` raises on an unhashable member, so a floor
            # written as `{"a.md": [{"route": "deep-review"}]}` used to crash the
            # validator with a TypeError instead of being reported as the
            # malformed manifest it is -- fail-closed means a bad manifest gets a
            # problem string, not a traceback.
            or not all(isinstance(route, str) for route in allowed)
            or len(set(allowed)) != len(allowed)
            or any(route not in declared_routes for route in allowed)
        ):
            problems.append(f"invalid lens route floor: {lens}")
            continue
        if lens not in menu_owners:
            problems.append(f"lens route floor names no menu lens: {lens}")
            continue
        for identifier, routes_value in menu_owners[lens]:
            if not set(allowed) & set(routes_value):
                problems.append(
                    f"boundary {identifier} offers lens {lens} but allows none of "
                    f"its required routes: {', '.join(allowed)}"
                )
    return problems


def _lens_floor_problems(root: Path, payload: dict[str, object]) -> list[str]:
    """Check that every fan-out menu contains its domain's declared lens floor.

    Containment against the classifier's universe plus completeness across the
    union of all menus leaves one hole: drop a lens from one boundary and the
    sibling menus keep the union whole, so the lane is unreachable in exactly one
    workflow and nothing complains. The floor closes it per boundary.

    The floors themselves are data in the manifest.
    """
    raw = payload.get("lens_floors")
    if not isinstance(raw, dict):
        return ["lens_floors must be an object"]
    if not raw:
        return ["lens_floors must not be empty"]
    problems: list[str] = []
    floors = _lens_floors(payload)
    for domain, declared in raw.items():
        if (
            not isinstance(domain, str)
            or domain not in LENS_DOMAINS
            or not isinstance(declared, list)
            or not declared
            or not all(isinstance(lens, str) for lens in declared)
            or len(set(declared)) != len(declared)
            or any(
                _safe_dispatch_path(root, lens) is None for lens in declared
            )
        ):
            problems.append(f"invalid lens floor: {domain}")
    boundaries = payload.get("dispatch_boundaries")
    if not isinstance(boundaries, list):
        return problems
    for boundary in boundaries:
        if not isinstance(boundary, dict):
            continue
        domain = _lens_domain(boundary)
        menu = _lens_menu(boundary)
        # The floor is a floor on *menus*. A lane that grades a domain without
        # fanning out has no menu to floor -- demanding it list all eight code
        # lenses would demand a selection nothing can make.
        if not menu:
            continue
        floor = floors.get(domain) if domain is not None else None
        if not floor or f"invalid lens floor: {domain}" in problems:
            continue
        missing = sorted(set(floor) - set(menu))
        if missing:
            problems.append(
                f"boundary {boundary.get('id')} omits {domain} lens floor entries: "
                f"{', '.join(missing)}"
            )
    return problems


def _closure_floor_problems(
    payload: dict[str, object],
    boundary: dict[str, object],
    identifier: str,
    route_name: str,
    closure: tuple[str, ...],
) -> list[str]:
    """Apply each lens's route floor to a lane that inlines the lens directly.

    `resolve_route` enforces `lens_routes` against the lens named by `--lens`,
    which only exists on a fan-out boundary. A lane that applies its lenses
    itself never passes `--lens`, so it inlined the adversarial lens and ran it
    on `review` with nothing objecting -- the floor was bypassed not by
    overriding it but by taking a code path it was never wired into.

    Only menu-less lanes are checked. On a fan-out boundary, check-time closure
    is computed with `lens=None` and deliberately contains *every* menu lens, so
    the same rule there would demand each boundary satisfy the strictest floor on
    its menu and reject all four fan-out lanes. Those are already covered per
    dispatch by the resolver, which is where exactly one lens is selected.
    """
    if _lens_menu(boundary):
        return []
    floors = _lens_routes(payload)
    return [
        f"boundary {identifier} inlines {contract} on {route_name}, below its "
        f"declared floor: {', '.join(floors[contract])}"
        for contract in closure
        if contract in floors and route_name not in floors[contract]
    ]


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
            "lens_routes",
            "lens_floors",
        }
        or type(payload.get("version")) is not int
        or payload.get("version") != 1
    ):
        return ["interfaces/model-routing.json does not match schema version 1"]
    problems: list[str] = []
    providers = payload.get("providers")
    if not isinstance(providers, dict) or set(providers) != PROVIDERS:
        problems.append("model routing providers must contain exactly codex and claude")
        providers = {}
    # A family is valid when the catalog names it with a selector; which
    # families exist, and which selector each runs, is the manifest's call.
    provider_models: dict[str, dict[str, str]] = {}
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
        if not isinstance(models, dict) or not models:
            problems.append(f"{provider}: model catalog must name at least one family")
            continue
        provider_models[provider] = {}
        for family, model in models.items():
            selector = model.get("selector") if isinstance(model, dict) else None
            if (
                not isinstance(model, dict)
                or set(model) != {"selector"}
                or not isinstance(selector, str)
                or not selector.strip()
                or selector in selectors
            ):
                problems.append(f"{provider}/{family}: invalid or duplicate selector")
                continue
            selectors.add(selector)
            provider_models[provider][family] = selector

    policy = payload.get("policy")
    if not isinstance(policy, dict) or set(policy) != {"efforts", "orchestrator"}:
        problems.append("invalid model routing policy")
    else:
        efforts = policy.get("efforts")
        if (
            not isinstance(efforts, dict)
            or set(efforts) != {"standard", "deep"}
            or any(value not in ROUTE_EFFORTS for value in efforts.values())
        ):
            problems.append("model routing policy efforts must name standard and deep")
        # The parent session is the orchestrator; the manifest records its family
        # per provider so docs and evals can name it.
        orchestrator = policy.get("orchestrator")
        if not isinstance(orchestrator, dict) or set(orchestrator) != PROVIDERS or any(
            not isinstance(orchestrator.get(provider), str)
            or orchestrator[provider] not in provider_models.get(provider, {})
            for provider in PROVIDERS
        ):
            problems.append("model routing orchestrator must name a catalog family per provider")

    routes = payload.get("routes")
    if not isinstance(routes, list):
        problems.append("model routes must be a list")
        routes = []
    seen_routes: set[str] = set()
    for route in routes:
        if not isinstance(route, dict) or set(route) != {
            "name",
            "reasoning",
            "effort",
            "tools",
            "responsibility",
            "restrictions",
            "providers",
        }:
            problems.append("invalid model route entry")
            continue
        name = route.get("name")
        reasoning = route.get("reasoning")
        responsibility = route.get("responsibility")
        restrictions = route.get("restrictions")
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
        # Every route pins its effort (D16): a provider default differs by model
        # and surface. `max` is never automatic, so no route may name it.
        effort = route.get("effort")
        if effort not in ROUTE_EFFORTS:
            problems.append(f"{name}: effort must be one of {', '.join(ROUTE_EFFORTS)}")
        if (
            not isinstance(restrictions, list)
            or not restrictions
            or any(not isinstance(item, str) or not item for item in restrictions)
        ):
            problems.append(f"{name}: restrictions must be nonempty strings")
        # The tool box and the write controls are pinned in policy: a read-only
        # route that quietly gained Edit, a sandbox, or a permission mode is a
        # widening no reviewer reads as a behaviour change in a JSON diff.
        tools = route.get("tools")
        if (
            not isinstance(tools, list)
            or not tools
            or any(
                not isinstance(item, str) or TOOL_ENTRY.fullmatch(item) is None
                for item in tools
            )
            or len(set(tools)) != len(tools)
        ):
            problems.append(f"{name}: tools must be distinct tool names or read-only git rules")
        elif tuple(tools) != ROUTE_TOOLS.get(name):
            problems.append(f"{name}: tools do not match policy")
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
        controls = (
            codex.get("sandbox"),
            claude.get("permission_mode"),
            tuple(claude.get("disallowed_tools", [])),
        )
        if controls != ROUTE_CONTROLS.get(name):
            problems.append(f"{name}: sandbox and permission controls do not match policy")

    declared_routes = seen_routes
    boundaries = payload.get("dispatch_boundaries")
    if not isinstance(boundaries, list):
        problems.append("dispatch_boundaries must be a list")
        boundaries = []
    seen_ids: set[str] = set()
    menu_owners: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for boundary in boundaries:
        if (
            not isinstance(boundary, dict)
            or not {"id", "path", "routes"} <= set(boundary)
            or not set(boundary)
            <= {
                "id",
                "path",
                "routes",
                "unscored",
                "lens_domain",
                "lenses",
                "contracts",
                "summary_form",
            }
            or type(boundary.get("unscored", False)) is not bool
            # A present `lens_domain` must name a known domain so a shared lens
            # can tell which output vocabulary this lane expects. Absent means
            # the lane grades nothing the runner can check.
            or boundary.get("lens_domain", "code") not in LENS_DOMAINS
            # `summary_form` names a grammar authored in `routing_policy.py`; a
            # name with no grammar behind it would be a contract the boundary
            # declares and the runner silently never applies.
            or boundary.get("summary_form", next(iter(SUMMARY_FORMS))) not in SUMMARY_FORMS
        ):
            problems.append("invalid dispatch boundary entry")
            continue
        identifier = boundary.get("id")
        routes_value = boundary.get("routes")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", identifier) is None
            or identifier in seen_ids
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
        # it implicit in the dispatch prose. The manifest is what `resolve_route`
        # checks `--lens` against, so an omitted lens is a rejected dispatch
        # instead of a lane that quietly does not exist.
        if not _valid_lens_menu(root, boundary):
            problems.append(f"invalid dispatch boundary lens menu: {identifier}")
            continue
        if not _valid_boundary_contracts(root, boundary):
            problems.append(f"invalid dispatch boundary contracts: {identifier}")
            continue
        try:
            _require_route_marker(root, str(boundary.get("path")), identifier)
        except ModelRouteError as error:
            problems.append(str(error))
        worker_reported = False
        for route_name in routes_value:
            route_item = _route_map(payload).get(route_name, {})
            responsibility = str(route_item.get("responsibility"))
            # Narrowing a fan-out to one lens only happens on the review route.
            # A graded boundary on any other route would demand `--lens` at
            # dispatch and drop the named lens without a word -- reject the
            # combination here rather than shipping it.
            if _lens_domain(boundary) is not None and responsibility != "review":
                problems.append(f"graded lens boundary is not a review lane: {identifier}")
            # `lens` is deliberately omitted: check time verifies the
            # unnarrowed union, so every menu lens is proven to exist. Dispatch
            # time is where exactly one gets selected.
            required_contracts = _required_contract_paths(
                _boundary_contracts(boundary), None, _lens_menu(boundary)
            )
            missing = [
                contract
                for contract in required_contracts
                if _safe_dispatch_path(root, contract) is None
            ]
            if missing:
                problems.append(
                    f"missing required boundary contract: {identifier}: "
                    f"{', '.join(missing)}"
                )
            problems.extend(
                _closure_floor_problems(
                    payload, boundary, identifier, route_name, required_contracts
                )
            )
            # Every route at a boundary shares its responsibility in practice, so
            # report the lane once rather than once per route it offers.
            if not worker_reported:
                worker_problems = _worker_contract_problems(
                    root, identifier, responsibility, required_contracts
                )
                if worker_problems:
                    worker_reported = True
                    problems.extend(worker_problems)
        seen_ids.add(identifier)
        for lens in _lens_menu(boundary):
            menu_owners.setdefault(str(lens), []).append(
                (identifier, tuple(str(route) for route in routes_value))
            )
    problems.extend(_lens_route_problems(payload, declared_routes, menu_owners))
    problems.extend(_lens_floor_problems(root, payload))
    return problems


def validate_model_routing(root: Path) -> list[str]:
    try:
        payload = _load(root / "interfaces/model-routing.json")
    except (OSError, json.JSONDecodeError) as error:
        return [str(error)]
    problems = _validate_payload(root, payload)
    if isinstance(payload, dict) and not problems:
        problems.extend(validate_dispatch_boundaries(root, payload))
        problems.extend(validate_route_bindings(root))
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
        # Same-provider workers are native subagents (the toolkit's installed
        # agent roster), so `fresh_subagent` may be native. Independent review
        # and every routed specialist still cross the source-linked transport:
        # that is the boundary that pins model, effort, sandbox, and contract
        # closure, and a generic worker must not be able to stand in for it.
        for capability in ("independent_review", "routed_subagent"):
            binding = bindings.get(capability) if isinstance(bindings, dict) else None
            if not isinstance(binding, dict) or (
                binding.get("mode"),
                binding.get("fallback"),
            ) != ("fallback", "source_linked_model_run"):
                problems.append(
                    f"{provider}/{capability}: must use source_linked_model_run"
                )
        binding = bindings.get("fresh_subagent") if isinstance(bindings, dict) else None
        if not isinstance(binding, dict) or binding.get("mode") not in {"native", "fallback"} or (
            binding.get("mode") == "fallback"
            and binding.get("fallback") != "source_linked_model_run"
        ):
            problems.append(
                f"{provider}/fresh_subagent: must be native or source_linked_model_run"
            )
    return problems


def validate_dispatch_boundaries(root: Path, payload: dict[str, object]) -> list[str]:
    """Hold the route markers and the declared boundaries in a bijection.

    Each declared boundary's document carries its marker exactly once, and every
    marker in a skill document names a declared boundary at that path. Markers
    inside fenced examples are documentation and are not counted.
    """
    declared = {
        item["id"]: item
        for item in payload["dispatch_boundaries"]
        if (root / item["path"]).is_file()
    }
    route_counts: dict[tuple[str, str], int] = {}
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
        for marker in _route_markers(path.read_text(encoding="utf-8", errors="replace")):
            key = (relative, marker)
            route_counts[key] = route_counts.get(key, 0) + 1
    for (path_value, identifier), count in sorted(route_counts.items()):
        item = declared.get(identifier)
        if item is None or item["path"] != path_value or count != 1:
            problems.append(
                f"unknown, misplaced, or duplicate route marker: {path_value}/{identifier}"
            )
    for identifier, item in sorted(declared.items()):
        if route_counts.get((item["path"], identifier), 0) != 1:
            problems.append(f"missing route marker: {item['path']}/{identifier}")
    return problems
