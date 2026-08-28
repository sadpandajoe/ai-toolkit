"""Tests for aitk.frontmatter, the minimal PROJECT.md header reader."""

from pathlib import Path

import pytest

from aitk.frontmatter import FrontmatterError, parse_frontmatter, read_frontmatter


def test_no_frontmatter_returns_empty_dict():
    assert parse_frontmatter("# PROJECT\n\nNo header here.\n") == {}


def test_empty_text_returns_empty_dict():
    assert parse_frontmatter("") == {}


def test_flat_scalars_are_coerced():
    text = (
        "---\n"
        "workflow: fix-bug\n"
        "attempt: 1\n"
        "planning_required: true\n"
        "rca_validation_required: false\n"
        "current_gate: none\n"
        "---\n"
        "\n# body\n"
    )
    assert parse_frontmatter(text) == {
        "workflow": "fix-bug",
        "attempt": 1,
        "planning_required": True,
        "rca_validation_required": False,
        "current_gate": "none",
    }


def test_blank_scalar_is_none():
    text = "---\nphase_plan_status:\nverification_status: PASS\n---\n"
    assert parse_frontmatter(text) == {
        "phase_plan_status": None,
        "verification_status": "PASS",
    }


def test_empty_list_is_parsed():
    text = "---\nmodifiers: []\n---\n"
    assert parse_frontmatter(text) == {"modifiers": []}


def test_nested_mapping_one_level_deep():
    text = (
        "---\n"
        "reasoning_attempts:\n"
        "  architecture: 1\n"
        "  phase_plan: 0\n"
        "  implementation: 0\n"
        "---\n"
    )
    assert parse_frontmatter(text) == {
        "reasoning_attempts": {
            "architecture": 1,
            "phase_plan": 0,
            "implementation": 0,
        }
    }


def test_trailing_blank_scalar_followed_by_top_level_key_is_not_nested():
    # A blank scalar's key line ends in ':' exactly like a nested mapping's
    # header does -- only a following indented line makes it nested.
    text = "---\nphase_plan_status:\nverification_status: PASS\n---\n"
    result = parse_frontmatter(text)
    assert result["phase_plan_status"] is None
    assert isinstance(result["phase_plan_status"], type(None))


def test_full_project_md_v2_header_shape():
    text = (
        "---\n"
        "workflow: audit-v2-spec\n"
        "complexity: COMPLEX\n"
        "classification_confidence: 9\n"
        "current_phase: wave-a\n"
        "current_gate: none\n"
        "attempt: 1\n"
        "planning_required: true\n"
        "rca_validation_required: false\n"
        "modifiers: []\n"
        "size: XL\n"
        "execution_shape: MULTI_PHASE\n"
        "phaseability_reason: four independent waves\n"
        "phase_complexity: STANDARD\n"
        "phase_size: S\n"
        "phase_execution_shape: SINGLE_PHASE\n"
        "architecture_plan_status: PASS\n"
        "phase_plan_status:\n"
        "verification_status: PASS\n"
        "reasoning_attempts:\n"
        "  architecture: 1\n"
        "  phase_plan: 0\n"
        "  implementation: 0\n"
        "---\n"
        "\n## Overview\n"
    )
    result = parse_frontmatter(text)
    assert result["modifiers"] == []
    assert result["phase_plan_status"] is None
    assert result["reasoning_attempts"] == {
        "architecture": 1,
        "phase_plan": 0,
        "implementation": 0,
    }
    assert result["size"] == "XL"
    assert result["classification_confidence"] == 9
    assert result["planning_required"] is True


def test_unterminated_header_raises():
    with pytest.raises(FrontmatterError, match="not terminated"):
        parse_frontmatter("---\nworkflow: fix-bug\n")


def test_indented_line_with_no_parent_raises():
    with pytest.raises(FrontmatterError, match="no parent"):
        parse_frontmatter("---\n  orphan: value\n---\n")


def test_read_frontmatter_reads_from_a_real_file(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("---\nworkflow: fix-bug\nattempt: 2\n---\n\nbody\n")
    assert read_frontmatter(path) == {"workflow": "fix-bug", "attempt": 2}
