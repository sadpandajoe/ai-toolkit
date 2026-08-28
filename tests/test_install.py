"""Installer coverage for agents/claude/*.md worker files.

agents/claude/*.md sits outside aitk.doctor's CONTENT_DIRECTORIES sweep, so
this file is the real gate proving the installer's manifest actually picks
up worker agent files as symlink targets — installed at ~/.claude/agents/
so Claude Code discovers them as native subagents. The tracked source lives
at agents/claude/, not .claude/agents/, because the repo's own .claude/ is
gitignored (it holds this toolkit project's own local Claude Code session
state, not installable source content). Exercises the real repository tree
(read-only: desired_targets() is a pure computation, never touches the
filesystem) plus a tmp_path fixture to prove the discovery/target-shape
logic in isolation from what happens to be committed today.
"""

import json
from pathlib import Path

from aitk.installer import (
    Target,
    _allowed_owned_dirs,
    _public_skills,
    _worker_agents,
    desired_targets,
    resolve_paths,
)
from aitk.interfaces import _discovered_skills, validate_skill_interfaces
from aitk.routing import COMPLEXITY_VALUES

REPO_ROOT = Path(__file__).resolve().parent.parent


def _paths(tmp_path: Path):
    return resolve_paths(
        REPO_ROOT,
        home=tmp_path / "home",
        codex_home=tmp_path / "codex",
        agents_dir=tmp_path / "agents",
    )


def test_worker_agents_discovers_real_source_directory():
    discovered = dict(_worker_agents(REPO_ROOT))
    assert discovered["debug-worker"] == REPO_ROOT / "agents/claude/debug-worker.md"
    assert discovered["test-worker"] == REPO_ROOT / "agents/claude/test-worker.md"
    assert (
        discovered["implementation-worker"]
        == REPO_ROOT / "agents/claude/implementation-worker.md"
    )
    assert discovered["planner"] == REPO_ROOT / "agents/claude/planner.md"


def test_worker_agents_ignores_symlinks(tmp_path: Path):
    root = tmp_path / "repo"
    agents = root / "agents/claude"
    agents.mkdir(parents=True)
    real = agents / "real-worker.md"
    real.write_text("---\nname: real-worker\n---\n")
    (agents / "linked-worker.md").symlink_to(real)
    discovered = dict(_worker_agents(root))
    assert discovered == {"real-worker": real}


def test_worker_agents_empty_when_directory_absent(tmp_path: Path):
    assert _worker_agents(tmp_path / "no-such-repo") == []


def test_desired_targets_includes_claude_agent_symlink(tmp_path: Path):
    paths = _paths(tmp_path)
    desired = desired_targets(paths, with_pgm=False)
    matches = [item for item in desired if item.name == "claude-agent:debug-worker"]
    assert len(matches) == 1
    target = matches[0]
    assert target == Target(
        "claude-agent:debug-worker",
        "symlink",
        paths.home / ".claude/agents/debug-worker.md",
        REPO_ROOT / "agents/claude/debug-worker.md",
    )


def test_desired_targets_includes_all_worker_agents(tmp_path: Path):
    paths = _paths(tmp_path)
    desired = desired_targets(paths, with_pgm=False)
    names = {item.name for item in desired if item.name.startswith("claude-agent:")}
    assert names == {
        "claude-agent:debug-worker",
        "claude-agent:test-worker",
        "claude-agent:implementation-worker",
        "claude-agent:planner",
        "claude-agent:review-worker",
        "claude-agent:deep-review-worker",
    }


def test_desired_targets_has_no_duplicate_target_paths(tmp_path: Path):
    paths = _paths(tmp_path)
    desired = desired_targets(paths, with_pgm=True)
    targets = [str(item.target) for item in desired]
    assert len(targets) == len(set(targets))


def test_claude_agents_directory_is_an_allowed_owned_dir(tmp_path: Path):
    paths = _paths(tmp_path)
    assert str(paths.home / ".claude/agents") in _allowed_owned_dirs(paths)


def test_planner_cites_the_current_complexity_tier_vocabulary():
    text = (REPO_ROOT / "agents/claude/planner.md").read_text()
    assert "COMPLEX" in text
    assert COMPLEXITY_VALUES == {"TRIVIAL", "STANDARD", "COMPLEX"}
    for stale_tier in ("MODERATE",):
        assert stale_tier not in text


def _write_goal_skill(root: Path, name: str) -> Path:
    skill_dir = root / "skills/goals" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\nBody.\n")
    agents_dir = skill_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "openai.yaml").write_text("allow_implicit_invocation: true\n")
    return skill_dir


