"""Model routing invariants: implementation/rca run on Sonnet, review/deep-review/
deep-rca stay on Opus/Fable so a stronger model always checks Sonnet's output.

Exercises the real repository's interfaces/model-routing.json against the real
validator, plus targeted mutations to prove the invariant actually rejects a
regression back to the pre-gate-contract Opus-everywhere routing.
"""

import copy
import json
from pathlib import Path

import pytest

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
    # `lens_domain` is a separate concern from the retired `lenses` fan-out
    # key: it tags which artefact this lane grades (code, here) and is now
    # required on every review-routed boundary, this one included.
    payload = _payload()
    boundary = _route_boundary(payload, "review.sol-review")
    assert boundary["path"] == "skills/review/references/sol-review.md"
    assert boundary["routes"] == ["review"]
    assert boundary["contracts"] == ["agents/codex/reviewer.md"]
    assert boundary["lens_domain"] == "code"
    assert "lenses" not in boundary


def test_delta_review_boundary_is_a_deep_review_escalation_not_a_second_baseline():
    # delta-review.md is the triggered-risk pass sol-review.md escalates to --
    # it must route through deep-review only (never "review", which stays
    # sol-review's baseline lane) and must carry no lens menu, since it is one
    # additional pass, not a return to the ensemble's fan-out roster.
    # `lens_domain` is a separate concern from the retired `lenses` fan-out
    # key: it tags which artefact this lane grades (code, here) and is now
    # required on every review-routed boundary, this one included.
    payload = _payload()
    boundary = _route_boundary(payload, "review.delta-review")
    assert boundary["path"] == "skills/review/references/delta-review.md"
    assert boundary["routes"] == ["deep-review"]
    assert boundary["contracts"] == [
        "agents/codex/reviewer.md",
        "skills/review/references/adversarial.md",
    ]
    assert boundary["lens_domain"] == "code"
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


def test_workers_map_resolves_expected_native_worker_ids():
    payload = _payload()
    assert _route_boundary(payload, "fix-bug.implement")["workers"] == {
        "implementation": "implementation-worker"
    }
    assert _route_boundary(payload, "fix-bug.test-authoring")["workers"] == {
        "implementation": "test-worker"
    }
    assert _route_boundary(payload, "qa.fresh-validation-judgment")["workers"] == {
        "review": "review-worker",
        "deep-review": "deep-review-worker",
    }
    assert _route_boundary(payload, "qa.fresh-validation-evidence")["workers"] == {
        "operations": "operations-worker"
    }
    assert _route_boundary(payload, "workflows.review-plan-selected")["workers"] == {
        "review": "plan-review-worker",
        "deep-review": "deep-plan-review-worker",
    }


def test_manifest_rejects_a_boundary_missing_workers():
    # `workers` is required on every boundary now -- an entry with the old,
    # pre-J1 key set is no longer a valid shape.
    payload = copy.deepcopy(_payload())
    boundary = payload["dispatch_boundaries"][0]
    del boundary["workers"]
    problems = _validate_payload(REPO_ROOT, payload)
    assert any("invalid dispatch boundary entry" in p for p in problems)


def test_manifest_rejects_a_workers_map_missing_a_route():
    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "qa.fresh-validation-judgment")
    del boundary["workers"]["deep-review"]
    problems = _validate_payload(REPO_ROOT, payload)
    assert any(
        "invalid dispatch boundary workers map: qa.fresh-validation-judgment" in p
        for p in problems
    )


def test_workers_map_covers_the_full_ladder_even_when_routes_is_baseline_only():
    # `fix-bug.review` only ever *dispatches* at baseline (`routes: ["review"]`)
    # -- that stays true, since `routes` is what the boundary offers today.
    # But its ladder can escalate to `deep-review`, and the workers map must
    # already resolve that rung so an in-flight escalation is never left
    # without a worker to hand off to.
    payload = _payload()
    boundary = _route_boundary(payload, "fix-bug.review")
    assert boundary["routes"] == ["review"]
    assert boundary["workers"] == {
        "review": "review-worker",
        "deep-review": "deep-review-worker",
    }


def test_manifest_rejects_a_baseline_only_boundary_missing_its_escalation_worker():
    # Reproduces the pre-fix shape: `routes: ["review"]` with a `workers` map
    # that only covers `review`, leaving the ladder's `deep-review` rung with
    # no worker to resolve to. This must fail even though `workers` matches
    # `routes` exactly -- `routes` is baseline dispatch, not the full ladder.
    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "fix-bug.review")
    del boundary["workers"]["deep-review"]
    problems = _validate_payload(REPO_ROOT, payload)
    assert any(
        "invalid dispatch boundary workers map: fix-bug.review" in p for p in problems
    )


