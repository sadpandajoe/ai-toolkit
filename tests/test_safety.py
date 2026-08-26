"""Safety invariants already enforced by aitk.conformance.validate_contracts.

Exercises the real invariant logic against the real repository contracts,
plus targeted mutations of a real contract to prove each invariant actually
rejects a violation rather than merely happening to pass by omission.
"""

import copy
import json
from pathlib import Path

from aitk import conformance

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_NAME = "check-resources"
REFERENCE = REPO_ROOT / "skills/workflows/references/check-resources.md"


def _contracts_document() -> dict[str, object]:
    return json.loads((REPO_ROOT / "interfaces/contracts.json").read_text())


def _vocabularies() -> dict[str, set[str]]:
    raw = _contracts_document()["vocabularies"]
    return {name: set(values) for name, values in raw.items()}


def _base_contract() -> dict[str, object]:
    for contract in _contracts_document()["contracts"]:
        if contract["name"] == CONTRACT_NAME:
            return copy.deepcopy(contract)
    raise AssertionError(f"fixture contract {CONTRACT_NAME!r} not found")


def _validate(contract: dict[str, object]) -> list[str]:
    return conformance._validate_contract(
        REPO_ROOT,
        CONTRACT_NAME,
        contract,
        "single_run",
        REFERENCE,
        (),
        _vocabularies(),
    )


def test_repo_contracts_satisfy_safety_invariants():
    assert conformance.validate_contracts(REPO_ROOT) == []


def test_baseline_contract_fixture_is_itself_valid():
    assert _validate(_base_contract()) == []


def test_mutating_contract_must_forbid_secret_output():
    contract = _base_contract()
    contract["forbidden_actions"].remove("secret-output")
    problems = _validate(contract)
    assert any(
        "forbid duplicate effects and secret output" in problem
        for problem in problems
    )


def test_mutating_contract_must_forbid_duplicate_effect():
    contract = _base_contract()
    contract["forbidden_actions"].remove("duplicate-effect")
    problems = _validate(contract)
    assert any(
        "forbid duplicate effects and secret output" in problem
        for problem in problems
    )


def test_production_refusal_gate_requires_production_mutation_forbidden_action():
    contract = _base_contract()
    contract["authorization"]["gates"] = ["production-refusal"]
    contract["forbidden_actions"] = [
        action
        for action in contract["forbidden_actions"]
        if action != "production-mutation"
    ]
    problems = _validate(contract)
    assert (
        "check-resources: gate production-refusal requires forbidden action production-mutation"
        in problems
    )


def test_publish_explicit_gate_requires_publish_without_authorization_forbidden_action():
    contract = _base_contract()
    contract["authorization"]["gates"] = ["publish-explicit"]
    problems = _validate(contract)
    assert (
        "check-resources: gate publish-explicit requires forbidden action publish-without-authorization"
        in problems
    )


def test_read_only_contract_cannot_use_effectful_authorization_mode():
    contract = _base_contract()
    contract["effect"] = "read_only"
    problems = _validate(contract)
    assert any(
        "read-only contract must use authorization mode none" in problem
        for problem in problems
    )


def test_mutating_contract_requires_authorization():
    contract = _base_contract()
    contract["authorization"]["mode"] = "none"
    contract["authorization"]["gates"] = []
    problems = _validate(contract)
    assert any(
        "mutating/effectful contract requires authorization" in problem
        for problem in problems
    )
