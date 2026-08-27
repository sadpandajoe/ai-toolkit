"""Minimal eval-harness: read fixture files, apply a checker, report pass/fail.

Not a framework — a fixture is a JSON file, a checker is a plain function
from fixture dict to (passed, reason). Each fixture family (a directory
under evals/) owns its own checker; this module only supplies the mechanics
shared by every family (load, run, aggregate).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

Checker = Callable[[dict], tuple[bool, str]]


class EvalError(Exception):
    """A fixture file could not be loaded or was malformed."""


@dataclass(frozen=True)
class EvalResult:
    name: str
    passed: bool
    reason: str


def load_fixtures(family_dir: Path) -> list[dict]:
    """Load every *.json fixture in family_dir, sorted by filename.

    Returns an empty list if family_dir does not exist — an unbuilt or
    not-yet-populated family is a normal state, not an error.
    """
    if not family_dir.is_dir():
        return []
    fixtures: list[dict] = []
    for path in sorted(family_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise EvalError(f"{path}: invalid JSON ({error})") from error
        if not isinstance(data, dict):
            raise EvalError(f"{path}: fixture must be a JSON object")
        data.setdefault("name", path.stem)
        fixtures.append(data)
    return fixtures


def run_fixture(fixture: dict, checker: Checker) -> EvalResult:
    passed, reason = checker(fixture)
    return EvalResult(name=fixture.get("name", "<unnamed>"), passed=passed, reason=reason)


def run_family(family_dir: Path, checker: Checker) -> list[EvalResult]:
    return [run_fixture(fixture, checker) for fixture in load_fixtures(family_dir)]
