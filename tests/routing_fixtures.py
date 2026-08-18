"""Shared fixtures for the routing test modules.

The routing suite is split by layer, and every layer needs the same three things:
the real manifest as data, the accessors that read one boundary's declarations, and
a stub provider CLI that passes preflight. They live here so the split modules share
one definition instead of five drifting copies.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


_MANIFEST = json.loads((ROOT / "interfaces/model-routing.json").read_text())


MODEL_CATALOG = _MANIFEST["providers"]


MODEL_ROUTE_FLOORS = {
    lens: tuple(routes) for lens, routes in _MANIFEST.get("lens_routes", {}).items()
}


def _claude_runner(
    worker: dict[str, object],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """A stub `claude` that passes preflight and returns one worker envelope."""

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "2.1.219\n", "")
        if "--help" in argv:
            flags = " ".join(
                (
                    "--print --no-session-persistence --safe-mode ",
                    "--strict-mcp-config --mcp-config --model --effort ",
                    "--permission-mode --json-schema --output-format ",
                    "--disallowedTools --tools",
                )
            )
            return subprocess.CompletedProcess(argv, 0, flags, "")
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "structured_output": worker,
                }
            ),
            "",
        )

    return runner


def _declared_at(boundary: dict[str, object]) -> list[str]:
    """What this lane is *told* to read: manifest `contracts` + Required Context.

    Deliberately not "every Markdown link in the span". A link is navigation, and
    treating one as a contract dependency is the defect that shipped the
    deep-quality gate into every closure whose span happened to link the
    classifier. Starvation is therefore measured against declarations -- the two
    channels a document actually uses to say a worker needs something -- so this
    check keeps catching workers starved of their instructions without reviving
    "linked from" as a dependency edge.
    """
    document = Path(str(boundary["path"]))
    section = re.search(
        r"^## Required Context.*?(?=^## |\Z)",
        (ROOT / document).read_text(),
        re.MULTILINE | re.DOTALL,
    )
    named: set[str] = set()
    if section is not None:
        # Both spellings are declarations here. Backticks name a repo-relative
        # path; a Markdown link inside this section is document-relative and is
        # how a reference points at its siblings without the reader guessing the
        # path. Only *inside* this section -- the same link in running prose below
        # is navigation.
        named |= set(re.findall(r"`([^`]+\.md)`", section.group(0)))
        named |= {
            os.path.normpath((document.parent / target).as_posix())
            for target in re.findall(r"\]\(([^)]+\.md)\)", section.group(0))
        }
    contracts = boundary.get("contracts")
    if isinstance(contracts, list):
        named |= {str(item) for item in contracts}
    return sorted(path for path in named if (ROOT / path).is_file())


def _lenses_named_at(boundary: dict[str, object]) -> list[str]:
    """The boundary's declared reviewer menu -- the manifest, not the prose.

    A span link is no longer proof of lens-hood: the manifest declares the menu
    and `validate_dispatch_boundaries` holds the prose to it, which is what lets
    a fan-out span link an ordinary shared reference without that reference
    becoming a selectable lane.
    """
    lenses = boundary.get("lenses")
    return sorted(lenses) if isinstance(lenses, list) else []


def _a_lens_named_at(boundary: dict[str, object]) -> str | None:
    """One valid --lens for a fan-out boundary; None where the flag is refused.

    A declared menu is what makes a boundary fan out. `lens_domain` is a separate
    property -- which artefact the lane grades -- and a lane can carry one without
    a menu, applying its lenses itself rather than dispatching them.
    """
    menu = _lenses_named_at(boundary)
    return menu[0] if menu else None


def _routes_for(boundary: dict[str, object], lens: str | None) -> list[str]:
    """The routes this lane can actually resolve, after the lens's route floor.

    A boundary's `routes` list is the union its lanes may use; a lens with a
    declared floor narrows it further. Sweeping the raw union asks the resolver
    for combinations it is *supposed* to refuse -- an architecture or adversarial
    lane on the cheap route -- so these sweeps would report the floor working as
    a failure.
    """
    floors = MODEL_ROUTE_FLOORS.get(lens or "")
    return [
        route
        for route in (str(item) for item in boundary["routes"])
        if floors is None or route in floors
    ]


RESULT = {
    "status": "completed",
    "summary": "done",
    "findings": [],
    "verification": ["checked"],
}


class RoutingTestCase(unittest.TestCase):
    """Base case with a throwaway copy of the repo to mutate."""

    def fixture(self, temporary: str) -> Path:
        root = Path(temporary) / "repo"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__"),
        )
        return root