def _write_skills_json(root: Path, entries: list[dict[str, str]]) -> None:
    interfaces_dir = root / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)
    (interfaces_dir / "skills.json").write_text(
        json.dumps({"version": 1, "skills": entries})
    )


def test_discovered_skills_includes_the_goals_tier(tmp_path: Path):
    root = tmp_path / "repo"
    _write_goal_skill(root, "fix-bug")
    discovered = _discovered_skills(root)
    assert discovered["fix-bug"] == "skills/goals/fix-bug"


def test_a_declared_goal_skill_passes_validation(tmp_path: Path):
    root = tmp_path / "repo"
    _write_goal_skill(root, "fix-bug")
    _write_skills_json(
        root,
        [
            {
                "name": "fix-bug",
                "path": "skills/goals/fix-bug",
                "classification": "public_direct",
            }
        ],
    )
    assert validate_skill_interfaces(root) == []


def test_an_undeclared_goal_skill_fails_validation(tmp_path: Path):
    root = tmp_path / "repo"
    _write_goal_skill(root, "fix-bug")
    _write_skills_json(root, [])
    assert "unclassified skill: fix-bug" in validate_skill_interfaces(root)


def test_public_skills_derives_install_target_from_declared_path_not_the_glob(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    _write_goal_skill(root, "fix-bug")
    _write_skills_json(
        root,
        [
            {
                "name": "fix-bug",
                "path": "skills/goals/fix-bug",
                "classification": "public_direct",
            }
        ],
    )
    assert _public_skills(root, with_pgm=False) == [
        ("fix-bug", root / "skills/goals/fix-bug")
    ]


def test_desired_targets_symlinks_a_goal_skill_by_declared_path(tmp_path: Path):
    root = tmp_path / "repo"
    _write_goal_skill(root, "fix-bug")
    _write_skills_json(
        root,
        [
            {
                "name": "fix-bug",
                "path": "skills/goals/fix-bug",
                "classification": "public_direct",
            }
        ],
    )
    paths = resolve_paths(
        root,
        home=tmp_path / "home",
        codex_home=tmp_path / "codex",
        agents_dir=tmp_path / "agents",
    )
    desired = desired_targets(paths, with_pgm=False)
    by_name = {item.name: item for item in desired}
    assert by_name["claude-skill:fix-bug"].source == root / "skills/goals/fix-bug"
    assert by_name["agent-skill:fix-bug"].source == root / "skills/goals/fix-bug"


def test_fix_bug_goal_skill_is_registered_and_installable():
    discovered = _discovered_skills(REPO_ROOT)
    assert discovered["fix-bug"] == "skills/goals/fix-bug"
    assert validate_skill_interfaces(REPO_ROOT) == []
    assert ("fix-bug", REPO_ROOT / "skills/goals/fix-bug") in _public_skills(
        REPO_ROOT, with_pgm=False
    )


def test_fix_ci_goal_skill_is_registered_and_installable():
    discovered = _discovered_skills(REPO_ROOT)
    assert discovered["fix-ci"] == "skills/goals/fix-ci"
    assert validate_skill_interfaces(REPO_ROOT) == []
    assert ("fix-ci", REPO_ROOT / "skills/goals/fix-ci") in _public_skills(
        REPO_ROOT, with_pgm=False
    )


def test_code_review_goal_skill_is_registered_and_installable():
    discovered = _discovered_skills(REPO_ROOT)
    assert discovered["code-review"] == "skills/goals/code-review"
    assert validate_skill_interfaces(REPO_ROOT) == []
    assert ("code-review", REPO_ROOT / "skills/goals/code-review") in _public_skills(
        REPO_ROOT, with_pgm=False
    )


def test_test_pr_goal_skill_is_registered_and_installable():
    discovered = _discovered_skills(REPO_ROOT)
    assert discovered["test-pr"] == "skills/goals/test-pr"
    assert validate_skill_interfaces(REPO_ROOT) == []
    assert ("test-pr", REPO_ROOT / "skills/goals/test-pr") in _public_skills(
        REPO_ROOT, with_pgm=False
    )


def test_address_feedback_goal_skill_is_registered_and_installable():
    discovered = _discovered_skills(REPO_ROOT)
    assert discovered["address-feedback"] == "skills/goals/address-feedback"
    assert validate_skill_interfaces(REPO_ROOT) == []
    assert (
        "address-feedback",
        REPO_ROOT / "skills/goals/address-feedback",
    ) in _public_skills(REPO_ROOT, with_pgm=False)
