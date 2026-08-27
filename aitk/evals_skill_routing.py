"""Checker factory for the evals/skill_routing/ fixture family.

Structural proxy for "does this trigger phrase route to the right goal
skill" that needs no model dispatch to verify: a fixture names a phrase and
the goal skill it should uniquely appear in. The check reads each goal
skill's live frontmatter description (not a snapshot in the fixture), so it
catches a description edit that either drops the phrase from its owning
skill or lets it collide with another skill's description — both are real
routing regressions per skills/README.md's "Description first" guidance.
"""

from __future__ import annotations

from pathlib import Path
import re

GOAL_SKILLS = (
    "fix-bug",
    "create-feature",
    "fix-ci",
    "code-review",
    "address-feedback",
    "test-pr",
    "cherry-pick",
)


def _description(skill_md: Path) -> str:
    text = skill_md.read_text()
    match = re.search(r"^description:\s*(.+)$", text, re.M)
    return match.group(1) if match else ""


def make_checker(root: Path):
    descriptions = {
        name: _description(root / "skills/goals" / name / "SKILL.md").lower()
        for name in GOAL_SKILLS
    }

    def checker(fixture: dict) -> tuple[bool, str]:
        expect = fixture["expect_skill"]
        if expect not in descriptions:
            return False, f"unknown expect_skill {expect!r} (not a goal skill)"
        phrase = fixture["phrase"].lower()
        matches = sorted(name for name, desc in descriptions.items() if phrase in desc)
        if expect not in matches:
            return False, f"phrase {phrase!r} not found in {expect}'s description"
        if len(matches) > 1:
            others = [name for name in matches if name != expect]
            return False, f"phrase {phrase!r} also matches {others} — routing is ambiguous"
        return True, f"phrase {phrase!r} uniquely matches {expect}"

    return checker
