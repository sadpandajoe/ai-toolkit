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
    calls: list[dict[str, object]] | None = None,
    refusal: str | None = None,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """A stub `claude` that passes preflight and returns one worker envelope.

    `calls` collects each worker invocation's argv, stdin and the instruction
    file's text and mode, read while the file still exists. A `refusal` stop
    reason makes the worker decline instead of answering.
    """

    def runner(argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "2.1.284\n", "")
        if calls is not None:
            path = Path(argv[argv.index("--append-system-prompt-file") + 1])
            calls.append(
                {
                    "argv": list(argv),
                    "input": options.get("input"),
                    "instructions": path.read_text(),
                    "instructions_mode": path.stat().st_mode & 0o777,
                }
            )
        if refusal is not None:
            envelope: dict[str, object] = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "stop_reason": refusal,
                "result": "",
            }
        else:
            envelope = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": worker,
            }
        return subprocess.CompletedProcess(argv, 0, json.dumps(envelope), "")

    return runner


def _codex_runner(
    worker: dict[str, object] | None,
    calls: list[dict[str, object]] | None = None,
    refusal: str | None = None,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """A stub `codex` that passes preflight and writes one final worker message.

    `calls` collects each worker invocation's argv, environment, stdin, the
    schema file's content and what its `CODEX_HOME` held (name to mode), read
    while those still exist, so a test can check what actually reached the
    worker. A `None` worker writes no final message at all; a `refusal` code
    emits an error event carrying it instead of a result.
    """

    def runner(argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "codex-cli 0.159.3\n", "")
        environment = dict(options.get("env") or {})
        if calls is not None:
            home = environment.get("CODEX_HOME")
            calls.append(
                {
                    "argv": list(argv),
                    "env": environment,
                    "input": options.get("input"),
                    "cwd": options.get("cwd"),
                    "schema": json.loads(
                        Path(argv[argv.index("--output-schema") + 1]).read_text()
                    ),
                    "codex_home": {
                        path.name: path.stat().st_mode & 0o777
                        for path in sorted(Path(home).iterdir())
                    }
                    if home
                    else None,
                }
            )
        if refusal is not None:
            event = {"type": "error", "error": {"code": refusal, "message": "declined"}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(event), "")
        if worker is not None:
            Path(argv[argv.index("--output-last-message") + 1]).write_text(
                json.dumps(worker)
            )
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"type": "turn.completed"}), ""
        )

    return runner


def _lenses_named_at(boundary: dict[str, object]) -> list[str]:
    """The boundary's declared reviewer menu -- the manifest, not the prose."""
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
