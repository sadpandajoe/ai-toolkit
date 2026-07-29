"""Deriving the transitive contract closure for one dispatch.

A routed worker runs with ambient skill loading disabled, so what reaches it is
exactly what this layer computes: the structural seeds for its boundary, the
boundary's declared contracts, the one selected lens, and everything those declare
transitively. Keeping the traversal here -- separate from the validation that checks
a manifest and the transport that ships a prompt -- is what makes "what did this
worker receive" answerable without reading either.
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
    """Return the seeds every boundary of this shape gets, before any declaration.

    These are derived from the boundary's path and route responsibility alone:
    the always-on policy rules, the owning skill, the route's discipline
    contract, and the boundary document itself. Nothing here is specific to what
    the lane reviews, which is why a closure equal to this set means the lane
    declared no contract of its own -- see `_seed_only_problems`.
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
    return tuple(dict.fromkeys(values))


def _required_contract_paths(
    root: Path,
    boundary_path: str,
    responsibility: str,
    boundary_id: str,
    lens: str | None = None,
    lens_menu: tuple[str, ...] = (),
    declared: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Derive the exact inline contract closure for one dispatch boundary.

    Seeds are the union of three channels, in this order: the structural seeds
    above, this lane's own `contracts` from the manifest, and -- on a fan-out
    boundary -- the one selected lens reached through the dispatch span. Every
    seed is then closed transitively over `## Required Context`.
    """
    seeds = _structural_seeds(root, boundary_path, responsibility) + declared
    return _contract_closure(
        root,
        tuple(dict.fromkeys(seeds)),
        Path(boundary_path).as_posix(),
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
        #
        # Only a fan-out span is scanned. Dispatch prose is navigation as much as
        # instruction -- "when a PR warrants a judo pass, run a single-PR deep
        # review instead" links a document the worker must never load -- so on a
        # boundary with no menu to select from, every span link was becoming an
        # executable contract dependency. `## Required Context` is the explicit
        # channel for those; a link in running prose is not a declaration.
        scan_span = (
            value == boundary_path
            and responsibility == "review"
            and bool(lens_menu)
        )
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
        # span links to". A fan-out span contributes *only* its declared lenses,
        # and only the selected one: a span link the manifest does not name as a
        # lens is prose navigation, and treating it as a shared dependency is how
        # the batch-PR document reached the adversarial worker's closure. Every
        # real shared dependency belongs in `## Required Context`, which is never
        # narrowed. `validate_dispatch_boundaries` keeps menu and span in step,
        # so a lens the doc gained but the manifest did not is a check-time
        # failure rather than a contract silently dropped from every worker.
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
                    if from_span:
                        if relative_text not in menu:
                            break
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
