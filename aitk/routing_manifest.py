"""Loading and validating the routing manifest, fail-closed.

Everything that answers "is this manifest, and the documents it points at,
internally consistent" lives here: payload shape, per-lens route floors, lens menu
completeness, seed-only closures, marker placement, and selector ownership. These
checks are the reason the resolver can be small -- by the time a route resolves, the
data it reads has already been proven well-formed.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from aitk.routing_policy import (
    CLAUDE_SELECTOR,
    CODEX_SELECTOR,
    DISALLOWED_TOOLS,
    DISPATCH_PATTERN,
    EXEMPT_MARKER,
    LENS_DOMAINS,
    LENS_DOMAIN_FLOORS,
    LENS_ROUTE_FLOORS,
    ModelRouteError,
    PERMISSION_MODES,
    PROVIDERS,
    REASONING,
    RESPONSIBILITIES,
    ROUTE_MARKER,
    ROUTE_NAMES,
    ROUTE_RESTRICTIONS,
    SANDBOXES,
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
from aitk.routing_markdown import (
    _catalog_lenses,
    _contract_dependency_allowed,
    _markdown_lines,
    _span_link_targets,
)
from aitk.routing_closure import (
    _required_contract_paths,
    _structural_seeds,
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
    """Check the declared per-lane contracts are distinct, existing Markdown files."""
    contracts = boundary.get("contracts")
    if contracts is None:
        return True
    if not isinstance(contracts, list) or not contracts:
        return False
    if len(set(map(repr, contracts))) != len(contracts):
        return False
    for contract in contracts:
        if not isinstance(contract, str) or not contract.endswith(".md"):
            return False
        safe = _safe_path(root, contract)
        if safe is None or not _contract_dependency_allowed(safe):
            return False
    return True


def _lens_route_problems(
    payload: dict[str, object],
    declared_routes: set[str],
    menu_owners: dict[str, list[tuple[str, tuple[str, ...]]]],
) -> list[str]:
    """Check that every declared route floor is satisfiable where its lens is offered.

    A floor that no boundary can honour is worse than no floor: the lens is on
    the menu, so an orchestrator picks it, and every dispatch then fails at
    resolve time. Catching it here keeps the failure at check time.

    The map is required and is checked against `LENS_ROUTE_FLOORS`. Treating it
    as optional meant `null`, `{}`, and a deleted entry each validated cleanly,
    so the guarantee "the adversarial lens never runs on the cheap route" could
    be removed by deleting the line that states it -- the one edit no reviewer
    reads as a change in behaviour. Widening a floor is the failure direction, so
    the manifest's allowed set for a pinned lens must stay within the pinned one;
    narrowing it further (or flooring an additional lens) is still free.
    """
    floors = payload.get("lens_routes")
    if not isinstance(floors, dict):
        return ["lens_routes must be an object"]
    if not floors:
        return ["lens_routes must not be empty"]
    problems: list[str] = []
    for lens, pinned in sorted(LENS_ROUTE_FLOORS.items()):
        declared = floors.get(lens)
        # Element types before the set comparison, for the reason spelled out in
        # the loop below: this reads the raw payload, not the coerced
        # `_lens_routes`, so a nested member reaches `set()` as written.
        if (
            not isinstance(declared, list)
            or not all(isinstance(route, str) for route in declared)
            or not set(declared) <= set(pinned)
        ):
            problems.append(
                f"lens route floor for {lens} must stay within: {', '.join(pinned)}"
            )
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

    The map is required, must cover every domain, and is checked against
    `LENS_DOMAIN_FLOORS`. Optional floors made the whole check self-deleting: an
    absent key, an empty object, or a dropped domain all validated, so the answer
    to "which lenses must every code menu offer?" could become "none" without a
    single check failing. Narrowing is the failure direction here -- the reverse
    of `lens_routes` -- so a declared floor must contain the pinned one.
    """
    raw = payload.get("lens_floors")
    if not isinstance(raw, dict):
        return ["lens_floors must be an object"]
    if not raw:
        return ["lens_floors must not be empty"]
    problems: list[str] = []
    floors = _lens_floors(payload)
    for domain in LENS_DOMAINS:
        pinned = LENS_DOMAIN_FLOORS.get(domain, ())
        if not set(pinned) <= set(floors.get(domain, ())):
            missing = sorted(set(pinned) - set(floors.get(domain, ())))
            problems.append(
                f"lens floor for {domain} drops pinned lenses: {', '.join(missing)}"
            )
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


