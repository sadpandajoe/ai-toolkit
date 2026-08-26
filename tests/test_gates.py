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


def test_first_failure_for_a_reason_retries():
    state, count = decide_failure(None, 0, "flaky assertion")
    assert (state, count) == ("RETRY", 1)


def test_second_consecutive_failure_for_same_reason_escalates():
    state, count = decide_failure("flaky assertion", 1, "flaky assertion")
    assert (state, count) == ("ESCALATE", 2)


def test_repeated_escalation_stays_escalated_and_keeps_counting():
    state, count = decide_failure("flaky assertion", 2, "flaky assertion")
    assert (state, count) == ("ESCALATE", 3)


def test_different_reason_resets_the_counter_to_retry():
    state, count = decide_failure("flaky assertion", 2, "missing fixture")
    assert (state, count) == ("RETRY", 1)


def test_rejects_empty_reason():
    with pytest.raises(ValueError, match="reason must be"):
        decide_failure(None, 0, "")


def test_rejects_negative_previous_count():
    with pytest.raises(ValueError, match="previous_count must be"):
        decide_failure("x", -1, "x")


def test_rejects_non_integer_previous_count():
    with pytest.raises(ValueError, match="previous_count must be"):
        decide_failure("x", True, "x")


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
    state, count = decide_failure(None, 0, "missing tests")
    gate_state.set_state(path, "review", state, "missing tests", count)
    assert gate_state.read(path, "review") == {
        "state": "RETRY",
        "reason": "missing tests",
        "count": 1,
    }


def test_repeat_count_builds_across_calls_via_persisted_history():
    # Simulate a caller re-deciding against the previously persisted record
    # on each call, the way a real workflow would after a context reset.
    previous_reason, previous_count = None, 0
    reasons = ["missing tests", "missing tests", "missing tests"]
    seen_states = []
    for reason in reasons:
        state, count = decide_failure(previous_reason, previous_count, reason)
        seen_states.append((state, count))
        previous_reason, previous_count = reason, count
    assert seen_states == [("RETRY", 1), ("ESCALATE", 2), ("ESCALATE", 3)]


def test_repeat_count_resets_when_persisted_gate_state_reason_changes(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    state, count = decide_failure(None, 0, "missing tests")
    gate_state.set_state(path, "review", state, "missing tests", count)

    stored = gate_state.read(path, "review")
    state, count = decide_failure(stored["reason"], stored["count"], "missing tests")
    gate_state.set_state(path, "review", state, "missing tests", count)
    assert gate_state.read(path, "review") == {
        "state": "ESCALATE",
        "reason": "missing tests",
        "count": 2,
    }

    stored = gate_state.read(path, "review")
    state, count = decide_failure(stored["reason"], stored["count"], "flaky test")
    gate_state.set_state(path, "review", state, "flaky test", count)
    assert gate_state.read(path, "review") == {
        "state": "RETRY",
        "reason": "flaky test",
        "count": 1,
    }


# --- scripted end-to-end scenario through the decision table --------------


def test_scripted_scenario_retry_then_escalate_then_pass_then_blocked(tmp_path: Path):
    """Walks one gate through RETRY -> ESCALATE -> PASS -> BLOCKED, persisting
    each decision, entirely offline against a tmp_path PROJECT.md."""
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate = "review"

    # First failure for a reason: RETRY, count 1.
    stored = gate_state.read(path, gate)
    previous_reason = stored["reason"] if stored else None
    previous_count = stored["count"] if stored else 0
    state, count = decide_failure(previous_reason, previous_count, "missing tests")
    gate_state.set_state(path, gate, state, "missing tests", count)
    assert (state, count) == ("RETRY", 1)

    # Same reason fails again: ESCALATE, count 2.
    stored = gate_state.read(path, gate)
    state, count = decide_failure(stored["reason"], stored["count"], "missing tests")
    gate_state.set_state(path, gate, state, "missing tests", count)
    assert (state, count) == ("ESCALATE", 2)

    # The fix lands: PASS advances the gate. decide_failure is not consulted
    # for a pass — the calling workflow decides PASS directly and persists it.
    gate_state.set_state(path, gate, "PASS", "tests added", 0)
    assert gate_state.read(path, gate) == {
        "state": "PASS",
        "reason": "tests added",
        "count": 0,
    }

    # A later phase hits unresolved required findings with no ambiguity to
    # ask about: BLOCKED, also decided by the workflow, not decide_failure.
    gate_state.set_state(path, gate, "BLOCKED", "unresolved required finding", 0)
    assert gate_state.read(path, gate) == {
        "state": "BLOCKED",
        "reason": "unresolved required finding",
        "count": 0,
    }
