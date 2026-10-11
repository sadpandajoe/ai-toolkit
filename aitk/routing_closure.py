"""Deriving the exact contract list for one dispatch.

A routed worker runs with ambient skill loading disabled, so what reaches it is
exactly what this layer computes: the boundary's declared `contracts`, the one
selected lens, and what those declare in their own `## Required Context`. Keeping
the derivation here -- separate from the validation that checks a manifest and the
transport that ships a prompt -- is what makes "what did this worker receive"
answerable without reading either.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from aitk.routing_policy import (
    BACKTICK_MARKDOWN_PATH,
    MARKDOWN_LINK,
    ModelRouteError,
    PROMPT_LIMIT,
    _safe_path,
)
from aitk.routing_markdown import (
    _contract_dependency_allowed,
    _marker_present,
    _marker_span_text,
    _required_context_text,
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


def _structural_seeds(
    root: Path,
    boundary_path: str,
    responsibility: str,
) -> tuple[str, ...]:
    """Return the files a boundary of this shape used to inherit implicitly.

    Derived from the boundary's path and route responsibility alone: the routing
    policy, the handoff rules, the owning skill, the route's discipline contract
    and the boundary document. None of them is inlined any more -- a worker
    receives only its declared `contracts` -- but `_seed_only_problems` still uses
    this set as the floor a review lane's closure must rise above.
    """
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
        # away from the QA, PM, plan-validation, and cherry-pick scope-leak lanes
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
        "planning": "skills/planning/SKILL.md",
        "rca": "skills/debug/SKILL.md",
        "operations": owner.as_posix(),
    }.get(responsibility)
    if route_contract is None:
        raise ModelRouteError(f"unknown contract responsibility: {responsibility}")
    values = (
        "rules/model-assignment.md",
        # Every worker returns the same compact handoff and never carries the
        # parent transcript; the handoff contract is small enough to ride along
        # with every route.
        "rules/specialist-handoff.md",
        owner.as_posix(),
        route_contract,
        path.as_posix(),
    )
    return tuple(dict.fromkeys(values))


def _resolve_reference(
    root: Path,
    source: Path,
    target_text: str,
    is_link: bool,
) -> tuple[str | None, list[str]]:
    """Resolve one Markdown reference to a repository-relative contract path.

    Returns the resolved path when it names an allowed, existing, non-symlinked
    Markdown file, otherwise `None` plus the allowed paths it could have meant, so
    the caller can tell "a link to something outside the contract tree" (ignored)
    from "a declared dependency that is missing" (fail closed).
    """
    target_path = Path(target_text)
    if is_link:
        possible: tuple[Path, ...] = (source.parent / target_path,)
    else:
        root_relative = [root / target_path]
        if len(target_path.parts) >= 2:
            root_relative.append(root / "skills" / target_path)
        root_relative.append(source.parent / target_path)
        possible = tuple(root_relative)
    allowed_paths: list[str] = []
    for candidate in possible:
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if not _contract_dependency_allowed(relative):
            continue
        if resolved.is_file() and not resolved.is_symlink() and resolved.suffix == ".md":
            return relative.as_posix(), []
        allowed_paths.append(relative.as_posix())
    return None, allowed_paths


def _references(text: str) -> list[tuple[str, bool]]:
    """Every Markdown link and backticked `.md` path in `text`, in order."""
    found: list[tuple[str, bool]] = []
    found.extend((match.group(1), True) for match in MARKDOWN_LINK.finditer(text))
    found.extend(
        (match.group(1), False) for match in BACKTICK_MARKDOWN_PATH.finditer(text)
    )
    result: list[tuple[str, bool]] = []
    for raw_target, is_link in found:
        target_text = raw_target.strip().strip("<>").split("#", 1)[0]
        if not target_text or "://" in target_text or target_text.startswith("mailto:"):
            continue
        if not is_link and len(Path(target_text).parts) == 1:
            continue
        result.append((target_text, is_link))
    return result


def _check_boundary_document(
    root: Path,
    boundary_path: str,
    responsibility: str,
    boundary_id: str,
    lens: str | None,
    lens_menu: tuple[str, ...],
) -> None:
    """Fail closed on a boundary document that does not dispatch this lane.

    The document is the parent's procedure, so nothing in it is inlined. It is
    still read on the dispatch path for two checks: it must carry this lane's own
    route marker (without one, `resolve_route` would hand back a launchable route
    for a lane the prose no longer dispatches; `validate_dispatch_boundaries`
    catches the same defect, but only at check time), and on a fan-out the
    selected lens must be one the marker's own span names.
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
    if not _marker_present(content, boundary_id):
        raise ModelRouteError(f"missing route marker: {boundary_path}/{boundary_id}")
    if lens is None or responsibility != "review" or not lens_menu:
        return
    span = _marker_span_text(content, boundary_id)
    for target_text, is_link in _references(span):
        resolved, _ = _resolve_reference(root, source, target_text, is_link)
        if resolved == lens:
            return
    # `resolve_route` already rejects a lens outside the declared menu, so
    # reaching here means the menu names a lens the dispatch prose does not
    # link. Dispatching it anyway would run a lane the parent never describes.
    raise ModelRouteError(f"lens {lens} is not named at boundary {boundary_id}")


def _required_contract_paths(
    root: Path,
    boundary_path: str,
    responsibility: str,
    boundary_id: str,
    lens: str | None = None,
    lens_menu: tuple[str, ...] = (),
    declared: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Derive the exact inline contract list for one dispatch boundary.

    The seeds are the lane's own `contracts` from the manifest, then the selected
    lens on a fan-out (every menu lens when `lens` is `None`, which is how check
    time proves each one resolves). Stable contracts come first and the lens
    last, so lanes that share contracts share a prompt prefix. Each seed is then
    closed over its own `## Required Context`. No structural seed is added: the
    routing policy, the handoff rules, the owning skill and the boundary document
    are the parent's, and a worker that receives them is being told how to
    orchestrate.
    """
    root = root.resolve()
    _check_boundary_document(
        root, Path(boundary_path).as_posix(), responsibility, boundary_id, lens, lens_menu
    )
    lenses = (lens,) if lens is not None else tuple(lens_menu)
    return _contract_closure(root, tuple(dict.fromkeys((*declared, *lenses))))


def _contract_closure(root: Path, seeds: tuple[str, ...]) -> tuple[str, ...]:
    """Close the seeds over `## Required Context`, in stable order.

    A declared dependency that does not resolve fails closed, so a renamed or
    misspelled contract is a check-time error rather than a worker that silently
    lost an instruction. A missing seed is left for the caller to report: the
    manifest check names it as a missing boundary contract, and `_contracts`
    refuses it on the dispatch path.
    """
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
        for target_text, is_link in _references(_required_context_text(content)):
            resolved, allowed_paths = _resolve_reference(
                root, source, target_text, is_link
            )
            if resolved is not None:
                if resolved not in seen and resolved not in queued:
                    queued.append(resolved)
            elif allowed_paths:
                raise ModelRouteError(
                    f"missing contract dependency from {value}: {target_text}"
                )
    return tuple(result)
