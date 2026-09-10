"""Resolving one (route, provider, boundary, lens) request to a pinned dispatch.

The narrow waist of the subsystem: it reads a validated manifest, applies the
lens route floor, and returns the selector, effort, controls, and contract closure a
worker will run under. It never falls back to another model and never widens a
closure -- an unroutable request is an error, not a downgrade.
"""

from __future__ import annotations

from pathlib import Path

from aitk.routing_policy import (
    ModelRouteError,
    PROVIDERS,
    ResolvedRoute,
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
