"""Deriving the exact contract list for one dispatch.

A routed worker runs with ambient skill loading disabled, so what reaches it is
exactly what this layer computes: the boundary's declared `contracts` and, on a
fan-out, the one selected lens. Nothing is walked or inferred from the Markdown:
a file reaches a worker only because the manifest names it for that lane, which
is what makes "what did this worker receive" answerable from the manifest alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from aitk.routing_policy import (
    ModelRouteError,
    PROMPT_LIMIT,
    _safe_path,
)


def _required_contract_paths(
    declared: tuple[str, ...],
    lens: str | None = None,
    lens_menu: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return the inline contract list for one dispatch lane.

    The lane's own `contracts` come first and the selected lens last, so lanes
    that share contracts share a prompt prefix. With no lens selected every menu
    lens is included, which is how check time proves each one exists. Whether
    the files exist is checked by the callers: the manifest check reports a
    missing boundary contract, and `_contracts` refuses one on the dispatch path.
    """
    lenses = (lens,) if lens is not None else tuple(lens_menu)
    return tuple(dict.fromkeys((*declared, *lenses)))


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
