from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from aitk.build import compare_build, expected_build, write_build


class BuildTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        (root / "config").mkdir()
        (root / "commands").mkdir()
        (root / "config/CLAUDE.md").write_text("@{{TOOLKIT_DIR}}/rules/universal.md\n")
        (root / "commands/hello.md").write_text("Read {{TOOLKIT_DIR}}/rules/test.md\n")

    def test_expected_build_resolves_portable_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            expected = expected_build(root)
            self.assertEqual(
                f"@{root}/rules/universal.md\n",
                expected[Path("build/config/CLAUDE.md")],
            )
            self.assertEqual(
                f"Read {root}/rules/test.md\n",
                expected[Path("build/commands/hello.md")],
            )

    def test_write_then_check_is_clean_and_stale_changes_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            result = write_build(root)
            self.assertEqual(2, result.written)
            self.assertEqual([], compare_build(root))

            (root / "commands/hello.md").write_text("changed\n")
            differences = compare_build(root)
            self.assertEqual(["different: build/commands/hello.md"], differences)

    def test_write_prunes_stale_generated_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            write_build(root)
            stale = root / "build/commands/stale.md"
            stale.write_text("old\n")

            result = write_build(root)
            self.assertEqual([Path("build/commands/stale.md")], result.removed)
            self.assertFalse(stale.exists())

    def test_manifest_generates_thin_source_and_built_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "interfaces").mkdir()
            (root / "rules").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "config/CLAUDE.md").write_text("Toolkit at {{TOOLKIT_DIR}}\n")
            (root / "rules/safety.md").write_text("# Safety\n")
            (root / "skills/workflows/references/hello.md").write_text(
                "Canonical workflow logic.\n"
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
                                "summary": "Say hello safely",
                                "arguments": "[name]",
                                "rules": ["rules/safety.md"],
                                "triggers": ["say hello"],
                                "execution_class": "single_run",
                            }
                        ],
                    }
                )
            )

            expected = expected_build(root)
            source = expected[Path("commands/hello.md")]
            built = expected[Path("build/commands/hello.md")]
            self.assertIn("@{{TOOLKIT_DIR}}/rules/safety.md", source)
            self.assertIn(
                "@{{TOOLKIT_DIR}}/skills/workflows/references/hello.md", source
            )
            self.assertNotIn("Canonical workflow logic", source)
            self.assertIn(f"@{root}/skills/workflows/references/hello.md", built)

            write_build(root)
            self.assertEqual(source, (root / "commands/hello.md").read_text())
            self.assertEqual([], compare_build(root))

    def test_semantically_invalid_manifest_refuses_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "interfaces").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "config/CLAUDE.md").write_text("# Config\n")
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
            self.assertFalse((root / "commands").exists())

    def test_optional_pgm_commands_are_generated_from_the_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "interfaces").mkdir()
            (root / "skills/workflows/references").mkdir(parents=True)
            (root / "extensions/pgm/interfaces").mkdir(parents=True)
            (root / "extensions/pgm/skills/pgm/references").mkdir(parents=True)
            (root / "config/CLAUDE.md").write_text("# Config\n")
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

            expected = expected_build(root, include_pgm=True)
            source = expected[Path("extensions/pgm/commands/report.md")]
            built = expected[Path("build/commands/report.md")]
            self.assertIn(
                "@{{TOOLKIT_DIR}}/extensions/pgm/skills/pgm/references/report.md",
                source,
            )
            self.assertIn(
                f"@{root}/extensions/pgm/skills/pgm/references/report.md", built
            )

            write_build(root, include_pgm=True)
            self.assertEqual(
                source, (root / "extensions/pgm/commands/report.md").read_text()
            )
            self.assertEqual([], compare_build(root, include_pgm=True))

    def test_manifest_destinations_cannot_escape_the_repository(self) -> None:
        for unsafe_name in ("../../outside", "/tmp/outside"):
            with self.subTest(
                name=unsafe_name
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "repo"
                (root / "config").mkdir(parents=True)
                (root / "interfaces").mkdir()
                (root / "skills/workflows/references").mkdir(parents=True)
                (root / "config/CLAUDE.md").write_text("# Config\n")
                (root / "skills/workflows/references/hello.md").write_text("# Hello\n")
                manifest = {
                    "version": 1,
                    "skill": "workflows",
                    "reference_root": "skills/workflows/references",
                    "workflows": [
                        {
                            "name": unsafe_name,
                            "summary": "Unsafe",
                            "arguments": "",
                            "rules": [],
                            "triggers": ["unsafe"],
                            "execution_class": "single_run",
                        }
                    ],
                }
                (root / "interfaces/workflows.json").write_text(json.dumps(manifest))
                outside = Path(temporary) / "outside"
                outside.write_text("sentinel\n")

                with self.assertRaisesRegex(ValueError, "unsafe workflow name"):
                    write_build(root)

                self.assertEqual("sentinel\n", outside.read_text())
                self.assertFalse((root / "build").exists())

    def test_generated_output_rejects_symlink_ancestors(self) -> None:
        for relative in (Path("commands"), Path("build/commands")):
            with self.subTest(
                relative=relative
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "repo"
                outside = Path(temporary) / "outside"
                root.mkdir()
                outside.mkdir()
                self.make_repo(root)
                if relative == Path("commands"):
                    shutil.rmtree(root / relative)
                    (root / "interfaces").mkdir()
                    (root / "skills/workflows/references").mkdir(parents=True)
                    (root / "skills/workflows/references/hello.md").write_text(
                        "# Hello\n"
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
                else:
                    (root / "build").mkdir()
                (root / relative).symlink_to(outside, target_is_directory=True)
                sentinel = outside / "sentinel"
                sentinel.write_text("safe\n")

                with self.assertRaisesRegex(ValueError, "symlink ancestor"):
                    write_build(root)

                self.assertEqual("safe\n", sentinel.read_text())
                self.assertFalse((outside / "hello.md").exists())

    def test_manifest_addition_creates_untracked_adapter_detected_by_ci_guard(
        self,
    ) -> None:
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            for relative in (
                "interfaces",
                "commands",
                "rules",
                "skills/workflows/references",
                "extensions/pgm/interfaces",
                "extensions/pgm/commands",
                "extensions/pgm/rules",
                "extensions/pgm/skills/pgm/references",
            ):
                source = source_root / relative
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(
                ["git", "add", "commands", "extensions/pgm/commands"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)

            manifest = root / "interfaces/workflows.json"
            payload = json.loads(manifest.read_text())
            payload["workflows"].append(
                {
                    "name": "new-workflow",
                    "summary": "New generated workflow",
                    "arguments": "",
                    "rules": [],
                    "triggers": ["new workflow"],
                    "execution_class": "single_run",
                }
            )
            manifest.write_text(json.dumps(payload))
            (root / "skills/workflows/references/new-workflow.md").write_text(
                "# New Workflow\n"
            )
            write_build(root, include_pgm=True)
            status = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                    "--",
                    "commands",
                    "extensions/pgm/commands",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertIn("?? commands/new-workflow.md", status)


if __name__ == "__main__":
    unittest.main()
