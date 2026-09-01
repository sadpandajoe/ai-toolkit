"""Resolving one (route, provider, boundary) request to a pinned dispatch.

The narrow waist of the subsystem: it reads a validated manifest and returns
the selector, effort, controls, and contract closure a worker will run under.
It never falls back to another model and never widens a closure -- an
unroutable request is an error, not a downgrade.
"""

from __future__ import annotations

from pathlib import Path

from aitk.routing_policy import (
    ModelRouteError,
    PROVIDERS,
    ResolvedRoute,
    _boundary_contracts,
    _lens_domain,
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
    # The reviewer-lens fan-out mechanism is retired: no dispatch boundary
    # fans out over a menu any more, so naming a lens is always a caller
    # error rather than a narrowing request. Rejecting it here, rather than
    # silently ignoring it, documents that the mechanism is gone instead of
    # letting a stale lens argument pass through as a silent no-op.
    if lens is not None:
        raise ModelRouteError(
            "the reviewer-lens argument is retired; no dispatch boundary "
            "fans out over reviewer lenses"
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
        required_contracts = _required_contract_paths(
            root,
            boundary_item["path"],
            str(item["responsibility"]),
            boundary,
            None,
            (),
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
        lens=None,
        lens_domain=lens_domain,
        summary_form=summary_form,
    )
