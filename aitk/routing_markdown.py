"""Reading dispatch declarations out of Markdown.

Every routing input that is not JSON is a Markdown document: the inline route
markers, the marker spans, and the `## Required Context` sections that declare what
a lane must read. This layer is the only one that parses them, so the rule that a
link in running prose is navigation while a link inside Required Context is a
declaration is stated in exactly one place.
"""

from __future__ import annotations

from pathlib import Path
import re

from aitk.routing_policy import (
    EXEMPT_MARKER,
    LENS_CATALOG,
    MARKDOWN_LINK,
    ROUTE_MARKER,
)


def _markdown_lines(path: Path) -> list[tuple[int, str]]:
    return _markdown_content_lines(path.read_text())


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


def _span_link_targets(root: Path, boundary: dict[str, object]) -> set[str]:
    """Resolve the Markdown links inside one boundary's marker span."""
    source = root / str(boundary["path"])
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    targets: set[str] = set()
    span = _marker_span_text(content, str(boundary["id"]))
    for match in MARKDOWN_LINK.finditer(span):
        target = match.group(1).strip().strip("<>").split("#", 1)[0]
        if not target or "://" in target:
            continue
        try:
            relative = (source.parent / target).resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        targets.add(relative.as_posix())
    return targets


def _catalog_lenses(root: Path) -> tuple[set[str], list[str]]:
    """Read the reviewer-lens universe from the classifier's Review Domain table.

    The universe has to come from outside the menus being checked. Deriving it
    from those menus made the check self-referential: a lens dropped from every
    menu left the universe at the same time, so nothing could observe that it had
    stopped being routable anywhere. The classifier table is the independent
    source -- it is what decides a lens should run at all.
    """
    source = root / LENS_CATALOG
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set(), [f"reviewer lens catalog could not be read: {LENS_CATALOG}"]
    table = re.search(
        r"^\| Review Domain \| Trigger \| Skill \|.*?(?=\n\n)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if table is None:
        return set(), [f"reviewer lens catalog lost its Review Domain table: {LENS_CATALOG}"]
    lenses: set[str] = set()
    for line in table.group(0).splitlines()[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        candidate = cells[2].strip("`")
        if candidate.endswith(".md"):
            lenses.add(f"skills/{candidate}")
    return lenses, []


def _marker_present(content: str, boundary_id: str) -> bool:
    """Report whether a boundary document carries its own route marker."""
    return any(
        (match := ROUTE_MARKER.fullmatch(line.strip())) is not None
        and match.group(1) == boundary_id
        for _, line in _markdown_content_lines(content)
    )


def _marker_span_text(content: str, boundary_id: str) -> str:
    """Return the dispatch prose owned by one route marker.

    The span runs from the marker to the next route/exemption marker or the next
    Markdown heading, whichever comes first. Headings and markers inside fenced
    examples are documentation, not span structure, so the scan runs over
    fence-stripped lines. A boundary whose marker is missing contributes nothing
    here; callers on the dispatch path check `_marker_present` first so a missing
    marker fails closed instead of silently shrinking the closure.
    """
    selected: list[str] = []
    in_span = False
    for _, line in _markdown_content_lines(content):
        stripped = line.strip()
        route_marker = ROUTE_MARKER.fullmatch(stripped)
        if route_marker is not None:
            in_span = route_marker.group(1) == boundary_id
            continue
        if in_span and (
            EXEMPT_MARKER.fullmatch(stripped) is not None or stripped.startswith("#")
        ):
            break
        if in_span:
            selected.append(line)
    return "\n".join(selected)


def _required_context_text(content: str) -> str:
    lines = content.splitlines()
    selected: list[str] = []
    in_required_section = False
    for line in lines:
        if line.startswith("## Required Context"):
            in_required_section = True
            selected.append(line)
            continue
        if in_required_section and line.startswith("## "):
            in_required_section = False
        if in_required_section or re.search(r"\b(?:Read before|Findings use)\b", line):
            selected.append(line)
    return "\n".join(selected)


def _contract_dependency_allowed(path: Path) -> bool:
    if not path.parts:
        return False
    if path.parts[0] in {"rules", "skills"}:
        return True
    return (
        len(path.parts) >= 4
        and path.parts[0] == "extensions"
        and path.parts[2] == "skills"
    )
