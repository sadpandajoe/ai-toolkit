"""Loading and validating the routing manifest, fail-closed.

Everything that answers "is this manifest, and the documents it points at,
internally consistent" lives here: payload shape, seed-only closures, marker
placement, and selector ownership. These checks are the reason the resolver
can be small -- by the time a route resolves, the data it reads has already
been proven well-formed.
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
    _load,
    _route_map,
    _safe_dispatch_path,
    _safe_path,
)
from aitk.routing_markdown import (
    _contract_dependency_allowed,
    _markdown_lines,
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
    if responsibility != "review" or _boundary_contracts(boundary):
        return []
    seeds = set(_structural_seeds(root, str(boundary.get("path")), responsibility))
    if set(closure) <= seeds:
        return [
            f"review boundary resolves to structural seeds only: {identifier} "
            "-- declare its grading contracts in the boundary's `contracts` or "
            "the document's `## Required Context`"
        ]
    return []


# Every dispatch boundary's route allowlist ceiling is pinned here. Structural
# validation alone would let an edit widen an allowlist (adding `review` to
# `review.code-judo`, say) and still pass, silently defeating the fail-closed
# route pinning the skills advertise.
BOUNDARY_INVARIANTS = {
    "cherry-pick.batch-investigation": ("rca", "deep-rca"),
    "cherry-pick.headless-implementation": ("implementation",),
    "cherry-pick.scope-leak-rereview": ("review", "deep-review"),
    "cherry-pick.scope-leak-review": ("review", "deep-review"),
    "cherry-pick.unblock-discovery": ("review",),
    "cherry-pick.validate-scope-leak": ("review", "deep-review"),
    "cherry-pick.validate-scope-leak-rerun": ("review", "deep-review"),
    "create-feature.implement": ("implementation",),
    "create-feature.test-authoring": ("implementation",),
    "create-feature.review": ("review",),
    "create-feature.plan": ("planning",),
    "debug.ci-triage": ("rca", "deep-rca"),
    "evals.live-check": ("operations",),
    "feedback.comment-fix-groups": ("implementation",),
    "fix-bug.investigate": ("rca", "deep-rca"),
    "fix-bug.implement": ("implementation",),
    "fix-bug.test-authoring": ("implementation",),
    "fix-bug.review": ("review",),
    "fix-bug.plan": ("planning",),
    "fix-ci.investigate": ("rca", "deep-rca"),
    "fix-ci.implement": ("implementation",),
    "fix-ci.test-authoring": ("implementation",),
    "fix-ci.review": ("review",),
    "fix-ci.plan": ("planning",),
    "pgm.status-collection": ("operations",),
    "planning.decompose-work": ("planning",),
    "planning.loop-ownership": ("review", "deep-review"),
    "planning.loop-summary": ("review", "deep-review"),
    "planning.plan-phase": ("planning",),
    "planning.pm-brief-review": ("review", "deep-review"),
    "planning.technical-plan-review": ("review", "deep-review"),
    "qa.fresh-validation-judgment": ("review", "deep-review"),
    "qa.fresh-validation-evidence": ("operations",),
    "refactor.invariants": ("rca", "deep-rca"),
    "refactor.implement": ("implementation",),
    "refactor.review": ("review",),
    "refactor.plan": ("planning",),
    "review.adversarial-cross-provider-panel": ("deep-review",),
    "review.code-judo": ("deep-review",),
    "review.code-quality-final": ("review", "deep-review"),
    "review.delta-review": ("deep-review",),
    "review.local-cross-provider-cold": ("review", "deep-review"),
    "review.local-final-pass": ("deep-review",),
    "review.local-independent-capability": ("review",),
    "review.local-resolved-audit": ("deep-review",),
    "review.local-independent-second-opinion": ("review",),
    "review.local-primary-lanes": ("review", "deep-review"),
    "review.pr-batch": ("review", "deep-review"),
    "review.pr-cross-provider-cold": ("review", "deep-review"),
    "review.pr-lenses": ("review", "deep-review"),
    "review.pr-moderate": ("review", "deep-review"),
    "review.pr-standard": ("review", "deep-review"),
    "review.pr-trivial": ("review",),
    "review.sol-review": ("review",),
    "testing.test-authoring": ("implementation",),
    "workflows.adversarial-primary": ("deep-review",),
    "workflows.adversarial-second-opinion": ("deep-review",),
    "workflows.create-feature-implementation": ("implementation",),
    "workflows.create-feature-moderate-handoff": ("implementation",),
    "workflows.create-feature-moderate-implementation": ("implementation",),
    "workflows.create-feature-plan-review": ("review", "deep-review"),
    "workflows.feedback-fix-wave": ("implementation",),
    "workflows.fix-bug-implementation": ("implementation",),
    "workflows.review-code-fresh": ("review", "deep-review"),
    "workflows.review-code-orchestration": ("review", "deep-review"),
    "workflows.review-plan-fresh": ("review", "deep-review"),
    "workflows.review-plan-selected": ("review", "deep-review"),
    "workflows.review-pr-fresh": ("review", "deep-review"),
}


# Each ladder is the escalation chain a boundary's routes must stay within: a
# `review` lane may also offer `deep-review` (the same lane run deeper), but
# never `rca` or `operations` -- those are different failure-recovery chains
# entirely. `BOUNDARY_INVARIANTS` already pins each boundary's exact allowed
# subset, but it is a per-boundary allowlist, not a shape constraint, so nothing
# else stops a *new* invariant entry from mixing two chains (`("review",
# "operations")`, the shape `qa.fresh-validation` had before it was split into
# `qa.fresh-validation-judgment`/`-evidence`). This is the shape check that
# catches that class of mistake independent of what any one boundary happens to
# be pinned to.
ROUTE_LADDERS: dict[str, tuple[str, ...]] = {
    "review": ("review", "deep-review"),
    "deep-review": ("review", "deep-review"),
    "rca": ("rca", "deep-rca"),
    "deep-rca": ("rca", "deep-rca"),
    "implementation": ("implementation",),
    "operations": ("operations",),
    "planning": ("planning",),
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
    claude_native_workers_raw: object = None
    for provider in sorted(PROVIDERS):
        value = providers.get(provider) if isinstance(providers, dict) else None
        # `native_workers` is a claude-only extension: it names the templates
        # `routed_subagent`'s native dispatch resolves `(worker_id, effort)`
        # against, and only claude has native worker files under
        # `agents/claude/` today.
        catalog_keys = {"minimum_cli", "models"}
        allowed_keys = catalog_keys | {"native_workers"} if provider == "claude" else catalog_keys
        if (
            not isinstance(value, dict)
            or not catalog_keys <= set(value)
            or not set(value) <= allowed_keys
        ):
            problems.append(f"{provider}: invalid model catalog")
            continue
        if provider == "claude":
            claude_native_workers_raw = value.get("native_workers")
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
            "sonnet",
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
            "sonnet",
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
        "planning": (
            "standard",
            "operations",
            False,
            "sol",
            "read-only",
            "opus",
            "plan",
            ("Write", "Edit", "NotebookEdit"),
        ),
    }
    if seen_routes != ROUTE_NAMES or actual != expected:
        problems.append("model route vocabulary or invariant mapping mismatch")

    declared_routes = seen_routes

    # `native_workers` names every `(worker_id, effort)` a boundary's `workers`
    # map can resolve to -- one row per Claude-native worker file. Validated
    # here, after `declared_routes` exists, since a row's `route` must name a
    # real route.
    native_workers: dict[str, dict[str, object]] = {}
    if not isinstance(claude_native_workers_raw, dict) or not claude_native_workers_raw:
        problems.append("claude: invalid native_workers table")
    else:
        for worker_id, row in claude_native_workers_raw.items():
            if (
                not isinstance(worker_id, str)
                or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", worker_id) is None
                or not isinstance(row, dict)
                or set(row) != {"template", "route", "lens_domain"}
            ):
                problems.append(f"claude: invalid native worker entry: {worker_id}")
                continue
            template = row.get("template")
            route = row.get("route")
            lens_domain = row.get("lens_domain")
            if (
                _safe_path(root, template) is None
                or route not in declared_routes
                or (lens_domain is not None and lens_domain not in LENS_DOMAINS)
            ):
                problems.append(f"claude: invalid native worker entry: {worker_id}")
                continue
            native_workers[worker_id] = row

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
    lens_domain_required_reported: set[str] = set()
    for boundary in boundaries:
        if (
            not isinstance(boundary, dict)
            or not {"id", "path", "count", "routes", "workers"} <= set(boundary)
            or not set(boundary)
            <= {
                "id",
                "path",
                "count",
                "routes",
                "unscored",
                "lens_domain",
                "contracts",
                "summary_form",
                "workers",
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
        if not _valid_boundary_contracts(root, boundary):
            problems.append(f"invalid dispatch boundary contracts: {identifier}")
            continue
        # `routes_value` is non-empty and every member is a declared route by
        # this point, so `routes_value[0]` always keys `ROUTE_LADDERS`. The
        # reachable set is the ladder *suffix* starting at `routes_value[0]`,
        # not the full ladder: escalation only climbs (`review` ->
        # `deep-review`), never descends, so a boundary already anchored at
        # the top rung (`deep-review`-only lanes like `review.delta-review`)
        # reaches only itself, while one anchored at the base rung reaches
        # every rung above it.
        ladder = ROUTE_LADDERS.get(routes_value[0])
        reachable: tuple[str, ...] = ()
        if ladder is not None:
            reachable = ladder[ladder.index(routes_value[0]) :]
        if ladder is None or not set(routes_value) <= set(reachable):
            problems.append(f"dispatch boundary routes span more than one ladder: {identifier}")
            reachable = ()
        # `workers` resolves every ladder-reachable route to a
        # `(worker_id, effort)` identity -- baseline dispatch (`routes`) is
        # what this boundary offers today; escalation (`reachable`) is
        # whatever the ladder can climb to from there, and both must resolve
        # to a worker so a mid-loop escalation is never left without one. The
        # worker row itself must agree with the map: filed under the same
        # route it is mapped from, and grading the same artefact the boundary
        # declares.
        workers_value = boundary.get("workers")
        if not isinstance(workers_value, dict) or (
            reachable and set(workers_value) != set(reachable)
        ):
            problems.append(f"invalid dispatch boundary workers map: {identifier}")
        elif reachable:
            for route_name, worker_id in workers_value.items():
                worker_row = native_workers.get(worker_id) if isinstance(worker_id, str) else None
                if (
                    worker_row is None
                    or worker_row.get("route") != route_name
                    or worker_row.get("lens_domain") != _lens_domain(boundary)
                ):
                    problems.append(
                        f"dispatch boundary worker mismatch: {identifier}/{route_name}"
                    )
        for route_name in routes_value:
            route_item = _route_map(payload).get(route_name, {})
            responsibility = str(route_item.get("responsibility"))
            # A graded boundary (one with a `lens_domain`) must be a review
            # lane -- a lane that is not review has no gate/severity vocabulary
            # for `_domain_problem` to check its output against.
            if _lens_domain(boundary) is not None and responsibility != "review":
                problems.append(f"graded lens boundary is not a review lane: {identifier}")
            # The inverse: a review lane with no `lens_domain` has no output
            # vocabulary declared for it to be graded against.
            if (
                responsibility == "review"
                and _lens_domain(boundary) is None
                and identifier not in lens_domain_required_reported
            ):
                lens_domain_required_reported.add(identifier)
                problems.append(f"review boundary missing lens_domain: {identifier}")
            try:
                required_contracts = _required_contract_paths(
                    root,
                    str(boundary.get("path")),
                    responsibility,
                    identifier,
                    None,
                    (),
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
            # Every route at a boundary shares its responsibility in practice, so
            # report the lane once rather than once per route it offers.
            if identifier not in seed_only_reported:
                seed_only = _seed_only_problems(
                    root, boundary, responsibility, identifier, required_contracts
                )
                if seed_only:
                    seed_only_reported.add(identifier)
                    problems.extend(seed_only)
        # A ceiling, not an exact match: widening is the failure direction.
        # Narrowing a boundary to a subset of
        # its pinned routes is what scoping a lane means and stays free; adding
        # `review` to `review.code-judo` is the edit that silently defeats the
        # fail-closed pinning, and it is the one this rejects. An unpinned
        # boundary is rejected outright so a new lane cannot skip the table.
        pinned = BOUNDARY_INVARIANTS.get(identifier)
        if pinned is None or not set(routes_value) <= set(pinned):
            problems.append(f"dispatch boundary route allowlist mismatch: {identifier}")
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
    paths = list((root / "skills/goals/cherry-pick").rglob("*.md"))
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
                path == root / "skills/goals/cherry-pick/references/gate.md"
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
            if provider == "claude" and capability == "routed_subagent":
                # Native Task-tool dispatch to agents/claude/*.md workers for the
                # native roster roles — any routed boundary without a worker
                # file still needs the model-run shim, documented in
                # config/providers/claude.md.
                if not isinstance(binding, dict) or (
                    binding.get("mode"),
                    binding.get("fallback"),
                ) != ("native", None):
                    problems.append(f"{provider}/{capability}: must be native")
                continue
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
    return problems
