"""Resolving one (route, provider, boundary, lens) request to a pinned dispatch.

The narrow waist of the subsystem: it reads a validated manifest, applies the
lens route floor, and returns the selector, effort, controls, and contract closure a
worker will run under. It never falls back to another model and never widens a
closure -- an unroutable request is an error, not a downgrade.
"""

from __future__ import annotations

from pathlib import Path

from typing import Iterable

from aitk.routing_policy import (
    COVERAGE_LEVELS,
    EnsembleLane,
    ModelRouteError,
    PROVIDERS,
    ResolvedEnsemble,
    ResolvedRoute,
    UNAVAILABLE_ERROR,
    _ensemble_map,
    _boundary_contracts,
    _lens_domain,
    _lens_menu,
    _lens_routes,
    _route_map,
    _summary_form,
)
from aitk.routing_closure import _required_contract_paths
from aitk.routing_manifest import load_model_routing


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
    # `--lens` only means something relative to a boundary's declared menu.
    # Accepting it without one used to resolve a route that silently ignored the
    # flag and exited 0, so a caller that meant to dispatch the adversarial lens
    # got an unnarrowed route and no signal that its selection was discarded.
    if lens is not None and boundary is None:
        raise ModelRouteError(
            "--lens names a lens of one dispatch boundary; pass --boundary too"
        )
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
        menu = _lens_menu(boundary_item)
        fans_out = bool(menu)
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
        # A boundary's `routes` list is the union its lanes may use, so set
        # membership alone lets an expensive lens resolve to the cheap route:
        # every fan-out boundary allows both `review` and `deep-review`, and the
        # adversarial lens -- whose own contract states it runs on `deep-review`
        # -- resolved to Opus/high without complaint. The floor is per lens and
        # lives in the manifest so the requirement is data the resolver enforces
        # rather than prose a dispatcher is trusted to have read.
        allowed = _lens_routes(payload).get(lens) if lens is not None else None
        if allowed is not None and route not in allowed:
            raise ModelRouteError(
                f"lens {lens} requires one of: {', '.join(allowed)}; "
                f"{route} is below its declared floor"
            )
        required_contracts = _required_contract_paths(
            root,
            boundary_item["path"],
            str(item["responsibility"]),
            boundary,
            lens,
            menu,
            _boundary_contracts(boundary_item),
        )
        unscored = bool(boundary_item.get("unscored", False))
        lens_domain = _lens_domain(boundary_item)
        summary_form = _summary_form(boundary_item)
    else:
        required_contracts = ()
        unscored = False
        lens_domain = None
        summary_form = None
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
        lens=lens,
        lens_domain=lens_domain,
        summary_form=summary_form,
    )


def _coverage_level(providers: tuple[str, ...], families: tuple[str, ...]) -> str:
    if len(set(providers)) > 1:
        return "provider-diverse"
    if len(set(families)) > 1:
        return "family-diverse"
    return "single-family"


def _lane(payload: dict[str, object], role: str, provider: str, route: str) -> EnsembleLane:
    item = _route_map(payload)[route]
    family = item["providers"][provider]["model"]
    return EnsembleLane(
        role=role,
        provider=provider,
        route=route,
        family=family,
        selector=payload["providers"][provider]["models"][family]["selector"],
        effort=payload["policy"]["efforts"][item["reasoning"]],
    )


def _unverifiable_clause(unverifiable: tuple[str, ...], diversity: str) -> str:
    if not unverifiable:
        return ""
    return (
        f"; no verifier meets {diversity} diversity for "
        f"{', '.join(unverifiable)}, so findings from those lanes stay unverified"
    )



