"""Tests for the PROJECT.md v2 state modules: checkpoint.read_snapshot() and
the routing-state block (aitk.routing)."""

from pathlib import Path

import pytest

from aitk import checkpoint, gate_state, routing
from aitk.checkpoint import CheckpointError, canonical_json, read_snapshot
from aitk.size_axis import SizeAxisError, validate_size_axis

BEGIN = "<!-- aitk-checkpoint:v1 -->"
END = "<!-- /aitk-checkpoint -->"

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_block(path: Path, body: str) -> None:
    path.write_text(f"# PROJECT\n\n{BEGIN}\n{body}\n{END}\n")


def _write_routing_block(path: Path, body: str) -> None:
    path.write_text(f"# PROJECT\n\n{routing.BEGIN}\n{body}\n{routing.END}\n")


def test_missing_file_returns_none(tmp_path: Path):
    assert read_snapshot(tmp_path / "PROJECT.md") is None


def test_file_without_checkpoint_markers_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo checkpoint block here.\n")
    assert read_snapshot(path) is None


def test_valid_marker_returns_dict(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    payload = {"schema_version": 1, "workflow": "fix-bug", "phase": "investigate"}
    _write_block(path, canonical_json(payload))
    assert read_snapshot(path) == payload


def test_malformed_json_raises_checkpoint_error(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    _write_block(path, "{not valid json")
    with pytest.raises(CheckpointError, match="malformed"):
        read_snapshot(path)


def test_non_object_json_raises_checkpoint_error(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    _write_block(path, "[1, 2, 3]")
    with pytest.raises(CheckpointError, match="must be an object"):
        read_snapshot(path)


def test_one_marker_without_its_pair_raises_checkpoint_error(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{BEGIN}\n{{}}\n")
    with pytest.raises(CheckpointError, match="exactly one marker pair"):
        read_snapshot(path)


def test_relative_path_raises_checkpoint_error():
    with pytest.raises(CheckpointError, match="not normalized"):
        read_snapshot(Path("PROJECT.md"))


# --- aitk.routing: routing-state block round-trip -------------------------


def test_routing_read_missing_file_returns_none(tmp_path: Path):
    assert routing.read(tmp_path / "PROJECT.md") is None


def test_routing_read_file_without_markers_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo routing block here.\n")
    assert routing.read(path) is None


def test_routing_set_then_read_round_trips(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    payload = routing.set_classification(path, "STANDARD", 8, "multi-file change")
    assert routing.read(path) == payload
    assert payload == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 8,
        "reason": "multi-file change",
    }


def test_routing_set_classification_updates_existing_block(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    routing.set_classification(path, "TRIVIAL", 9, "one-line fix")
    routing.set_classification(path, "COMPLEX", 6, "reclassified")
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "COMPLEX",
        "confidence": 6,
        "reason": "reclassified",
    }
    # exactly one marker pair survives the update
    content = path.read_text()
    assert content.count(routing.BEGIN) == 1
    assert content.count(routing.END) == 1


def test_routing_set_classification_rejects_invalid_complexity(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(routing.RoutingStateError, match="complexity is invalid"):
        routing.set_classification(path, "MODERATE", 5, "pre-rename tier name")
    assert routing.read(path) is None


def test_routing_read_normalizes_legacy_moderate_to_standard(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    legacy_payload = {
        "schema_version": 1,
        "complexity": "MODERATE",
        "confidence": 8,
        "reason": "written under the pre-rename schema",
    }
    _write_routing_block(path, canonical_json(legacy_payload))
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 8,
        "reason": "written under the pre-rename schema",
    }


def test_routing_read_normalizes_legacy_standard_to_complex(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    legacy_payload = {
        "schema_version": 1,
        "complexity": "STANDARD",
        "confidence": 6,
        "reason": "written under the pre-rename schema",
    }
    _write_routing_block(path, canonical_json(legacy_payload))
    assert routing.read(path)["complexity"] == "COMPLEX"
    assert routing.read(path)["schema_version"] == 2


def test_routing_read_does_not_remap_current_schema_standard(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    routing.set_classification(path, "STANDARD", 8, "current schema, not legacy")
    assert routing.read(path)["complexity"] == "STANDARD"


def test_routing_set_classification_rejects_out_of_range_confidence(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(routing.RoutingStateError, match="confidence must be"):
        routing.set_classification(path, "TRIVIAL", 11, "reason")


def test_routing_set_classification_rejects_empty_reason(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(routing.RoutingStateError, match="reason must be"):
        routing.set_classification(path, "TRIVIAL", 5, "")


def test_routing_set_classification_requires_existing_file(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    with pytest.raises(CheckpointError, match="routing-state artifact is missing"):
        routing.set_classification(path, "TRIVIAL", 5, "reason")


def test_routing_read_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{routing.BEGIN}\n{{not valid json\n{routing.END}\n")
    with pytest.raises(routing.RoutingStateError, match="malformed"):
        routing.read(path)


def test_routing_one_marker_without_its_pair_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{routing.BEGIN}\n{{}}\n")
    with pytest.raises(routing.RoutingStateError, match="exactly one marker pair"):
        routing.read(path)


# --- aitk.gate_state: gate-state block round-trip --------------------------


def test_gate_state_read_missing_file_returns_none(tmp_path: Path):
    assert gate_state.read(tmp_path / "PROJECT.md") is None


def test_gate_state_read_file_without_markers_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n\nNo gate block here.\n")
    assert gate_state.read(path) is None


def test_gate_state_set_then_read_round_trips(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    record = gate_state.set_state(path, "review", "RETRY", "missing tests", 1)
    assert record == {
        "state": "RETRY",
        "reason": "missing tests",
        "count": 1,
        "kind": "reasoning",
    }
    assert gate_state.read(path, "review") == record
    assert gate_state.read(path) == {"review": record}


def test_gate_state_set_preserves_other_gates(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)
    gate_state.set_state(path, "rca", "PASS", "root cause confirmed", 0)
    assert gate_state.read(path) == {
        "review": {
            "state": "RETRY",
            "reason": "missing tests",
            "count": 1,
            "kind": "reasoning",
        },
        "rca": {
            "state": "PASS",
            "reason": "root cause confirmed",
            "count": 0,
            "kind": "reasoning",
        },
    }
    content = path.read_text()
    assert content.count(gate_state.BEGIN) == 1
    assert content.count(gate_state.END) == 1


def test_gate_state_set_updates_existing_gate(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)
    gate_state.set_state(path, "review", "ESCALATE", "missing tests", 2)
    assert gate_state.read(path, "review") == {
        "state": "ESCALATE",
        "reason": "missing tests",
        "count": 2,
        "kind": "reasoning",
    }


def test_gate_state_read_unknown_gate_returns_none(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(path, "review", "PASS", "clean", 0)
    assert gate_state.read(path, "rca") is None


def test_gate_state_set_classification_rejects_invalid_state(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(gate_state.GateStateError, match="state is invalid"):
        gate_state.set_state(path, "review", "NOT_A_STATE", "reason", 0)


def test_gate_state_set_rejects_negative_count(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    with pytest.raises(gate_state.GateStateError, match="count must be"):
        gate_state.set_state(path, "review", "RETRY", "reason", -1)


def test_gate_state_set_requires_existing_file(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    with pytest.raises(CheckpointError, match="gate-state artifact is missing"):
        gate_state.set_state(path, "review", "PASS", "reason", 0)


def test_gate_state_read_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(
        f"# PROJECT\n\n{gate_state.BEGIN}\n{{not valid json\n{gate_state.END}\n"
    )
    with pytest.raises(gate_state.GateStateError, match="malformed"):
        gate_state.read(path)


def test_gate_state_one_marker_without_its_pair_raises(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text(f"# PROJECT\n\n{gate_state.BEGIN}\n{{}}\n")
    with pytest.raises(gate_state.GateStateError, match="exactly one marker pair"):
        gate_state.read(path)


# --- Multi-phase checkpoint/resume (create-feature's Multi-Phase Path) -----
#
# create-feature's Multi-Phase Path (skills/goals/create-feature/SKILL.md)
# deliberately does not use aitk.checkpoint's initialize()/advance() -- that
# mechanism resumes only through a fixed, pre-declared phase list keyed to a
# named workflow contract in interfaces/contracts.json, and cannot accept
# the runtime-derived phase names decompose-work.md produces per feature.
# Cross-phase persistence instead composes aitk.size_axis (per-phase
# reclassification) with aitk.gate_state under a gate name scoped per phase.
# These tests prove that composition survives a simulated context reset: a
# phase's own gate history is independent of every other phase's, and
# re-reading the file from scratch (a fresh gate_state.read() call, not a
# cached object) recovers the full history for every phase already run.


def test_multi_phase_gate_history_is_independent_per_phase(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    # Phase 1 ("layout-editing") fails once, then passes.
    gate_state.set_state(
        path, "create-feature-phase-layout-editing-verify", "RETRY", "missing test", 1
    )
    gate_state.set_state(
        path, "create-feature-phase-layout-editing-verify", "PASS", "clean", 0
    )

    # Phase 2 ("persistence") starts fresh -- its own gate name, own history.
    gate_state.set_state(
        path, "create-feature-phase-persistence-verify", "RETRY", "flaky fixture", 1
    )

    # A fresh read (simulating a resumed context) sees both phases intact:
    # phase 2's RETRY does not touch phase 1's PASS, and phase 1's earlier
    # RETRY does not leak into phase 2's count.
    history = gate_state.read(path)
    assert history == {
        "create-feature-phase-layout-editing-verify": {
            "state": "PASS",
            "reason": "clean",
            "count": 0,
            "kind": "reasoning",
        },
        "create-feature-phase-persistence-verify": {
            "state": "RETRY",
            "reason": "flaky fixture",
            "count": 1,
            "kind": "reasoning",
        },
    }


def test_multi_phase_resume_uses_current_phase_to_scope_gate_history(tmp_path: Path):
    # Models create-feature's Multi-Phase Path step (e): the gate name is
    # templated from current_phase, so a resuming orchestrator that already
    # knows current_phase (hand-set PROJECT.md frontmatter -- no aitk reader
    # owns that field, see aitk/size_axis.py's module docstring) can look up
    # exactly what the in-flight phase has already tried, without touching
    # any other phase's history.
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    gate_state.set_state(
        path, "create-feature-phase-layout-editing-verify", "PASS", "clean", 0
    )
    gate_state.set_state(
        path, "create-feature-phase-persistence-verify", "ESCALATE", "flaky fixture", 2
    )

    current_phase = "persistence"  # as if just read off resumed frontmatter
    resumed_gate = gate_state.read(path, f"create-feature-phase-{current_phase}-verify")
    assert resumed_gate == {
        "state": "ESCALATE",
        "reason": "flaky fixture",
        "count": 2,
        "kind": "reasoning",
    }
    # The completed phase's history survives untouched alongside it.
    assert gate_state.read(path, "create-feature-phase-layout-editing-verify") == {
        "state": "PASS",
        "reason": "clean",
        "count": 0,
        "kind": "reasoning",
    }


def test_multi_phase_reclassification_is_independent_per_phase():
    # Each phase reclassifies complexity/size on its own (source plan: "then
    # classify each phase independently") -- two phases with different
    # phase-level classifications must both validate independently, without
    # one phase's fields constraining or leaking into the other's.
    phase_one = {
        "phase_complexity": "STANDARD",
        "phase_size": "M",
        "phase_execution_shape": "SINGLE_PHASE",
        "phase_plan_status": "PASS",
        "verification_status": "PASS",
    }
    phase_two = {
        "phase_complexity": "COMPLEX",
        "phase_size": "S",
        "phase_execution_shape": "SINGLE_PHASE",
        "phase_plan_status": "RETRY",
        "verification_status": None,
    }
    validate_size_axis(phase_one)
    validate_size_axis(phase_two)


# --- aitk.checkpoint: initialize()/advance() ownership and resume ----------
#
# These exercise the real "fix-bug" contract in interfaces/contracts.json
# (phases: reproduce -> diagnose -> implement -> verify -> review), the only
# state-machine path with no prior test coverage anywhere in the repo.


def test_initialize_then_advance_survives_interrupt_alongside_sibling_blocks(
    tmp_path: Path,
):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    started = checkpoint.initialize(REPO_ROOT, "fix-bug", path)
    assert started.workflow == "fix-bug"
    assert started.phase == "reproduce"
    assert started.generation == 0

    routing.set_classification(path, "STANDARD", 8, "multi-file change")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)

    # Interrupt: drop every in-memory result and re-read the file fresh.
    del started
    snapshot = read_snapshot(path)
    assert snapshot["workflow"] == "fix-bug"
    assert snapshot["phase"] == "reproduce"
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 8,
        "reason": "multi-file change",
    }
    assert gate_state.read(path, "review") == {
        "state": "RETRY",
        "reason": "missing tests",
        "count": 1,
        "kind": "reasoning",
    }

    # All three blocks coexist as exactly one marker pair each -- each
    # writer rewrites the whole file, so this is the real coexistence risk.
    content = path.read_text()
    assert content.count(BEGIN) == 1 and content.count(END) == 1
    assert content.count(routing.BEGIN) == 1 and content.count(routing.END) == 1
    assert content.count(gate_state.BEGIN) == 1 and content.count(gate_state.END) == 1

    # Resume: advance the checkpoint into the next legal phase.
    resumed = checkpoint.advance(REPO_ROOT, "fix-bug", path, "diagnose")
    assert resumed.phase == "diagnose"
    assert resumed.generation == 1

    post_resume = read_snapshot(path)
    assert post_resume["phase"] == "diagnose"
    assert post_resume["generation"] == 1
    # The checkpoint rewrite must not disturb the sibling blocks.
    assert routing.read(path)["complexity"] == "STANDARD"
    assert gate_state.read(path, "review")["state"] == "RETRY"


def test_advance_rejects_a_transition_not_in_the_contract(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    checkpoint.initialize(REPO_ROOT, "fix-bug", path)
    with pytest.raises(CheckpointError, match="illegal checkpoint transition"):
        checkpoint.advance(REPO_ROOT, "fix-bug", path, "review")


def test_initialize_rejects_ownership_by_a_different_workflow(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    checkpoint.initialize(REPO_ROOT, "fix-bug", path)
    with pytest.raises(
        CheckpointError,
        match="another durable workflow already owns this checkpoint artifact",
    ):
        checkpoint.initialize(REPO_ROOT, "create-feature", path)


def test_initialize_replace_existing_rejects_pending_effects(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")
    checkpoint.initialize(REPO_ROOT, "fix-bug", path)
    checkpoint.reserve(REPO_ROOT, "fix-bug", path, "commit_sha", "abc123")
    with pytest.raises(
        CheckpointError, match="cannot replace a checkpoint with pending effects"
    ):
        checkpoint.initialize(REPO_ROOT, "fix-bug", path, replace_existing=True)


# --- aitk.size_axis: PROJECT.md v2 size-axis schema -------------------------
#
# These fields are frontmatter, not a marker-block state module -- no YAML
# frontmatter parser exists anywhere in aitk/ yet, so validate_size_axis()
# is a pure function over an already-parsed dict, not a PROJECT.md reader.


def test_an_unfilled_template_validates_cleanly():
    # PROJECT_TEMPLATE.md ships every size-axis field blank; every fresh
    # TRIVIAL/STANDARD project must start valid with none of them set.
    unfilled = {
        "size": None,
        "execution_shape": None,
        "phaseability_reason": None,
        "phase_complexity": None,
        "phase_size": None,
        "phase_execution_shape": None,
        "architecture_plan_status": None,
        "phase_plan_status": None,
        "verification_status": None,
        "reasoning_attempts": None,
    }
    validate_size_axis(unfilled)  # must not raise
    validate_size_axis({})  # absent keys are equivalent to None


def test_a_fully_populated_multi_phase_payload_validates():
    # Mirrors the source plan's create-feature MULTI_PHASE example.
    validate_size_axis(
        {
            "size": "XL",
            "execution_shape": "MULTI_PHASE",
            "phaseability_reason": (
                "editor has independent state, layout, persistence, "
                "history workstreams"
            ),
            "phase_complexity": "STANDARD",
            "phase_size": "M",
            "phase_execution_shape": "SINGLE_PHASE",
            "architecture_plan_status": "PASS",
            "phase_plan_status": "PASS",
            "verification_status": "RETRY",
            "reasoning_attempts": {
                "architecture": 1,
                "phase_plan": 0,
                "implementation": 0,
            },
        }
    )


def test_unrelated_frontmatter_keys_are_ignored():
    # This module owns only the size-axis slice of PROJECT.md's frontmatter;
    # the v1 fields (workflow, complexity, current_phase, ...) are someone
    # else's schema and must not be rejected here.
    validate_size_axis({"workflow": "fix-bug", "complexity": "TRIVIAL", "size": "S"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("size", "MEDIUM"),
        ("execution_shape", "PARALLEL_PHASE"),
        ("phase_complexity", "MODERATE"),
        ("phase_size", "XXL"),
        ("phase_execution_shape", "SINGLE_PHASE "),
        ("architecture_plan_status", "DONE"),
        ("phase_plan_status", "OK"),
        ("verification_status", "PENDING"),
    ],
)
def test_an_invalid_enum_value_is_rejected(field, value):
    with pytest.raises(SizeAxisError, match=field):
        validate_size_axis({field: value})


def test_phaseability_reason_must_be_a_nonempty_string():
    with pytest.raises(SizeAxisError, match="phaseability_reason"):
        validate_size_axis({"phaseability_reason": ""})


def test_reasoning_attempts_rejects_a_missing_unit():
    with pytest.raises(SizeAxisError, match="reasoning_attempts"):
        validate_size_axis({"reasoning_attempts": {"architecture": 1, "phase_plan": 0}})


def test_reasoning_attempts_rejects_an_unknown_unit():
    with pytest.raises(SizeAxisError, match="reasoning_attempts"):
        validate_size_axis(
            {
                "reasoning_attempts": {
                    "architecture": 1,
                    "phase_plan": 0,
                    "implementation": 0,
                    "review": 0,
                }
            }
        )


def test_reasoning_attempts_rejects_a_negative_count():
    with pytest.raises(SizeAxisError, match="reasoning_attempts.implementation"):
        validate_size_axis(
            {
                "reasoning_attempts": {
                    "architecture": 1,
                    "phase_plan": 0,
                    "implementation": -1,
                }
            }
        )


def test_reasoning_attempts_rejects_a_bool_disguised_as_an_int():
    with pytest.raises(SizeAxisError, match="reasoning_attempts.phase_plan"):
        validate_size_axis(
            {
                "reasoning_attempts": {
                    "architecture": 1,
                    "phase_plan": True,
                    "implementation": 0,
                }
            }
        )
