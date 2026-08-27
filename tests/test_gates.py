"""Tests for the pure gate-decision module (aitk.gates) and its persistence
integration with aitk.gate_state."""

from pathlib import Path

import pytest

from aitk import gate_state
from aitk.gates import GATE_STATES, assert_independent_verification, decide_failure


def test_gate_states_is_the_six_state_vocabulary():
    assert GATE_STATES == {
        "PASS",
        "RETRY",
        "ESCALATE",
        "USER_DECISION",
        "BLOCKED",
        "RECLASSIFY",
    }


def test_first_reasoning_failure_retries():
    state, count = decide_failure(0, "flaky assertion")
    assert (state, count) == ("RETRY", 1)


def test_second_consecutive_reasoning_failure_escalates():
    state, count = decide_failure(1, "flaky assertion")
    assert (state, count) == ("ESCALATE", 2)


def test_repeated_escalation_stays_escalated_and_keeps_counting():
    state, count = decide_failure(2, "flaky assertion")
    assert (state, count) == ("ESCALATE", 3)


def test_reasoning_escalates_even_when_the_reason_text_differs():
    # The same-reason comparison is retired: two consecutive reasoning
    # failures escalate regardless of whether the text matches.
    state, count = decide_failure(1, "missing fixture")
    assert (state, count) == ("ESCALATE", 2)


def test_mechanical_failure_always_retries_and_never_advances_count():
    state, count = decide_failure(0, "flaky CI runner", kind="mechanical")
    assert (state, count) == ("RETRY", 0)
    state, count = decide_failure(count, "flaky CI runner", kind="mechanical")
    assert (state, count) == ("RETRY", 0)
    state, count = decide_failure(count, "different flake", kind="mechanical")
    assert (state, count) == ("RETRY", 0)


def test_mechanical_failures_do_not_spend_the_reasoning_budget():
    # A mechanical retry in between two reasoning failures does not reset
    # or advance the reasoning count — only reasoning failures do.
    state, count = decide_failure(0, "wrong approach")
    assert (state, count) == ("RETRY", 1)
    state, count = decide_failure(count, "transient timeout", kind="mechanical")
    assert (state, count) == ("RETRY", 1)
    state, count = decide_failure(count, "wrong approach, take two")
    assert (state, count) == ("ESCALATE", 2)


def test_rejects_empty_reason():
    with pytest.raises(ValueError, match="reason must be"):
        decide_failure(0, "")


def test_rejects_invalid_kind():
    with pytest.raises(ValueError, match="kind must be"):
        decide_failure(0, "x", kind="vibes")


def test_rejects_negative_previous_count():
    with pytest.raises(ValueError, match="previous_count must be"):
        decide_failure(-1, "x")


def test_rejects_non_integer_previous_count():
    with pytest.raises(ValueError, match="previous_count must be"):
        decide_failure(True, "x")


# --- never-self-verify: assert_independent_verification() -----------------


def test_independent_identities_pass_silently():
    assert assert_independent_verification("planner", "codex-plan-validator") is None


def test_same_identity_as_author_and_verifier_raises():
    with pytest.raises(ValueError, match="independent of author"):
        assert_independent_verification("planner", "planner")


def test_rejects_empty_author():
    with pytest.raises(ValueError, match="author must be"):
        assert_independent_verification("", "reviewer")


def test_rejects_empty_verifier():
    with pytest.raises(ValueError, match="verifier must be"):
        assert_independent_verification("planner", "")


def test_rejects_non_string_author():
    with pytest.raises(ValueError, match="author must be"):
        assert_independent_verification(None, "reviewer")


# --- persistence integration: decide_failure() composed with gate_state ---


def test_decide_failure_persists_and_round_trips_through_gate_state(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    state, count = decide_failure(0, "missing tests")
    gate_state.set_state(path, "review", state, "missing tests", count)
    assert gate_state.read(path, "review") == {
        "state": "RETRY",
        "reason": "missing tests",
        "count": 1,
        "kind": "reasoning",
    }


def test_repeat_count_builds_across_calls_via_persisted_history():
    # Simulate a caller re-deciding against the previously persisted record
    # on each call, the way a real workflow would after a context reset.
    previous_count = 0
    reasons = ["missing tests", "missing tests", "missing tests"]
    seen_states = []
    for reason in reasons:
        state, count = decide_failure(previous_count, reason)
        seen_states.append((state, count))
        previous_count = count
    assert seen_states == [("RETRY", 1), ("ESCALATE", 2), ("ESCALATE", 3)]


def test_mechanical_kind_round_trips_through_gate_state(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    state, count = decide_failure(0, "flaky runner", kind="mechanical")
    gate_state.set_state(path, "review", state, "flaky runner", count, "mechanical")
    assert gate_state.read(path, "review") == {
        "state": "RETRY",
        "reason": "flaky runner",
        "count": 0,
        "kind": "mechanical",
    }


# --- scripted end-to-end scenario through the decision table --------------


def test_scripted_scenario_retry_then_escalate_then_pass_then_blocked(tmp_path: Path):
    """Walks one gate through RETRY -> ESCALATE -> PASS -> BLOCKED, persisting
    each decision, entirely offline against a tmp_path PROJECT.md."""
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate = "review"

    # First failure: RETRY, count 1.
    stored = gate_state.read(path, gate)
    previous_count = stored["count"] if stored else 0
    state, count = decide_failure(previous_count, "missing tests")
    gate_state.set_state(path, gate, state, "missing tests", count)
    assert (state, count) == ("RETRY", 1)

    # A second reasoning failure escalates, regardless of the reason text.
    stored = gate_state.read(path, gate)
    state, count = decide_failure(stored["count"], "missing tests")
    gate_state.set_state(path, gate, state, "missing tests", count)
    assert (state, count) == ("ESCALATE", 2)

    # The fix lands: PASS advances the gate. decide_failure is not consulted
    # for a pass — the calling workflow decides PASS directly and persists it.
    gate_state.set_state(path, gate, "PASS", "tests added", 0)
    assert gate_state.read(path, gate) == {
        "state": "PASS",
        "reason": "tests added",
        "count": 0,
        "kind": "reasoning",
    }

    # A later phase hits unresolved required findings with no ambiguity to
    # ask about: BLOCKED, also decided by the workflow, not decide_failure.
    gate_state.set_state(path, gate, "BLOCKED", "unresolved required finding", 0)
    assert gate_state.read(path, gate) == {
        "state": "BLOCKED",
        "reason": "unresolved required finding",
        "count": 0,
        "kind": "reasoning",
    }