def resolve_ensemble(
    root: Path,
    name: str,
    origin_provider: str,
    available_providers: Iterable[str] | None = None,
    engage_cross_provider: bool = False,
) -> ResolvedEnsemble:
    """Resolve one review tier into its exact provider/model roster.

    ``available_providers`` reports which provider CLIs the caller could
    actually reach. A missing cross provider never downgrades to a substitute
    model: the ensemble either continues with disclosed reduced coverage or
    blocks, per its ``on_degraded`` action.

    ``engage_cross_provider`` opts an ``optional`` tier into its cross lanes.
    Optional means opt-in, not automatic: without it a MODERATE review stays
    provider-local, which is what keeps the escalation ladder four tiers deep
    instead of collapsing MODERATE into STANDARD. It is distinct from the
    independent second-opinion *capability*, which is a same-provider lane.
    """

    payload = load_model_routing(root)
    if origin_provider not in PROVIDERS:
        raise ModelRouteError(f"unknown provider: {origin_provider}")
    entry = _ensemble_map(payload).get(name)
    if entry is None:
        raise ModelRouteError(f"unknown review ensemble: {name}")
    available = (
        set(PROVIDERS) if available_providers is None else set(available_providers)
    )
    if unknown := available - PROVIDERS:
        raise ModelRouteError(f"unknown provider: {sorted(unknown)[0]}")
    if origin_provider not in available:
        raise ModelRouteError(
            f"origin provider {origin_provider} is unavailable",
            UNAVAILABLE_ERROR,
        )
    cross_provider = next(iter(PROVIDERS - {origin_provider}))
    lens = tuple(
        _lane(payload, "lens", origin_provider, route)
        for route in entry["lens_routes"]
    )
    policy = str(entry["cross_provider"])
    engaged = policy == "required" or (policy == "optional" and engage_cross_provider)
    requested = tuple(
        (origin_provider if lane["provider"] == "origin" else cross_provider, lane["route"])
        for lane in entry["cross_lanes"]
    ) if engaged else ()
    cross = tuple(
        _lane(payload, "cross", provider, route)
        for provider, route in requested
        if provider in available
    )
    dropped = tuple(
        f"{provider}/{route}" for provider, route in requested if provider not in available
    )
    lanes = lens + cross
    coverage = _coverage_level(
        tuple(lane.provider for lane in lanes), tuple(lane.family for lane in lanes)
    )
    verification = dict(entry["verification"])
    # The verification pool is drawn from the providers this tier actually
    # engaged, not from everything reachable. A provider-local tier must not
    # reach across for its verifier — that would silently make MODERATE
    # provider-diverse and contradict the ladder.
    pool = tuple(
        _lane(payload, "verify", provider, route)
        for provider in sorted({lane.provider for lane in lanes})
        for route in sorted(set(entry["lens_routes"]) | {"review", "deep-review"})
    )
    # A tier whose verification contract cannot be satisfied by its own roster
    # (Codex has one model family, so a provider-local Codex tier can never meet
    # family diversity) must say so. Silently returning no verifier while
    # reporting full coverage is the same lie as claiming a lane that never ran.
    diversity = str(verification["diversity"])
    unverifiable = tuple(
        sorted(
            {
                f"{lane.provider}/{lane.family}"
                for lane in lanes
                if int(verification["lanes"]) > 0
                and not _verifier_candidates(pool, diversity, lane.provider, lane.family)
            }
        )
    )
    floor = str(entry["coverage_floor"])
    meets_floor = COVERAGE_LEVELS.index(coverage) >= COVERAGE_LEVELS.index(floor)
    on_degraded = str(entry["on_degraded"])
    # A dropped lane is always disclosed, even when the coverage floor is still
    # met: the caller asked for a lane and did not get it. Reporting "full"
    # there would claim ensemble coverage that never ran.
    if meets_floor and not dropped and not unverifiable:
        status, disclosure = "full", ""
    elif on_degraded == "block":
        status = "blocked"
        disclosure = (
            f"Model coverage: BLOCKED — {name} review requires {floor} coverage; "
            f"unavailable lane(s): {', '.join(dropped) or 'none'}"
            f"{_unverifiable_clause(unverifiable, diversity)}. "
            "No substitute model was used."
        )
    else:
        status = "degraded"
        comparison = (
            f"(reduced from {floor})"
            if not meets_floor
            else f"(floor {floor} met, but a requested lane was unavailable)"
        )
        disclosure = (
            f"Model coverage: {coverage} {comparison} — "
            f"unavailable lane(s): {', '.join(dropped) or 'none'}"
            f"{_unverifiable_clause(unverifiable, diversity)}. "
            "Model diversity was reduced; this run is not ensemble coverage."
        )
    return ResolvedEnsemble(
        name=name,
        origin_provider=origin_provider,
        cross_provider=cross_provider if engaged and cross_provider in available else None,
        cross_provider_policy=policy,
        lens_lanes=int(entry["lens_lanes"]),
        lens=lens,
        cross=cross,
        dropped_lanes=dropped,
        unverifiable_lanes=unverifiable,
        verification_lanes=int(verification["lanes"]),
        verifier_diversity=str(verification["diversity"]),
        verification_pool=pool,
        coverage_floor=floor,
        coverage=coverage,
        providers=tuple(sorted({lane.provider for lane in lanes})),
        families=tuple(sorted({lane.family for lane in lanes})),
        on_degraded=on_degraded,
        status=status,
        disclosure=disclosure,
    )


