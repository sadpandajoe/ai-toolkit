from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import tempfile
import unittest

from aitk.workflows import load_workflows, workflow_dependency_resources


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

    def test_every_workflow_reference_resolves(self) -> None:
        workflows = load_workflows(ROOT, include_pgm=True)
        self.assertEqual(len({item.name for item in workflows}), len(workflows))
        for workflow in workflows:
            with self.subTest(workflow=workflow.name):
                if not workflow.command:
                    self.assertTrue((ROOT / workflow.reference).is_file())
                for rule in workflow.rules:
                    self.assertTrue((ROOT / rule).is_file(), rule)
                workflow_dependency_resources(ROOT, workflow)

    def test_command_only_entries_run_one_command_and_keep_no_reference(self) -> None:
        commands = {
            workflow.name: workflow.command
            for workflow in load_workflows(ROOT)
            if workflow.command
        }
        self.assertEqual(
            {
                "custom-skills-info": "bin/aitk list",
                "metrics": "bin/aitk metrics",
                "show-cost": "bin/aitk cost",
                "toolkit-doctor": "bin/aitk doctor --strict",
            },
            commands,
        )
        for name in commands:
            with self.subTest(workflow=name):
                self.assertFalse(
                    (ROOT / f"skills/workflows/references/{name}.md").exists()
                )
                self.assertEqual(
                    (), workflow_dependency_resources(ROOT, next(
                        item for item in load_workflows(ROOT) if item.name == name
                    ))
                )
        for command in ("aitk cost", "bin/aitk", "bin/aitk cost\nrm -rf /", ""):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                manifest = root / "interfaces/workflows.json"
                payload = json.loads(manifest.read_text())
                next(
                    item for item in payload["workflows"] if item["name"] == "show-cost"
                )["command"] = command
                manifest.write_text(json.dumps(payload))
                with self.assertRaisesRegex(
                    ValueError, "command must be one `bin/aitk <subcommand>` line"
                ):
                    load_workflows(root)

    def test_malformed_manifest_values_fail_the_load(self) -> None:
        mutations = {
            "rule-object": lambda payload: payload["workflows"][0].update(rules=[{}]),
            "duplicate": lambda payload: payload["workflows"].append(
                dict(payload["workflows"][0])
            ),
            "unsafe-rule": lambda payload: payload["workflows"][0].update(
                rules=["../outside.md"]
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                manifest = root / "interfaces/workflows.json"
                payload = json.loads(manifest.read_text())
                mutate(payload)
                manifest.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    load_workflows(root)

    def test_memory_store_is_bound_on_both_providers(self) -> None:
        payload = json.loads((ROOT / "interfaces/providers.json").read_text())
        self.assertIn({"name": "memory_store", "required": True}, payload["capabilities"])
        claude = payload["providers"]["claude"]["bindings"]["memory_store"]
        codex = payload["providers"]["codex"]["bindings"]["memory_store"]
        self.assertEqual("native", claude["mode"])
        self.assertEqual(
            ("fallback", "repository_memory_directory"), (codex["mode"], codex["fallback"])
        )
        self.assertIn(
            ".ai-toolkit/memory/", (ROOT / "config/providers/codex.md").read_text()
        )

    def test_dependency_resolution_fails_closed_in_the_router_loader(self) -> None:
        # `list --details` resolves dependencies through aitk.workflows, so the
        # loader itself refuses a missing, unclassified or escaping link.
        cases = {
            "missing": ("[missing](../../qa/references/not-present.md)", "missing or not a file"),
            "unclassified": ("[unclassified](../../unclassified/resource.md)", "not classified"),
            "escape": ("[escape](../../../../outside.md)", "escapes repository"),
        }
        for name, (link, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                reference = root / "skills/workflows/references/verify.md"
                if name == "unclassified":
                    target = root / "skills/unclassified/resource.md"
                    target.parent.mkdir()
                    target.write_text("# Resource\n")
                elif name == "escape":
                    (root.parent / "outside.md").write_text("# Outside\n")
                reference.write_text(reference.read_text() + f"\n{link}\n")
                workflow = next(item for item in load_workflows(root) if item.name == "verify")

                with self.assertRaisesRegex(ValueError, expected):
                    workflow_dependency_resources(root, workflow)

    def test_every_named_inline_skill_resource_is_resolved_exactly(self) -> None:
        # Two channels name skill resources: a bare skill-relative path in
        # backticks (`fix-bug` names the existing-fix check) and a Markdown link
        # (`review-code` links the classifier). Both fail closed when the target
        # vanishes.
        cases = (
            (
                "skills/debug/references/check-existing-fix.md",
                "fix-bug",
                "named skill resource is missing or unsafe: "
                "debug/references/check-existing-fix.md",
            ),
            (
                "skills/review/references/classify-diff.md",
                "review-code",
                "dependency link target is missing or not a file: "
                "../../review/references/classify-diff.md",
            ),
        )
        for removed, name, expected in cases:
            with self.subTest(workflow=name), tempfile.TemporaryDirectory() as temporary:
                root = self.fixture(temporary)
                (root / removed).unlink()
                workflow = next(item for item in load_workflows(root) if item.name == name)
                with self.assertRaisesRegex(ValueError, re.escape(expected)):
                    workflow_dependency_resources(root, workflow)

    def test_removing_a_known_link_changes_the_exact_dependency_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            reference = root / "skills/workflows/references/complete-project.md"
            linked = (
                "[skills/reflection/references/observations.md]"
                "(../../reflection/references/observations.md)"
            )
            self.assertIn(linked, reference.read_text())
            reference.write_text(
                reference.read_text().replace(linked, "summary template")
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
                    "reflection",
                    "skills/reflection/references/observations.md",
                ),
                dependencies,
            )



if __name__ == "__main__":
    unittest.main()
