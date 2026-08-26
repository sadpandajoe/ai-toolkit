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


def test_planning_stays_on_opus_and_is_read_only():
    payload = _payload()
    route = _route(payload, "planning")
    assert route["providers"]["claude"]["model"] == "opus"
    assert route["providers"]["claude"]["permission_mode"] == "plan"


def test_regressing_planning_to_sonnet_fails_validation():
    # Planning precedes implementation and must never self-approve on the
    # same model family that would go on to implement its own plan.
    payload = copy.deepcopy(_payload())
    _route(payload, "planning")["providers"]["claude"]["model"] = "sonnet"
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("model route vocabulary or invariant mapping mismatch" in p for p in problems)


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


def _boundaries(payload: dict[str, object]) -> list[dict[str, object]]:
    return list(payload["dispatch_boundaries"])


def test_every_rca_boundary_cites_the_codex_rca_contract():
    payload = _payload()
    for boundary in _boundaries(payload):
        routes = set(boundary["routes"])
        if routes & {"rca", "deep-rca"}:
            contracts = boundary.get("contracts") or []
            assert "agents/codex/rca.md" in contracts, boundary["id"]


def test_every_plan_domain_review_boundary_cites_the_plan_validator_contract():
    payload = _payload()
    for boundary in _boundaries(payload):
        if boundary.get("lens_domain") == "plan":
            contracts = boundary.get("contracts") or []
            assert "agents/codex/plan-validator.md" in contracts, boundary["id"]


def test_every_code_domain_review_boundary_cites_the_reviewer_contract():
    payload = _payload()
    for boundary in _boundaries(payload):
        if boundary.get("lens_domain") == "code":
            contracts = boundary.get("contracts") or []
            assert "agents/codex/reviewer.md" in contracts, boundary["id"]


def test_no_boundary_cites_both_reviewer_and_plan_validator():
    # The code/plan split is exclusive -- a boundary grades one artifact kind.
    payload = _payload()
    for boundary in _boundaries(payload):
        contracts = set(boundary.get("contracts") or [])
        cites_both = {"agents/codex/reviewer.md", "agents/codex/plan-validator.md"} <= contracts
        assert not cites_both, boundary["id"]


def test_every_declared_contract_path_exists_on_disk():
    payload = _payload()
    for boundary in _boundaries(payload):
        for contract in boundary.get("contracts") or []:
            assert (REPO_ROOT / contract).is_file(), f"{boundary['id']}: {contract}"


def test_implementation_only_boundaries_are_untouched_by_the_codex_retarget():
    # Codex still serves the implementation route (routes[].providers.codex is
    # live), and every one of these boundaries has a physical
    # `aitk-model-route` marker in its skill file -- dropping the entry would
    # orphan that marker. Retargeting is scoped to rca/review/deep-review only.
    payload = _payload()
    implementation_only_ids = {
        boundary["id"]
        for boundary in _boundaries(payload)
        if set(boundary["routes"]) == {"implementation"}
    }
    expected = {
        "workflows.create-feature-implementation",
        "workflows.fix-bug-implementation",
        "cherry-pick.headless-implementation",
        "feedback.comment-fix-groups",
        "testing.test-authoring",
        "workflows.feedback-fix-wave",
        "workflows.create-feature-moderate-implementation",
        "workflows.create-feature-moderate-handoff",
        "fix-bug.implement",
        "fix-bug.test-authoring",
        "create-feature.implement",
        "create-feature.test-authoring",
    }
    assert implementation_only_ids == expected
    for identifier in implementation_only_ids:
        boundary = next(b for b in _boundaries(payload) if b["id"] == identifier)
        assert "contracts" not in boundary


def test_sol_review_boundary_is_a_single_menu_less_reviewer_dispatch():
    # sol-review.md replaces the tier-resolved ensemble roster with one
    # independent pass -- it must not carry a lens menu (that would make it
    # a fan-out lane again) and must route only through the review tier, not
    # deep-review, which stays the triggered-risk escalation's job.
    payload = _payload()
    boundary = _route_boundary(payload, "review.sol-review")
    assert boundary["path"] == "skills/review/references/sol-review.md"
    assert boundary["routes"] == ["review"]
    assert boundary["contracts"] == ["agents/codex/reviewer.md"]
    assert "lens_domain" not in boundary
    assert "lenses" not in boundary


def _route_boundary(payload: dict[str, object], identifier: str) -> dict[str, object]:
    for boundary in _boundaries(payload):
        if boundary["id"] == identifier:
            return boundary
    raise AssertionError(f"no dispatch boundary named {identifier!r}")


def test_contract_dependency_allowed_permits_only_the_codex_agents_directory():
    from aitk.routing_markdown import _contract_dependency_allowed
    from pathlib import PurePosixPath

    assert _contract_dependency_allowed(PurePosixPath("agents/codex/rca.md"))
    assert not _contract_dependency_allowed(PurePosixPath("agents/claude/debug-worker.md"))
    assert not _contract_dependency_allowed(PurePosixPath("agents/codex/nested/rca.md"))
