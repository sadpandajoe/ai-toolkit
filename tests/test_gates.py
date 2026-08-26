"""Tests for the pure gate-decision module (aitk.gates)."""

import pytest

from aitk.gates import GATE_STATES, decide_failure


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
