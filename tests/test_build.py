from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from aitk.build import compare_build, expected_build, write_build


class BuildTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        (root / "config").mkdir()
        (root / "config/CLAUDE.md").write_text(
            "@{{TOOLKIT_DIR}}/rules/universal.md\n"
        )

    def test_expected_build_resolves_portable_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)

            expected = expected_build(root)

            self.assertEqual(
                f"@{root}/rules/universal.md\n",
                expected[Path("build/config/CLAUDE.md")],
            )
            self.assertEqual({Path("build/config/CLAUDE.md")}, set(expected))

    def test_write_then_check_is_clean_and_source_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)

            result = write_build(root)

            self.assertEqual(1, result.written)
            self.assertEqual([], compare_build(root))
            (root / "config/CLAUDE.md").write_text("changed\n")
            self.assertEqual(
                ["different: build/config/CLAUDE.md"], compare_build(root)
            )

    def test_build_preserves_legacy_command_output_as_rollback_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)
            stale = root / "build/commands/stale.md"
            stale.parent.mkdir(parents=True)
            stale.write_text("old\n")

            result = write_build(root)

            self.assertEqual([], result.removed)
            self.assertEqual("old\n", stale.read_text())
            self.assertEqual([], compare_build(root))

    def test_manifest_validation_precedes_config_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)
            (root / "interfaces").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "skills/workflows/references/hello.md").write_text("# Hello\n")
            workflow = {
                "name": "hello",
                "summary": "Hello",
                "arguments": "",
                "rules": [],
                "triggers": ["hello"],
                "execution_class": "single_run",
            }
            (root / "interfaces/workflows.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skill": "workflows",
                        "reference_root": "skills/workflows/references",
                        "workflows": [workflow, dict(workflow)],
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "duplicate workflow name"):
                write_build(root)

            self.assertFalse((root / "build").exists())

    def test_optional_extension_is_validated_without_generating_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.make_repo(root)
            (root / "interfaces").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "extensions/pgm/interfaces").mkdir(parents=True)
            (root / "extensions/pgm/skills/pgm/references").mkdir(parents=True)
            (root / "skills/workflows/references/hello.md").write_text("# Hello\n")
            (root / "extensions/pgm/skills/pgm/references/report.md").write_text(
                "# Report\n"
            )
            (root / "interfaces/workflows.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skill": "workflows",
                        "reference_root": "skills/workflows/references",
                        "workflows": [
                            {
                                "name": "hello",
                                "summary": "Hello",
                                "arguments": "",
                                "rules": [],
                                "triggers": ["hello"],
                                "execution_class": "single_run",
                            }
                        ],
                    }
                )
            )
            (root / "extensions/pgm/interfaces/workflows.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skill": "pgm",
                        "reference_root": "extensions/pgm/skills/pgm/references",
                        "workflows": [
                            {
                                "name": "report",
                                "summary": "Create report",
                                "arguments": "[team]",
                                "rules": [],
                                "triggers": ["create report"],
                                "execution_class": "single_run",
                            }
                        ],
                    }
                )
            )

            result = write_build(root, include_pgm=True)

            self.assertEqual(1, result.written)
            self.assertFalse((root / "commands").exists())
            self.assertFalse((root / "extensions/pgm/commands").exists())
            self.assertFalse((root / "build/commands").exists())
            self.assertEqual([], compare_build(root, include_pgm=True))

    def test_generated_output_rejects_symlink_ancestors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            self.make_repo(root)
            (root / "build").mkdir()
            (root / "build/config").symlink_to(outside, target_is_directory=True)
            sentinel = outside / "sentinel"
            sentinel.write_text("safe\n")

            with self.assertRaisesRegex(ValueError, "symlink ancestor"):
                write_build(root)

            self.assertEqual("safe\n", sentinel.read_text())
            self.assertFalse((outside / "CLAUDE.md").exists())


if __name__ == "__main__":
    unittest.main()
