"""Validated model/effort routing and fail-closed provider CLI workers.

Facade over the routing layers. The subsystem is five concerns stacked in
dependency order, and this module re-exports them under the import path callers
already use:

- `routing_policy` -- the vocabulary: enumerations, patterns, errors, `ResolvedRoute`
- `routing_markdown` -- reading route markers and Required Context out of documents
- `routing_closure` -- deriving what one dispatch actually receives
- `routing_manifest` -- loading and validating the manifest, fail-closed
- `routing_resolver` -- one request to one pinned dispatch
- `routing_transport` -- running that dispatch as a provider CLI worker

Nothing is defined here. Import from a layer directly when the dependency is worth
stating; import from this facade when the caller just wants "the routing subsystem".
"""

from __future__ import annotations

from aitk.routing_closure import (
    _contract_closure,
    _contracts,
    _required_contract_paths,
    _structural_seeds,
)
from aitk.routing_manifest import (
    load_model_routing,
    validate_dispatch_boundaries,
    validate_legacy_route_prose,
    validate_model_routing,
    validate_route_bindings,
    validate_selector_ownership,
)
from aitk.routing_markdown import (
    _catalog_lenses,
    _marker_present,
    _marker_span_text,
    _markdown_content_lines,
    _markdown_lines,
    _required_context_text,
    _span_link_targets,
)
from aitk.routing_policy import (
    BLOCKED_EXIT,
    CLAUDE_SELECTOR,
    CODEX_SELECTOR,
    DEFAULT_TIMEOUT,
    DISALLOWED_TOOLS,
    DISPATCH_PATTERN,
    EXEMPT_MARKER,
    FAILED_EXIT,
    LENS_CATALOG,
    LENS_DOMAINS,
    PERMISSION_MODES,
    PREFLIGHT_TIMEOUT,
    PROMPT_LIMIT,
    PROVIDERS,
    REASONING,
    RESPONSIBILITIES,
    ROUTE_ERROR,
    ROUTE_MARKER,
    ROUTE_NAMES,
    ROUTE_RESTRICTIONS,
    SANDBOXES,
    UNAVAILABLE_ERROR,
    WORKER_SCHEMA,
    ModelRouteError,
    ResolvedRoute,
    _safe_path,
)
from aitk.routing_resolver import resolve_route
from aitk.routing_transport import (
    _valid_worker,
    parse_claude_output,
    parse_codex_output,
    run_model,
    worker_prompt,
)


__all__ = [
    "BLOCKED_EXIT",
    "CLAUDE_SELECTOR",
    "CODEX_SELECTOR",
    "DEFAULT_TIMEOUT",
    "DISALLOWED_TOOLS",
    "DISPATCH_PATTERN",
    "EXEMPT_MARKER",
    "FAILED_EXIT",
    "LENS_CATALOG",
    "LENS_DOMAINS",
    "PERMISSION_MODES",
    "PREFLIGHT_TIMEOUT",
    "PROMPT_LIMIT",
    "PROVIDERS",
    "REASONING",
    "RESPONSIBILITIES",
    "ROUTE_ERROR",
    "ROUTE_MARKER",
    "ROUTE_NAMES",
    "ROUTE_RESTRICTIONS",
    "SANDBOXES",
    "UNAVAILABLE_ERROR",
    "WORKER_SCHEMA",
    "ModelRouteError",
    "ResolvedRoute",
    "load_model_routing",
    "parse_claude_output",
    "parse_codex_output",
    "resolve_route",
    "run_model",
    "validate_dispatch_boundaries",
    "validate_legacy_route_prose",
    "validate_model_routing",
    "validate_route_bindings",
    "validate_selector_ownership",
    "worker_prompt",
    # Underscored, and re-exported deliberately: the routing tests exercise the
    # markdown scanners, the closure traversal, and the worker-result schema
    # directly, because each is a fail-closed rule whose behavior is not
    # observable from `resolve_route`'s return value alone.
    "_catalog_lenses",
    "_contract_closure",
    "_contracts",
    "_marker_present",
    "_marker_span_text",
    "_markdown_content_lines",
    "_markdown_lines",
    "_required_contract_paths",
    "_required_context_text",
    "_safe_path",
    "_span_link_targets",
    "_structural_seeds",
    "_valid_worker",
]
