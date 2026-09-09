"""Yield thresholds for optional review lanes, computed from ``metrics.jsonl``.

``rules/code-review.md`` (Yield Thresholds) says which lanes are optional,
over what window they are judged, and what happens when they stop earning
their place. Reading the metrics file by hand and applying that table is the
kind of rule a parent follows on a good day; this module makes it a command so
the demotion is computed, not remembered.

Each metrics event may carry ``review.lanes``: a map from lane name to the
counts for that run (``raised``, ``accepted``, ``converged``, ``confirmed``,
``refuted``, ``not_fixed``, ``introduced``). Missing counts read as zero. A
lane with fewer runs than its window is not judged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


DEEP_LENSES = ("adversarial", "deep-quality", "architecture")
LENS_WINDOW = 5
LANE_WINDOW = 10
VERIFIER_MINIMUM_CONFIRMED = 3
NEVER_DEMOTED = ("independent",)


@dataclass(frozen=True)
class Demotion:
    lane: str
    window: int
    runs: int
    observed: dict[str, int]
    consequence: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_events(path: Path) -> list[dict[str, object]]:
    """Read the metrics file; skip lines that are not JSON objects."""
    if not path.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _count(stats: object, field: str) -> int:
    if not isinstance(stats, dict):
        return 0
    value = stats.get(field, 0)
    return int(value) if isinstance(value, (int, float)) and value >= 0 else 0


def lane_history(events: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Return per-lane run stats, oldest first, from ``review.lanes``."""
    history: dict[str, list[dict[str, object]]] = {}
    for event in events:
        review = event.get("review")
        lanes = review.get("lanes") if isinstance(review, dict) else None
        if not isinstance(lanes, dict):
            continue
        for lane, stats in lanes.items():
            if isinstance(lane, str) and isinstance(stats, dict):
                history.setdefault(_normalize(lane), []).append(stats)
    return history


def _normalize(lane: str) -> str:
    """Lens paths and bare names refer to the same lane."""
    name = lane.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name


def _sum(runs: list[dict[str, object]], field: str) -> int:
    return sum(_count(stats, field) for stats in runs)


def evaluate(events: list[dict[str, object]]) -> list[Demotion]:
    """Apply the yield table to the lane history and return the demotions."""
    demotions: list[Demotion] = []
    for lane, runs in sorted(lane_history(events).items()):
        if lane in NEVER_DEMOTED:
            continue
        if lane in DEEP_LENSES:
            window = runs[-LENS_WINDOW:]
            if len(window) < LENS_WINDOW:
                continue
            raised, accepted = _sum(window, "raised"), _sum(window, "accepted")
            if accepted == 0 or accepted * 4 < raised:
                demotions.append(
                    Demotion(
                        lane,
                        LENS_WINDOW,
                        len(window),
                        {"raised": raised, "accepted": accepted},
                        "opt-in only: run on an explicit ask until reflect reviews it; "
                        "record the classifier flag as deferred (low yield)",
                    )
                )
            continue
        window = runs[-LANE_WINDOW:]
        if len(window) < LANE_WINDOW:
            continue
        if lane == "second-family":
            unique = sum(max(_count(s, "accepted") - _count(s, "converged"), 0) for s in window)
            refuted = _sum(window, "refuted")
            if unique == 0 and refuted == 0:
                demotions.append(
                    Demotion(
                        lane,
                        LANE_WINDOW,
                        len(window),
                        {"unique_accepted": unique, "refuted": refuted},
                        "COMPLEX only: drop the CORE trigger; the clean-verdict guard keeps it",
                    )
                )
        elif lane == "verify-major":
            confirmed = _sum(window, "confirmed")
            if confirmed < VERIFIER_MINIMUM_CONFIRMED:
                demotions.append(
                    Demotion(
                        lane,
                        LANE_WINDOW,
                        len(window),
                        {"confirmed": confirmed, "refuted": _sum(window, "refuted")},
                        "single-source majors from the raising lane default to [minor]; "
                        "write a low-yield-lane observation for that lane",
                    )
                )
        elif lane == "delta":
            not_fixed, introduced = _sum(window, "not_fixed"), _sum(window, "introduced")
            if not_fixed == 0 and introduced == 0:
                demotions.append(
                    Demotion(
                        lane,
                        LANE_WINDOW,
                        len(window),
                        {"not_fixed": not_fixed, "introduced": introduced},
                        "delta pass runs only after a [major] fix",
                    )
                )
    return demotions


def default_metrics_file(cwd: Path | None = None) -> Path:
    return ((cwd or Path.cwd()) / ".ai-toolkit" / "metrics.jsonl").resolve()
