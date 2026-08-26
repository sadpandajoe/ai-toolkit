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

from pathlib import Path

from aitk.installer import (
    Target,
    _allowed_owned_dirs,
    _worker_agents,
    desired_targets,
    resolve_paths,
)

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
    }


def test_desired_targets_has_no_duplicate_target_paths(tmp_path: Path):
    paths = _paths(tmp_path)
    desired = desired_targets(paths, with_pgm=True)
    targets = [str(item.target) for item in desired]
    assert len(targets) == len(set(targets))


def test_claude_agents_directory_is_an_allowed_owned_dir(tmp_path: Path):
    paths = _paths(tmp_path)
    assert str(paths.home / ".claude/agents") in _allowed_owned_dirs(paths)
