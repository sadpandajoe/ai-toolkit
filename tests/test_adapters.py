"""Coverage for the Claude routed_subagent capability's native-dispatch flip.

interfaces/providers.json declares, per provider, how each shared capability
maps to provider syntax. This proves the claude/routed_subagent binding now
reads "native" (Task-tool dispatch by name to agents/claude/*.md workers)
while codex/routed_subagent is untouched (still the source_linked_model_run
fallback, since no native Codex worker roster exists), and that the schema
validator in aitk.interfaces still accepts the whole file.
"""

import json
from pathlib import Path

from aitk.interfaces import validate_provider_interfaces
from aitk.routing_manifest import validate_model_routing

REPO_ROOT = Path(__file__).resolve().parent.parent


def _providers():
    return json.loads((REPO_ROOT / "interfaces/providers.json").read_text())


def test_real_providers_file_is_valid():
    assert validate_provider_interfaces(REPO_ROOT) == []


def test_claude_routed_subagent_is_native_with_no_fallback():
    binding = _providers()["providers"]["claude"]["bindings"]["routed_subagent"]
    assert binding == {
        "mode": "native",
        "document": "config/providers/claude.md",
        "fallback": None,
    }


def test_codex_routed_subagent_is_unchanged():
    binding = _providers()["providers"]["codex"]["bindings"]["routed_subagent"]
    assert binding == {
        "mode": "fallback",
        "document": "config/providers/codex.md",
        "fallback": "source_linked_model_run",
    }


def test_claude_fresh_subagent_and_independent_review_stay_on_fallback():
    bindings = _providers()["providers"]["claude"]["bindings"]
    for capability in ("fresh_subagent", "independent_review"):
        assert bindings[capability]["mode"] == "fallback"
        assert bindings[capability]["fallback"] == "source_linked_model_run"


def test_claude_provider_doc_describes_native_dispatch_by_name():
    text = (REPO_ROOT / "config/providers/claude.md").read_text()
    assert "Task-tool" in text
    for worker in (
        "implementation-worker",
        "debug-worker",
        "test-worker",
        "planner",
        "review-worker",
        "deep-review-worker",
        "deep-rca-worker",
        "operations-worker",
    ):
        assert worker in text
    assert "model-run --provider claude" in text


def test_regressing_claude_routed_subagent_back_to_fallback_still_schema_valid():
    # The interfaces/providers.json binding-shape schema doesn't know about
    # this specific invariant — it's satisfied by either mode. The mechanical
    # enforcement lives in aitk.routing_manifest.validate_route_bindings
    # instead (see the next test), the same pattern C16 used for the
    # implementation/rca Sonnet-routing invariant.
    payload = _providers()
    payload["providers"]["claude"]["bindings"]["routed_subagent"] = {
        "mode": "fallback",
        "document": "config/providers/claude.md",
        "fallback": "source_linked_model_run",
    }
    path = REPO_ROOT / "interfaces/providers.json"
    original = path.read_text()
    try:
        path.write_text(json.dumps(payload))
        assert validate_provider_interfaces(REPO_ROOT) == []
    finally:
        path.write_text(original)


def test_regressing_claude_routed_subagent_back_to_fallback_fails_the_real_gate():
    payload = _providers()
    payload["providers"]["claude"]["bindings"]["routed_subagent"] = {
        "mode": "fallback",
        "document": "config/providers/claude.md",
        "fallback": "source_linked_model_run",
    }
    path = REPO_ROOT / "interfaces/providers.json"
    original = path.read_text()
    try:
        path.write_text(json.dumps(payload))
        problems = validate_model_routing(REPO_ROOT)
        assert any("claude/routed_subagent: must be native" in p for p in problems)
    finally:
        path.write_text(original)


def test_flipping_codex_routed_subagent_to_native_fails_the_real_gate():
    # Codex has no native worker roster yet — only claude/routed_subagent may
    # flip to native today.
    payload = _providers()
    payload["providers"]["codex"]["bindings"]["routed_subagent"] = {
        "mode": "native",
        "document": "config/providers/codex.md",
        "fallback": None,
    }
    path = REPO_ROOT / "interfaces/providers.json"
    original = path.read_text()
    try:
        path.write_text(json.dumps(payload))
        problems = validate_model_routing(REPO_ROOT)
        assert any(
            "codex/routed_subagent: must use source_linked_model_run" in p
            for p in problems
        )
    finally:
        path.write_text(original)
