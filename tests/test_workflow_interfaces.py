from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import unittest

from aitk.interfaces import (
    validate_provider_interfaces,
    validate_skill_interfaces,
    validate_support_interface,
)
from aitk.workflows import (
    command_adapters,
    extension_command_adapters,
    validate_extension_workflows,
    validate_workflows,
)
from aitk.conformance import validate_contracts, workflow_dependency_resources
from aitk.workflows import load_workflows


ROOT = Path(__file__).resolve().parents[1]


class WorkflowInterfaceTests(unittest.TestCase):
    def fixture(self, temporary: str) -> Path:
        root = Path(temporary) / "repo"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__"),
        )
        return root

    def test_manifest_is_complete_and_references_canonical_workflows(self) -> None:
        self.assertEqual([], validate_workflows(ROOT))

    def test_tracked_commands_are_exact_generated_adapters(self) -> None:
        adapters = command_adapters(ROOT)
        tracked = {
            path.name: path.read_text() for path in (ROOT / "commands").glob("*.md")
        }
        expected = {path.name: content for path, content in adapters.items()}
        self.assertEqual(expected, tracked)
        self.assertTrue(
            all(content.count("@{{TOOLKIT_DIR}}/") >= 1 for content in tracked.values())
        )
        self.assertTrue(
            all(len(content.splitlines()) <= 12 for content in tracked.values())
        )

    def test_optional_pgm_commands_are_exact_generated_adapters(self) -> None:
        self.assertEqual([], validate_extension_workflows(ROOT, "pgm"))
        adapters = extension_command_adapters(ROOT, "pgm")
        tracked = {
            path.name: path.read_text()
            for path in (ROOT / "extensions/pgm/commands").glob("*.md")
        }
        expected = {path.name: content for path, content in adapters.items()}
        self.assertEqual(expected, tracked)
        self.assertTrue(
            all(len(content.splitlines()) <= 12 for content in tracked.values())
        )

    def test_skill_provider_and_support_interfaces_are_total(self) -> None:
        self.assertEqual([], validate_skill_interfaces(ROOT))
        self.assertEqual([], validate_provider_interfaces(ROOT))
        self.assertEqual([], validate_support_interface(ROOT))

    def test_contract_version_one_is_rejected_with_migration_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            (root / "interfaces/contracts.json").write_text(
                json.dumps({"version": 1, "contracts": {}})
            )
            problems = validate_contracts(root)
            self.assertTrue(
                any("version 2" in problem for problem in problems), problems
            )

    def test_manifest_execution_class_cannot_hide_a_durable_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            path = root / "interfaces/workflows.json"
            payload = json.loads(path.read_text())
            workflow = next(
                item
                for item in payload["workflows"]
                if item["name"] == "create-feature"
            )
            workflow["execution_class"] = "single_run"
            path.write_text(json.dumps(payload))
            problems = validate_contracts(root)
            self.assertTrue(
                any("create-feature: single_run" in problem for problem in problems),
                problems,
            )

    def test_effect_and_authorization_markers_are_contract_bound(self) -> None:
        cases = {
            "effect-marker": (
                "skills/workflows/references/show-cost.md",
                "Effect: `read_only`.",
                "Effect: `local_mutation`.",
                "effect boundary marker",
            ),
            "authorization-marker": (
                "skills/workflows/references/address-feedback.md",
                "Authorization mode: `invocation`.",
                "Authorization mode: `explicit`.",
                "authorization marker",
            ),
        }
        for name, (relative, old, new, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                path = root / relative
                path.write_text(path.read_text().replace(old, new))

                problems = validate_contracts(root)

                self.assertTrue(any(expected in item for item in problems), problems)

    def test_read_only_linked_script_cannot_hide_an_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            script = root / "scripts/show-cost.py"
            script.write_text(script.read_text() + '\nPath("unsafe").write_text("x")\n')

            problems = validate_contracts(root)

            self.assertTrue(
                any(
                    "show-cost: read-only executable surface" in item
                    for item in problems
                ),
                problems,
            )

    def test_semantic_contract_failures_are_not_accepted_as_structural_success(
        self,
    ) -> None:
        def mutate_contract(root: Path, callback) -> None:
            path = root / "interfaces/contracts.json"
            payload = json.loads(path.read_text())
            callback(payload)
            path.write_text(json.dumps(payload))

        cases = {
            "missing-phases": (
                lambda root: mutate_contract(
                    root,
                    lambda payload: next(
                        item
                        for item in payload["contracts"]
                        if item["name"] == "create-feature"
                    ).update({"phases": []}),
                ),
                "phases must be unique",
            ),
            "missing-authorization": (
                lambda root: mutate_contract(
                    root,
                    lambda payload: next(
                        item
                        for item in payload["contracts"]
                        if item["name"] == "create-feature"
                    )["authorization"].update({"mode": "none"}),
                ),
                "requires authorization",
            ),
            "missing-idempotency": (
                lambda root: mutate_contract(
                    root,
                    lambda payload: next(
                        item
                        for item in payload["contracts"]
                        if item["name"] == "create-feature"
                    ).update({"idempotency_keys": []}),
                ),
                "requires an idempotency key",
            ),
            "read-only-executable-effect": (
                lambda root: (
                    root / "skills/workflows/references/show-cost.md"
                ).write_text(
                    (root / "skills/workflows/references/show-cost.md").read_text()
                    + "\n```sh\ngit commit -am unsafe\n```\n"
                ),
                "read-only executable surface is effectful",
            ),
            "negated-runtime-authorization": (
                lambda root: (root / "rules/durable-workflows.md").write_text(
                    (root / "rules/durable-workflows.md")
                    .read_text()
                    .replace(
                        "Complete the contract's authorization and preflight gates before any effect.",
                        "Skip authorization and preflight gates before effects.",
                    )
                ),
                "missing semantic clause",
            ),
            "missing-runtime-binding": (
                lambda root: (
                    lambda path, payload: (
                        next(
                            item
                            for item in payload["workflows"]
                            if item["name"] == "create-feature"
                        )["rules"].remove("rules/durable-workflows.md"),
                        path.write_text(json.dumps(payload)),
                    )
                )(
                    root / "interfaces/workflows.json",
                    json.loads((root / "interfaces/workflows.json").read_text()),
                ),
                "must load rules/durable-workflows.md",
            ),
        }
        for name, (mutate, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                mutate(root)
                problems = validate_contracts(root)
                self.assertTrue(
                    any(expected in problem for problem in problems),
                    problems,
                )

    def test_malformed_nested_contract_values_are_reported_without_crashing(
        self,
    ) -> None:
        mutations = {
            "phase-object": lambda contract, payload: contract.update({"phases": [{}]}),
            "authorization-gate-object": lambda contract, payload: contract[
                "authorization"
            ].update({"gates": [{}]}),
            "idempotency-strategy-object": lambda contract, payload: contract.update(
                {"idempotency_keys": [{"key": "commit", "strategy": {}}]}
            ),
            "evidence-object": lambda contract, payload: contract[
                "verification"
            ].update({"evidence": [{}]}),
            "vocabulary-object": lambda contract, payload: payload[
                "vocabularies"
            ].update({"gates": [{}]}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                path = root / "interfaces/contracts.json"
                payload = json.loads(path.read_text())
                contract = next(
                    item
                    for item in payload["contracts"]
                    if item["name"] == "create-feature"
                )
                mutate(contract, payload)
                path.write_text(json.dumps(payload))
                self.assertTrue(validate_contracts(root))

    def test_malformed_manifest_and_provider_values_are_reported_without_crashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            workflow_path = root / "interfaces/workflows.json"
            workflow_payload = json.loads(workflow_path.read_text())
            workflow_payload["workflows"][0]["rules"] = [{}]
            workflow_path.write_text(json.dumps(workflow_payload))
            self.assertTrue(validate_workflows(root))

        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            provider_path = root / "interfaces/providers.json"
            provider_payload = json.loads(provider_path.read_text())
            provider_payload["providers"]["codex"]["bindings"]["planning_boundary"][
                "mode"
            ] = {}
            provider_path.write_text(json.dumps(provider_payload))
            self.assertTrue(validate_provider_interfaces(root))

    def test_each_provider_guidance_must_load_every_shared_always_on_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            codex = root / "config/AGENTS.md"
            codex.write_text(
                codex.read_text().replace(
                    "{{TOOLKIT_DIR}}/rules/context-management.md",
                    "missing-context-rule",
                )
            )

            problems = validate_provider_interfaces(root)

            self.assertTrue(
                any(
                    "codex: installed guidance omits always-on rule" in item
                    for item in problems
                ),
                problems,
            )

    def test_dependency_links_fail_closed_on_missing_unclassified_and_escape(
        self,
    ) -> None:
        cases = {
            "missing": (
                "[missing](../../qa/references/not-present.md)",
                "missing or not a file",
            ),
            "unclassified": (
                "[unclassified](../../unclassified/resource.md)",
                "not classified",
            ),
            "escape": ("[escape](../../../../outside.md)", "escapes repository"),
        }
        for name, (link, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                reference = root / "skills/workflows/references/show-cost.md"
                if name == "unclassified":
                    target = root / "skills/unclassified/resource.md"
                    target.parent.mkdir()
                    target.write_text("# Resource\n")
                elif name == "escape":
                    (root.parent / "outside.md").write_text("# Outside\n")
                reference.write_text(reference.read_text() + f"\n{link}\n")

                problems = validate_contracts(root)

                self.assertTrue(any(expected in item for item in problems), problems)

    def test_every_named_inline_skill_resource_is_resolved_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            resource = root / "skills/plan-review/references/architecture.md"
            resource.unlink()

            problems = validate_contracts(root)

            self.assertTrue(
                any(
                    "review-plan: named skill resource is missing or unsafe: plan-review/references/architecture.md"
                    in item
                    for item in problems
                ),
                problems,
            )

    def test_removing_a_known_link_changes_the_exact_dependency_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            reference = root / "skills/workflows/references/complete-project.md"
            linked = (
                "[skills/reporting/templates/complete-project-metrics.md]"
                "(../../reporting/templates/complete-project-metrics.md)"
            )
            self.assertIn(linked, reference.read_text())
            reference.write_text(
                reference.read_text().replace(linked, "metrics template")
            )
            workflow = next(
                item for item in load_workflows(root) if item.name == "complete-project"
            )

            dependencies = {
                (item.name, item.resource.as_posix())
                for item in workflow_dependency_resources(root, workflow)
            }

            self.assertNotIn(
                (
                    "reporting",
                    "skills/reporting/templates/complete-project-metrics.md",
                ),
                dependencies,
            )


if __name__ == "__main__":
    unittest.main()
