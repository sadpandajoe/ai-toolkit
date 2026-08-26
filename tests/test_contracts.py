"""State and specialist contracts.

Part 1: PROJECT.md v2 schema round-trip — proves the three independent state
modules (checkpoint, routing, gate_state) coexist in one file without one's
marker block corrupting another's, and that `aitk project-state` surfaces
all three together.

Part 2: agents/codex/*.md specialist contracts — the Codex-side counterpart
to agents/claude/*.md. No prior convention exists in this repo for a Codex
contract file's frontmatter shape; this establishes one (name, routes,
responsibility, domain) and proves the three files satisfy it consistently.
"""

import json
from pathlib import Path

from aitk import gate_state, routing
from aitk.checkpoint import canonical_json, read_snapshot
from aitk.cli import main
from aitk.doctor import _frontmatter

CHECKPOINT_BEGIN = "<!-- aitk-checkpoint:v1 -->"
CHECKPOINT_END = "<!-- /aitk-checkpoint -->"


def _write_checkpoint_block(path: Path, payload: dict[str, object]) -> None:
    existing = path.read_text() if path.is_file() else ""
    block = f"{CHECKPOINT_BEGIN}\n{canonical_json(payload)}\n{CHECKPOINT_END}"
    separator = "" if not existing or existing.endswith("\n\n") else "\n"
    path.write_text(existing + separator + block + "\n")


def test_three_state_blocks_coexist_and_round_trip_independently(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    checkpoint_payload = {
        "schema_version": 1,
        "workflow": "fix-bug",
        "phase": "implement",
    }
    _write_checkpoint_block(path, checkpoint_payload)
    routing.set_classification(path, "STANDARD", 7, "touches three modules")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)

    # Each block round-trips through its own module, undisturbed by the others.
    assert read_snapshot(path) == checkpoint_payload
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "STANDARD",
        "confidence": 7,
        "reason": "touches three modules",
    }
    assert gate_state.read(path) == {
        "review": {"state": "RETRY", "reason": "missing tests", "count": 1}
    }

    content = path.read_text()
    for begin, end in (
        (CHECKPOINT_BEGIN, CHECKPOINT_END),
        (routing.BEGIN, routing.END),
        (gate_state.BEGIN, gate_state.END),
    ):
        assert content.count(begin) == 1
        assert content.count(end) == 1


def test_updating_one_block_leaves_the_others_untouched(tmp_path: Path):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    checkpoint_payload = {"schema_version": 1, "workflow": "fix-bug", "phase": "plan"}
    _write_checkpoint_block(path, checkpoint_payload)
    routing.set_classification(path, "TRIVIAL", 9, "one-line fix")
    gate_state.set_state(path, "review", "RETRY", "missing tests", 1)

    # Mutate routing and gate state again; the checkpoint block, written first
    # and never touched by either module, must survive unchanged.
    routing.set_classification(path, "COMPLEX", 6, "reclassified after review")
    gate_state.set_state(path, "review", "ESCALATE", "missing tests", 2)
    gate_state.set_state(path, "rca", "PASS", "root cause confirmed", 0)

    assert read_snapshot(path) == checkpoint_payload
    assert routing.read(path) == {
        "schema_version": 2,
        "complexity": "COMPLEX",
        "confidence": 6,
        "reason": "reclassified after review",
    }
    assert gate_state.read(path) == {
        "review": {"state": "ESCALATE", "reason": "missing tests", "count": 2},
        "rca": {"state": "PASS", "reason": "root cause confirmed", "count": 0},
    }


def test_project_state_cli_surfaces_all_three_blocks_together(tmp_path: Path, capsys):
    path = tmp_path / "PROJECT.md"
    path.write_text("# PROJECT\n")

    checkpoint_payload = {
        "schema_version": 1,
        "workflow": "create-feature",
        "phase": "verify",
    }
    _write_checkpoint_block(path, checkpoint_payload)
    routing.set_classification(path, "COMPLEX", 8, "multi-phase build")
    gate_state.set_state(path, "verify", "PASS", "suite green", 0)

    exit_code = main(["project-state", "--file", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["file"] == str(path)
    assert payload["checkpoint"] == checkpoint_payload
    assert payload["routing"] == {
        "schema_version": 2,
        "complexity": "COMPLEX",
        "confidence": 8,
        "reason": "multi-phase build",
    }
    assert payload["gates"] == {
        "verify": {"state": "PASS", "reason": "suite green", "count": 0}
    }


REPO_ROOT = Path(__file__).resolve().parent.parent
CODEX_CONTRACT_NAMES = ("rca", "reviewer", "plan-validator")


def test_codex_contracts_exist_and_are_non_empty():
    for name in CODEX_CONTRACT_NAMES:
        path = REPO_ROOT / "agents/codex" / f"{name}.md"
        assert path.is_file()
        assert len(path.read_text().strip()) > 0


def test_codex_contracts_share_a_consistent_frontmatter_shape():
    for name in CODEX_CONTRACT_NAMES:
        path = REPO_ROOT / "agents/codex" / f"{name}.md"
        fields = _frontmatter(path.read_text())
        assert fields.get("name") == name
        assert fields.get("routes", "").startswith("[") and fields["routes"].endswith(
            "]"
        )
        assert fields.get("responsibility")
        assert fields.get("domain")


def test_codex_contract_routes_are_real_model_routing_routes():
    payload = json.loads((REPO_ROOT / "interfaces/model-routing.json").read_text())
    known_routes = {route["name"] for route in payload["routes"]}
    for name in CODEX_CONTRACT_NAMES:
        path = REPO_ROOT / "agents/codex" / f"{name}.md"
        fields = _frontmatter(path.read_text())
        listed = [
            item.strip()
            for item in fields["routes"].strip("[]").split(",")
            if item.strip()
        ]
        assert listed, f"{name}: routes list must not be empty"
        assert set(listed) <= known_routes, f"{name}: unknown route in {listed}"


def test_codex_contracts_each_cite_specialist_handoff():
    for name in CODEX_CONTRACT_NAMES:
        path = REPO_ROOT / "agents/codex" / f"{name}.md"
        assert "rules/specialist-handoff.md" in path.read_text()