def test_manifest_does_not_require_a_review_entry_on_a_deep_review_only_boundary():
    # Escalation only climbs the ladder, never descends: a boundary anchored
    # at the top rung (`routes: ["deep-review"]`) never dispatches at
    # baseline `review`, so its workers map correctly has no `review` entry.
    payload = _payload()
    boundary = _route_boundary(payload, "review.delta-review")
    assert boundary["routes"] == ["deep-review"]
    assert boundary["workers"] == {"deep-review": "deep-review-worker"}
    assert _validate_payload(REPO_ROOT, payload) == []


def test_manifest_rejects_a_workers_map_naming_an_unknown_worker_id():
    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "fix-bug.implement")
    boundary["workers"]["implementation"] = "nonexistent-worker"
    problems = _validate_payload(REPO_ROOT, payload)
    assert any(
        "dispatch boundary worker mismatch: fix-bug.implement/implementation" in p
        for p in problems
    )


def test_manifest_rejects_a_worker_row_filed_under_the_wrong_route():
    # debug-worker's native_workers row names route "rca" -- filing it under
    # the "deep-rca" key must fail even though both are valid routes for this
    # boundary.
    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "fix-bug.investigate")
    boundary["workers"] = {"rca": "deep-rca-worker", "deep-rca": "debug-worker"}
    problems = _validate_payload(REPO_ROOT, payload)
    assert any(
        "dispatch boundary worker mismatch: fix-bug.investigate" in p for p in problems
    )


def test_manifest_rejects_a_plan_boundary_naming_a_code_worker():
    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "workflows.review-plan-selected")
    boundary["workers"]["review"] = "review-worker"
    problems = _validate_payload(REPO_ROOT, payload)
    assert any(
        "dispatch boundary worker mismatch: workflows.review-plan-selected/review" in p
        for p in problems
    )


def test_manifest_rejects_a_review_boundary_with_no_lens_domain():
    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "review.sol-review")
    del boundary["lens_domain"]
    problems = _validate_payload(REPO_ROOT, payload)
    assert any(
        "review boundary missing lens_domain: review.sol-review" in p for p in problems
    )


def test_manifest_rejects_boundary_routes_spanning_two_ladders():
    # `BOUNDARY_INVARIANTS` pins each boundary's route ceiling, but it is an
    # allowlist, not a shape constraint -- nothing else stops a new invariant
    # entry from mixing two escalation chains (the shape `qa.fresh-validation`
    # had before it was split). Patch the table with exactly that shape to
    # prove the ladder check catches it independent of any real boundary.
    import aitk.routing_manifest as routing_manifest

    payload = copy.deepcopy(_payload())
    boundary = _route_boundary(payload, "qa.fresh-validation-evidence")
    boundary["routes"] = ["operations", "review"]
    boundary["workers"] = {"operations": "operations-worker", "review": "review-worker"}
    original = dict(routing_manifest.BOUNDARY_INVARIANTS)
    routing_manifest.BOUNDARY_INVARIANTS["qa.fresh-validation-evidence"] = (
        "operations",
        "review",
    )
    try:
        problems = _validate_payload(REPO_ROOT, payload)
    finally:
        routing_manifest.BOUNDARY_INVARIANTS.clear()
        routing_manifest.BOUNDARY_INVARIANTS.update(original)
    assert any(
        "dispatch boundary routes span more than one ladder: qa.fresh-validation-evidence" in p
        for p in problems
    )


def test_every_manifest_boundary_id_is_pinned_in_boundary_invariants():
    from aitk.routing_manifest import BOUNDARY_INVARIANTS

    payload = _payload()
    missing = [b["id"] for b in _boundaries(payload) if b["id"] not in BOUNDARY_INVARIANTS]
    assert missing == []


def test_plan_verdict_pattern_matches_each_of_the_three_verdicts():
    from aitk.routing_policy import PLAN_VERDICT_PATTERN

    assert PLAN_VERDICT_PATTERN.search("APPROVE")
    assert PLAN_VERDICT_PATTERN.search("CHANGES REQUIRED\nsome prose after\n")
    assert PLAN_VERDICT_PATTERN.search("## Test Plan Review\nVerdict: REPLAN\n")
    assert PLAN_VERDICT_PATTERN.search("**REPLAN**\n")
    assert PLAN_VERDICT_PATTERN.search("**Verdict:** APPROVE\n")
    assert PLAN_VERDICT_PATTERN.search(
        "REPLAN -- the invalidated assumption is that the API is idempotent\n"
    )


