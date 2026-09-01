"""Per-goal-skill entry-section context budget (PLAN.md's Wave G, item G2).

Each `skills/goals/<name>/SKILL.md` is the entry section Claude Code loads
before any reference file — the state machine that decides which path to
follow. Keeping it small keeps the always-loaded context small; heavier
procedural detail belongs in `skills/goals/<name>/references/*.md`, loaded
only once a path is selected. This module measures each goal skill's
`SKILL.md` byte size against a fixed per-goal budget and reports pass/fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 10KB per goal skill's entry section. Given as a fixed constant (not derived
# from measured sizes) so the budget cannot silently drift upward as skills
# grow — a skill that would exceed it must be trimmed, not have the budget
# raised to fit it.
GOAL_SKILL_BUDGET_BYTES = 10_240


@dataclass(frozen=True)
class SkillBudget:
    name: str
    path: Path
    byte_count: int
    budget: int

    @property
    def passed(self) -> bool:
        return self.byte_count <= self.budget

    @property
    def overage(self) -> int:
        return max(0, self.byte_count - self.budget)


def measure_goal_skills(root: Path) -> list[SkillBudget]:
    """Measure every `skills/goals/*/SKILL.md`'s byte size against budget.

    Returns results sorted by skill name for stable, deterministic output.
    """
    goals_dir = root / "skills/goals"
    results: list[SkillBudget] = []
    if not goals_dir.is_dir():
        return results
    for skill_dir in sorted(goals_dir.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        byte_count = len(skill_file.read_bytes())
        results.append(
            SkillBudget(
                name=skill_dir.name,
                path=skill_file,
                byte_count=byte_count,
                budget=GOAL_SKILL_BUDGET_BYTES,
            )
        )
    return sorted(results, key=lambda result: result.name)