def _verifier_candidates(
    pool: tuple[EnsembleLane, ...],
    diversity: str,
    finding_provider: str,
    finding_family: str,
) -> list[EnsembleLane]:
    if diversity == "provider":
        candidates = [lane for lane in pool if lane.provider != finding_provider]
    else:
        candidates = [lane for lane in pool if lane.family != finding_family]
    return sorted(
        candidates,
        key=lambda lane: (lane.provider == finding_provider, lane.effort != "xhigh"),
    )


def select_verifiers(
    resolved: ResolvedEnsemble,
    finding_provider: str,
    finding_family: str,
) -> tuple[EnsembleLane, ...]:
    """Pick up to ``verification_lanes`` distinct verifier lanes for a finding.

    Every returned lane differs from the lane that raised the finding by the
    tier's diversity rule. Returns fewer lanes than the contract asks for — or
    none at all — when the roster cannot supply them; callers report the
    shortfall rather than padding it with the originating model.
    """

    if resolved.verifier_diversity == "none" or resolved.verification_lanes == 0:
        return ()
    if finding_provider not in PROVIDERS:
        raise ModelRouteError(f"unknown provider: {finding_provider}")
    # Validate the pair, not the two fields separately: a provider and a family
    # that each appear somewhere in the roster can still name a lane that never
    # ran (codex/fable), and verifying against a phantom raiser is exactly the
    # silent-substitution failure the diversity rule exists to prevent.
    known = {
        (lane.provider, lane.family)
        for lane in resolved.verification_pool + resolved.lens + resolved.cross
    }
    if (finding_provider, finding_family) not in known:
        raise ModelRouteError(
            f"unknown roster lane: {finding_provider}/{finding_family}"
        )
    candidates = _verifier_candidates(
        resolved.verification_pool,
        resolved.verifier_diversity,
        finding_provider,
        finding_family,
    )
    picked: list[EnsembleLane] = []
    seen: set[tuple[str, str]] = set()
    for lane in candidates:
        key = (lane.provider, lane.route)
        if key in seen:
            continue
        seen.add(key)
        picked.append(lane)
        if len(picked) == resolved.verification_lanes:
            break
    return tuple(picked)


def select_verifier(
    resolved: ResolvedEnsemble,
    finding_provider: str,
    finding_family: str,
) -> EnsembleLane | None:
    """Pick the single best verifier lane, or ``None`` when none qualifies.

    A convenience wrapper over :func:`select_verifiers` for the one-lane tiers.
    ``None`` means report the finding unverified — never reuse the originating
    model.
    """

    lanes = select_verifiers(resolved, finding_provider, finding_family)
    return lanes[0] if lanes else None

