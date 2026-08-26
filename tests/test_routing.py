"""Model routing invariants: implementation/rca run on Sonnet, review/deep-review/
deep-rca stay on Opus/Fable so a stronger model always checks Sonnet's output.

Exercises the real repository's interfaces/model-routing.json against the real
validator, plus targeted mutations to prove the invariant actually rejects a
regression back to the pre-gate-contract Opus-everywhere routing.
"""

import copy
import json
from pathlib import Path

from aitk.routing_manifest import _validate_payload, validate_model_routing

REPO_ROOT = Path(__file__).resolve().parent.parent


def _payload() -> dict[str, object]:
    return json.loads((REPO_ROOT / "interfaces/model-routing.json").read_text())


def _route(payload: dict[str, object], name: str) -> dict[str, object]:
    for route in payload["routes"]:
        if route["name"] == name:
            return route
    raise AssertionError(f"route {name!r} not found")


def test_real_manifest_is_valid():
    assert validate_model_routing(REPO_ROOT) == []


def test_implementation_and_rca_route_to_sonnet():
    payload = _payload()
    assert _route(payload, "implementation")["providers"]["claude"]["model"] == "sonnet"
    assert _route(payload, "rca")["providers"]["claude"]["model"] == "sonnet"


def test_review_deep_review_and_deep_rca_stay_on_a_stronger_model():
    payload = _payload()
    assert _route(payload, "review")["providers"]["claude"]["model"] == "opus"
    assert _route(payload, "deep-review")["providers"]["claude"]["model"] == "fable"
    assert _route(payload, "deep-rca")["providers"]["claude"]["model"] == "fable"


def test_regressing_implementation_back_to_opus_fails_validation():
    payload = copy.deepcopy(_payload())
    _route(payload, "implementation")["providers"]["claude"]["model"] = "opus"
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("model route vocabulary or invariant mapping mismatch" in p for p in problems)


def test_regressing_rca_back_to_opus_fails_validation():
    payload = copy.deepcopy(_payload())
    _route(payload, "rca")["providers"]["claude"]["model"] = "opus"
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("model route vocabulary or invariant mapping mismatch" in p for p in problems)


def test_promoting_review_to_sonnet_fails_validation():
    # Review must never move onto the same model family it is meant to check.
    payload = copy.deepcopy(_payload())
    _route(payload, "review")["providers"]["claude"]["model"] = "sonnet"
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("model route vocabulary or invariant mapping mismatch" in p for p in problems)