def _seed_only_problems(
    root: Path,
    boundary: dict[str, object],
    responsibility: str,
    identifier: str,
    closure: tuple[str, ...],
) -> list[str]:
    """Reject a review lane whose closure is nothing but its structural seeds.

    A review worker needs a grading contract: the lens it applies, or the
    procedure it follows, or the severity vocabulary it reports in. The
    structural seeds carry none of that -- they are the policy rules, the owning
    skill, and the boundary document. A lane that adds nothing to them was
    dispatched with no instructions about what to look for, and it will still
    exit 0 and return confident-sounding prose, which is why this is checked
    rather than left to show up as a weak review.

    This is the check whose absence let thirteen boundaries lose their real
    contracts silently when span traversal narrowed: each kept resolving, kept
    passing validation, and only a full closure diff revealed the loss.

    A lane whose boundary document genuinely *is* its grading contract -- the
    Code-judo lens, the QA skill -- satisfies this by naming that document in its
    own `contracts`. The declaration adds nothing to the closure, which is the
    point: it turns "this lane needs nothing else" from an accident of the seed
    arithmetic into a claim someone wrote down and a reviewer can disagree with.
    """
    if (
        responsibility != "review"
        or _lens_menu(boundary)
        or _boundary_contracts(boundary)
    ):
        return []
    seeds = set(_structural_seeds(root, str(boundary.get("path")), responsibility))
    if set(closure) <= seeds:
        return [
            f"review boundary resolves to structural seeds only: {identifier} "
            "-- declare its grading contracts in the boundary's `contracts` or "
            "the document's `## Required Context`"
        ]
    return []


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
            "lens_routes",
            "lens_floors",
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
            efforts != {"light": "medium", "standard": "high", "deep": "xhigh"}
            or policy.get("automatic_max") is not False
            or policy.get("fallback") != "forbidden"
        ):
            problems.append(
                "model routing policy must use light/medium, standard/high, and "
                "deep/xhigh reasoning tiers with no max or fallback"
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
            "light",
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
    seed_only_reported: set[str] = set()
    menu_owners: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for boundary in boundaries:
        if (
            not isinstance(boundary, dict)
            or not {"id", "path", "count", "routes"} <= set(boundary)
            or not set(boundary)
            <= {
                "id",
                "path",
                "count",
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
        if not _valid_boundary_contracts(root, boundary):
            problems.append(f"invalid dispatch boundary contracts: {identifier}")
            continue
        for route_name in routes_value:
            route_item = _route_map(payload).get(route_name, {})
            responsibility = str(route_item.get("responsibility"))
            # Narrowing a fan-out span to one lens only happens on the review
            # route. A fan-out boundary on any other route would demand `--lens`
            # at dispatch, never scan its span, and drop the named lens without
            # a word -- reject the combination here rather than shipping it.
            if _lens_domain(boundary) is not None and responsibility != "review":
                problems.append(f"graded lens boundary is not a review lane: {identifier}")
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
                    _boundary_contracts(boundary),
                )
            except ModelRouteError as error:
                problems.append(str(error))
                continue
            if any(
                _safe_dispatch_path(root, contract) is None
                for contract in required_contracts
            ):
                problems.append(f"missing required boundary contract: {identifier}")
            problems.extend(
                _closure_floor_problems(
                    payload, boundary, identifier, route_name, required_contracts
                )
            )
            # Every route at a boundary shares its responsibility in practice, so
            # report the lane once rather than once per route it offers.
            if identifier not in seed_only_reported:
                seed_only = _seed_only_problems(
                    root, boundary, responsibility, identifier, required_contracts
                )
                if seed_only:
                    seed_only_reported.add(identifier)
                    problems.extend(seed_only)
        seen_ids.add(identifier)
        for lens in _lens_menu(boundary):
            menu_owners.setdefault(str(lens), []).append(
                (identifier, tuple(str(route) for route in routes_value))
            )
    problems.extend(_lens_route_problems(payload, declared_routes, menu_owners))
    problems.extend(_lens_floor_problems(root, payload))
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


def _lens_menu_problems(root: Path, declared: dict[str, dict[str, object]]) -> list[str]:
    """Report drift between declared reviewer menus and the dispatch prose.

    Both directions matter and they fail differently. A lens the manifest names
    but the span does not link cannot be dispatched -- `_contract_closure` fails
    closed on it, but only when someone happens to select it. A lens the span
    links but the manifest omits is worse and quieter: it used to ride into every
    worker's closure as a shared dependency, and now it is dropped from all of
    them, so the lane exists in prose and in no contract. Neither shows up in a
    passing route resolution, so both are caught here instead.
    """
    catalog, problems = _catalog_lenses(root)
    every_lens = catalog | {
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
