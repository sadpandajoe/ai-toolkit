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
        "cherry-pick.headless-implementation",
        "feedback.comment-fix-groups",
        "testing.test-authoring",
        "fix-bug.implement",
        "fix-bug.test-authoring",
        "fix-ci.implement",
        "fix-ci.test-authoring",
        "create-feature.implement",
        "create-feature.test-authoring",
        "refactor.implement",
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


def test_delta_review_boundary_is_a_deep_review_escalation_not_a_second_baseline():
    # delta-review.md is the triggered-risk pass sol-review.md escalates to --
    # it must route through deep-review only (never "review", which stays
    # sol-review's baseline lane) and must carry no lens menu, since it is one
    # additional pass, not a return to the ensemble's fan-out roster.
    payload = _payload()
    boundary = _route_boundary(payload, "review.delta-review")
    assert boundary["path"] == "skills/review/references/delta-review.md"
    assert boundary["routes"] == ["deep-review"]
    assert boundary["contracts"] == [
        "agents/codex/reviewer.md",
        "skills/review/references/adversarial.md",
    ]
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


def test_manifest_rejects_a_reintroduced_top_level_ensembles_key():
    # The reviewer-lens fan-out mechanism is retired end to end: a manifest
    # that resurrects the old `ensembles` table must fail schema validation
    # rather than silently being ignored.
    payload = copy.deepcopy(_payload())
    payload["ensembles"] = {}
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("does not match schema version 1" in p for p in problems)


def test_manifest_rejects_a_boundary_with_a_lenses_key():
    # Per-boundary lens menus are retired along with the ensemble table --
    # a boundary carrying a `lenses` key is no longer a valid shape.
    payload = copy.deepcopy(_payload())
    boundary = payload["dispatch_boundaries"][0]
    boundary["lenses"] = ["architecture"]
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("invalid dispatch boundary" in p for p in problems)


def test_gate_block_pattern_matches_a_well_formed_gate_block():
    from aitk.routing_policy import GATE_BLOCK_PATTERN

    assert GATE_BLOCK_PATTERN.search("## Gate\nState: PASS\nReason: looks good\n")
    assert GATE_BLOCK_PATTERN.search("## Gate\nState: RETRY\n")


def test_gate_block_pattern_rejects_missing_block_or_unknown_state():
    from aitk.routing_policy import GATE_BLOCK_PATTERN

    assert not GATE_BLOCK_PATTERN.search("Looks fine, ship it.")
    assert not GATE_BLOCK_PATTERN.search("## Gate\nState: MAYBE\n")
    assert not GATE_BLOCK_PATTERN.search("Score: 8/10\n")


def _resolved_route(**overrides: object):
    from aitk.routing_policy import ResolvedRoute

    fields: dict[str, object] = dict(
        name="review",
        boundary="review.sol-review",
        required_contracts=(),
        provider="claude",
        family="opus",
        selector="opus",
        effort="high",
        responsibility="review",
        restrictions=(),
        controls={},
        minimum_cli="0.0.0",
        lens_domain="plan",
    )
    fields.update(overrides)
    return ResolvedRoute(**fields)


def test_domain_problem_accepts_a_plan_result_carrying_a_gate_block():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "## Gate\nState: PASS\nReason: plan is sound\n",
        "findings": [],
    }
    assert _domain_problem(route, result) is None


def test_domain_problem_rejects_a_plan_result_missing_a_gate_block():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "Looks fine overall, 9/10.",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "## Gate" in problem