def test_plan_verdict_pattern_rejects_missing_or_unknown_verdict():
    from aitk.routing_policy import PLAN_VERDICT_PATTERN

    assert not PLAN_VERDICT_PATTERN.search("Looks fine, ship it.")
    assert not PLAN_VERDICT_PATTERN.search("## Gate\nState: PASS\n")
    assert not PLAN_VERDICT_PATTERN.search("no CHANGES REQUIRED here")
    assert not PLAN_VERDICT_PATTERN.search("Score: 8/10\n")


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


def test_domain_problem_accepts_a_plan_result_carrying_a_bare_verdict():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "APPROVE",
        "findings": [],
    }
    assert _domain_problem(route, result) is None


def test_domain_problem_rejects_a_plan_result_missing_a_verdict():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "Looks fine overall, 9/10.",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "APPROVE/CHANGES REQUIRED/REPLAN" in problem


def test_domain_problem_rejects_a_plan_result_still_carrying_a_gate_block():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "## Gate\nState: PASS\nReason: plan is sound\n",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None


def test_domain_problem_rejects_a_plan_result_with_two_contradictory_verdicts():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "APPROVE\nREPLAN -- actually the premise is invalid\n",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "contradictory" in problem


def test_domain_problem_rejects_a_plan_result_pairing_a_verdict_with_a_gate_block():
    from aitk.routing_transport import _domain_problem

    route = _resolved_route()
    result = {
        "status": "completed",
        "summary": "APPROVE\n## Gate\nState: BLOCKED\n",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None


def _real_code_route(route_name: str, boundary: str):
    # Resolve the *actual* manifest boundary rather than a synthetic
    # ResolvedRoute -- `_resolved_route()`'s default fixture names
    # `review.sol-review` as its `boundary` but overrides `lens_domain` to
    # `plan`, which is not what that boundary's real manifest entry
    # declares (`code`), so it never exercised the code-severity vocabulary
    # (`CODE_SEVERITIES`/`DOMAIN_FINDING_PATTERNS["code"]`) at all. These
    # tests resolve `review.sol-review`/`review.delta-review` for real,
    # through the same resolver a live dispatch uses, so `lens_domain` here
    # is provably what the manifest pins rather than an unrelated override.
    from aitk.routing_resolver import resolve_route

    route = resolve_route(REPO_ROOT, route_name, "codex", boundary=boundary)
    assert route.lens_domain == "code"
    return route


def test_domain_problem_accepts_valid_code_severity_tags_on_the_real_sol_review_boundary():
    from aitk.routing_transport import _domain_problem

    route = _real_code_route("review", "review.sol-review")
    result = {
        "status": "completed",
        "summary": "one major, one minor, one nitpick",
        "findings": [
            "[major] unchecked return value drops a write error",
            "[minor] duplicated null check",
            "[nitpick] inconsistent naming",
        ],
    }
    assert _domain_problem(route, result) is None


def test_domain_problem_rejects_untagged_findings_on_the_real_sol_review_boundary():
    from aitk.routing_transport import _domain_problem

    route = _real_code_route("review", "review.sol-review")
    result = {
        "status": "completed",
        "summary": "looks fine",
        "findings": ["This drops a write error on failure."],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "review.sol-review" in problem
    assert "[major]/[minor]/[nitpick]" in problem


def test_domain_problem_rejects_plan_style_tags_on_the_real_sol_review_boundary():
    from aitk.routing_transport import _domain_problem

    route = _real_code_route("review", "review.sol-review")
    result = {
        "status": "completed",
        "summary": "looks fine",
        # A plan-domain tag, not a code-domain one -- the code lane's
        # vocabulary is `[major]`/`[minor]`/`[nitpick]`, never `[High]`.
        "findings": ["[High] this drops a write error on failure"],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "review.sol-review" in problem


def test_domain_problem_accepts_valid_code_severity_tags_on_the_real_delta_review_boundary():
    from aitk.routing_transport import _domain_problem

    route = _real_code_route("deep-review", "review.delta-review")
    result = {
        "status": "completed",
        "summary": "confirmed one finding on re-review",
        "findings": ["[major] confirmed: unchecked return value drops a write error"],
    }
    assert _domain_problem(route, result) is None


def test_domain_problem_rejects_untagged_findings_on_the_real_delta_review_boundary():
    from aitk.routing_transport import _domain_problem

    route = _real_code_route("deep-review", "review.delta-review")
    result = {
        "status": "completed",
        "summary": "confirmed",
        "findings": ["Confirmed: this drops a write error on failure."],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "review.delta-review" in problem


def test_domain_problem_rejects_plan_style_tags_on_the_real_delta_review_boundary():
    from aitk.routing_transport import _domain_problem

    route = _real_code_route("deep-review", "review.delta-review")
    result = {
        "status": "completed",
        "summary": "confirmed",
        # A plan-domain tag, not a code-domain one -- delta-review is the
        # code ladder's escalation rung and shares sol-review's vocabulary
        # (`[major]`/`[minor]`/`[nitpick]`), never `[High]`/`[Medium]`/`[Low]`.
        "findings": ["[High] confirmed: this drops a write error on failure"],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert "review.delta-review" in problem


def _real_plan_route(route_name: str, boundary: str):
    # Resolve the actual manifest boundaries the review finding named --
    # `workflows.review-plan-fresh` and `workflows.review-plan-selected` --
    # rather than the synthetic `_resolved_route()` fixture, so a regression
    # in the manifest's own `lens_domain`/routes wiring for these two
    # boundaries would be caught here too.
    from aitk.routing_resolver import resolve_route

    route = resolve_route(REPO_ROOT, route_name, "claude", boundary=boundary)
    assert route.lens_domain == "plan"
    return route


@pytest.mark.parametrize(
    "boundary", ["workflows.review-plan-fresh", "workflows.review-plan-selected"]
)
@pytest.mark.parametrize("route_name", ["review", "deep-review"])
@pytest.mark.parametrize("verdict", ["APPROVE", "CHANGES REQUIRED", "REPLAN"])
def test_domain_problem_accepts_all_three_verdicts_on_the_real_plan_review_boundaries(
    boundary, route_name, verdict
):
    from aitk.routing_transport import _domain_problem

    route = _real_plan_route(route_name, boundary)
    result = {"status": "completed", "summary": verdict, "findings": []}
    assert _domain_problem(route, result) is None


@pytest.mark.parametrize(
    "boundary", ["workflows.review-plan-fresh", "workflows.review-plan-selected"]
)
@pytest.mark.parametrize("route_name", ["review", "deep-review"])
@pytest.mark.parametrize("verdict", ["APPROVE", "CHANGES REQUIRED", "REPLAN"])
def test_full_worker_envelope_with_each_verdict_clears_every_check_run_model_applies(
    boundary, route_name, verdict
):
    # `run_model` (aitk/routing_transport.py) validates a worker's result
    # through `_valid_worker`, then `_domain_problem`, then `_summary_problem`
    # -- in that order -- before ever looking at `lens_domain`-specific
    # vocabulary. A test that calls `_domain_problem` alone would pass even if
    # `_valid_worker`'s generic envelope shape check or a `summary_form`
    # requirement rejected the exact payload a real plan-review worker sends.
    # Run the same three checks, in the same order, against a complete
    # envelope to prove the finding's original repro
    # (`{"status": "completed", "summary": "APPROVE", "findings": []}`) is
    # actually accepted end to end, not just by one of the three checks.
    from aitk.routing_transport import _domain_problem, _summary_problem, _valid_worker

    route = _real_plan_route(route_name, boundary)
    result = {
        "status": "completed",
        "summary": verdict,
        "findings": [],
        "verification": [],
    }
    assert _valid_worker(result)
    assert _domain_problem(route, result) is None
    assert _summary_problem(route, result) is None


@pytest.mark.parametrize(
    "boundary", ["workflows.review-plan-fresh", "workflows.review-plan-selected"]
)
def test_domain_problem_rejects_a_gate_block_summary_on_the_real_plan_review_boundaries(
    boundary,
):
    from aitk.routing_transport import _domain_problem

    route = _real_plan_route("review", boundary)
    result = {
        "status": "completed",
        "summary": "## Gate\nState: PASS\nReason: looks good\n",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert boundary in problem


@pytest.mark.parametrize(
    "boundary", ["workflows.review-plan-fresh", "workflows.review-plan-selected"]
)
def test_domain_problem_rejects_contradictory_verdicts_on_the_real_plan_review_boundaries(
    boundary,
):
    from aitk.routing_transport import _domain_problem

    route = _real_plan_route("review", boundary)
    result = {
        "status": "completed",
        "summary": "APPROVE\nREPLAN -- the invalidated assumption is X\n",
        "findings": [],
    }
    problem = _domain_problem(route, result)
    assert problem is not None
    assert boundary in problem


def test_worker_prompt_for_a_real_plan_boundary_states_the_verdict_vocabulary_not_a_gate_block():
    from aitk.routing_transport import worker_prompt

    route = _real_plan_route("review", "workflows.review-plan-fresh")
    prompt = worker_prompt(route, "review the plan", ())
    assert "APPROVE" in prompt
    assert "CHANGES REQUIRED" in prompt
    assert "REPLAN" in prompt
    # The prompt explicitly tells the worker never to render a `## Gate`
    # block -- it is allowed to *name* that heading as the thing to avoid,
    # just not to instruct the worker to produce one.
    assert "summary must contain a `## Gate` heading" not in prompt
