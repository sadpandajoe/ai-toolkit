from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from aitk.doctor import run_doctor
from aitk.installer import (
    FAILPOINT_ENV,
    _legacy_command_targets,
    inspect_install,
    install,
    resolve_paths,
    rollback,
    uninstall,
)


ROOT = Path(__file__).resolve().parents[1]


def tree_state(root: Path) -> tuple[tuple[object, ...], ...]:
    if not root.exists():
        return ()
    result: list[tuple[object, ...]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result.append(("link", relative, os.readlink(path)))
        elif path.is_file():
            result.append(
                ("file", relative, path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            )
        elif path.is_dir():
            result.append(("dir", relative, stat.S_IMODE(path.stat().st_mode)))
    return tuple(result)


class InstallerLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.paths = resolve_paths(
            ROOT,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy_checkout(self, name: str) -> Path:
        checkout = self.base / name
        for directory in (
            "config",
            "docs",
            "interfaces",
            "rules",
            "skills",
            "extensions",
        ):
            shutil.copytree(ROOT / directory, checkout / directory, symlinks=True)
        for filename in ("pyproject.toml", "PROJECT_TEMPLATE.md"):
            shutil.copy2(ROOT / filename, checkout / filename)
        return checkout

    def test_guidance_round_trip_preserves_exact_bytes_and_modes(self) -> None:
        cases = (
            (b"", 0o600),
            (b"personal-no-newline", 0o700),
            (b"personal\n", 0o644),
            (b"personal\n\n\n", 0o755),
            (b"personal\r\n", 0o600),
            (b"personal\r\n\r\n", 0o640),
        )
        for content, mode in cases:
            with self.subTest(
                content=content, mode=oct(mode)
            ), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary).resolve() / "home"
                claude = home / ".claude/CLAUDE.md"
                codex = home / ".codex/AGENTS.md"
                claude.parent.mkdir(parents=True)
                codex.parent.mkdir(parents=True)
                for guidance in (claude, codex):
                    guidance.write_bytes(content)
                    guidance.chmod(mode)
                paths = resolve_paths(ROOT, home, home / ".codex", home / ".agents")

                self.assertEqual("ok", install(paths).status)
                removed = uninstall(paths)

                self.assertEqual("ok", removed.status, removed.conflicts)
                for guidance in (claude, codex):
                    self.assertEqual(content, guidance.read_bytes())
                    self.assertEqual(mode, stat.S_IMODE(guidance.stat().st_mode))

    def test_uninstall_rollback_and_repeat_refusal_preserve_user_content(self) -> None:
        claude = self.home / ".claude/CLAUDE.md"
        codex = self.home / ".codex/AGENTS.md"
        claude.parent.mkdir(parents=True)
        codex.parent.mkdir(parents=True)
        claude.write_text("# Claude user preface\n")
        codex.write_text("# Codex user preface\n")
        self.assertEqual("ok", install(self.paths).status)
        claude.write_text(claude.read_text() + "# Claude post-install edit\n")
        codex.write_text(codex.read_text() + "# Codex post-install edit\n")

        removed = uninstall(self.paths)
        self.assertEqual("ok", removed.status, removed.conflicts)
        self.assertNotIn("ai-toolkit managed guidance", claude.read_text())
        self.assertIn("Claude user preface", claude.read_text())
        self.assertIn("Claude post-install edit", claude.read_text())
        self.assertFalse((self.home / ".claude/skills/workflows").exists())

        restored = rollback(self.paths)
        self.assertEqual("ok", restored.status, restored.conflicts)
        self.assertIn("ai-toolkit managed guidance", claude.read_text())
        self.assertIn("Claude post-install edit", claude.read_text())
        self.assertIn("Codex post-install edit", codex.read_text())
        self.assertTrue((self.home / ".claude/skills/workflows").is_symlink())
        self.assertEqual("refused", rollback(self.paths).status)
        self.assertEqual("ok", uninstall(self.paths).status)

    def test_installed_guidance_loads_current_provider_bindings(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        claude = (self.home / ".claude/CLAUDE.md").read_text()
        codex = (self.home / ".codex/AGENTS.md").read_text()

        self.assertIn(str(ROOT / "config/providers/claude.md"), claude)
        self.assertIn(str(ROOT / "config/providers/codex.md"), codex)

    def test_rollback_of_initial_install_restores_exact_prior_state(self) -> None:
        claude = self.home / ".claude/CLAUDE.md"
        claude.parent.mkdir(parents=True)
        claude.write_text("personal\n")
        before = tree_state(self.home)

        self.assertEqual("ok", install(self.paths).status)
        result = rollback(self.paths)

        self.assertEqual("ok", result.status, result.conflicts)
        ledger = json.loads(self.paths.ledger.read_text())
        self.assertEqual("rolled_back", ledger["status"])
        self.assertEqual([], ledger["active"])
        state_without_ledger = tuple(
            item
            for item in tree_state(self.home)
            if not str(item[1]).startswith(".ai-toolkit")
        )
        self.assertEqual(before, state_without_ledger)

    def test_corrupt_backup_refuses_before_mutation(self) -> None:
        guidance = self.home / ".claude/CLAUDE.md"
        guidance.parent.mkdir(parents=True)
        guidance.write_text("personal\n")
        self.assertEqual("ok", install(self.paths).status)
        ledger = json.loads(self.paths.ledger.read_text())
        snapshot = next(
            item
            for item in ledger["last_transaction"]["before"]
            if item["target"] == str(guidance)
        )
        material = (
            self.paths.state_dir
            / ledger["last_transaction"]["backup_path"]
            / snapshot["backup"]
        )
        material.write_text("corrupt\n")
        before = tree_state(self.home)

        result = rollback(self.paths)

        self.assertEqual("refused", result.status)
        self.assertIn("corrupt backup", " ".join(result.conflicts))
        self.assertEqual(before, tree_state(self.home))

    def test_tampered_ledgers_fail_closed_for_every_reader_and_writer(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        payload = json.loads(self.paths.ledger.read_text())
        payload["active"][0]["source"] = "/tmp/escape"
        self.paths.ledger.write_text(json.dumps(payload))
        os.chmod(self.paths.ledger, 0o600)
        before = tree_state(self.home)

        self.assertEqual("refused", install(self.paths).status)
        self.assertEqual("refused", uninstall(self.paths).status)
        self.assertEqual("refused", rollback(self.paths).status)
        self.assertTrue(inspect_install(self.paths)[0].startswith("FAIL:"))
        self.assertEqual(before, tree_state(self.home))

    def test_ledger_mode_is_a_fail_closed_lifecycle_boundary(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        self.paths.ledger.chmod(0o644)
        before = tree_state(self.home)

        self.assertEqual("refused", install(self.paths).status)
        self.assertEqual("refused", uninstall(self.paths).status)
        self.assertEqual("refused", rollback(self.paths).status)
        self.assertEqual(
            ("FAIL: install ledger mode must be 0600",), inspect_install(self.paths)
        )
        self.assertEqual(before, tree_state(self.home))

    def test_hostile_ledger_refuses_before_regenerating_the_checkout(self) -> None:
        checkout = self.copy_checkout("hostile-ledger-checkout")
        paths = resolve_paths(
            checkout,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )
        self.assertEqual("ok", install(paths).status)
        built = checkout / "build/config/CLAUDE.md"
        before_build = built.read_bytes()
        (checkout / "config/CLAUDE.md").write_text("changed source\n")
        payload = json.loads(paths.ledger.read_text())
        payload["active"][0]["target"] = "/tmp/outside"
        paths.ledger.write_text(json.dumps(payload))
        paths.ledger.chmod(0o600)
        before_home = tree_state(self.home)

        result = install(paths)

        self.assertEqual("refused", result.status)
        self.assertEqual(before_build, built.read_bytes())
        self.assertEqual(before_home, tree_state(self.home))

    def test_hostile_skill_manifest_refuses_before_any_install_mutation(self) -> None:
        checkout = self.copy_checkout("hostile-skill-checkout")
        manifest = checkout / "interfaces/skills.json"
        payload = json.loads(manifest.read_text())
        payload["skills"][0]["path"] = "../../outside"
        manifest.write_text(json.dumps(payload))
        paths = resolve_paths(
            checkout,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )
        before = tree_state(self.home)

        result = install(paths)

        self.assertEqual("refused", result.status)
        self.assertIn("unsafe skill path", " ".join(result.conflicts))
        self.assertEqual(before, tree_state(self.home))
        self.assertFalse((checkout / "build").exists())

    def test_semantically_invalid_source_refuses_before_any_mutation(self) -> None:
        mutations = {
            "duplicate-workflow": lambda checkout: self._duplicate_workflow(checkout),
            "missing-public-skill": lambda checkout: self._missing_public_skill(
                checkout
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                checkout = self.copy_checkout(f"semantic-{name}")
                mutate(checkout)
                paths = resolve_paths(
                    checkout,
                    self.home,
                    self.home / ".codex",
                    self.home / ".agents",
                )
                before = tree_state(self.home)

                result = install(paths)

                self.assertEqual("refused", result.status, result.conflicts)
                self.assertIn("source interface validation failed", result.conflicts[0])
                self.assertEqual(before, tree_state(self.home))
                self.assertFalse((checkout / "build").exists())

    @staticmethod
    def _duplicate_workflow(checkout: Path) -> None:
        manifest = checkout / "interfaces/workflows.json"
        payload = json.loads(manifest.read_text())
        payload["workflows"].append(dict(payload["workflows"][0]))
        manifest.write_text(json.dumps(payload))

    @staticmethod
    def _missing_public_skill(checkout: Path) -> None:
        manifest = checkout / "interfaces/skills.json"
        payload = json.loads(manifest.read_text())
        public = next(
            item
            for item in payload["skills"]
            if item["classification"] in {"public_router", "public_direct"}
            and str(item["path"]).startswith("skills/")
        )
        public["path"] = "skills/missing"
        manifest.write_text(json.dumps(payload))

    def test_ledger_rejects_cross_inventory_records_and_privileged_modes(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        original = json.loads(self.paths.ledger.read_text())

        def wrong_source(payload: dict[str, object]) -> None:
            records = payload["active"]
            first, second = records[0], records[1]
            first["source"] = second["source"]
            first["link_target"] = second["source"]

        def wrong_name(payload: dict[str, object]) -> None:
            payload["active"][0]["name"] = "another-record"

        def privileged_mode(payload: dict[str, object]) -> None:
            guidance = next(
                item for item in payload["active"] if item["kind"] == "guidance"
            )
            guidance["mode"] = 0o4755

        for name, mutate in (
            ("cross-source", wrong_source),
            ("wrong-name", wrong_name),
            ("privileged-mode", privileged_mode),
        ):
            with self.subTest(name=name):
                payload = json.loads(json.dumps(original))
                mutate(payload)
                self.paths.ledger.write_text(json.dumps(payload))
                os.chmod(self.paths.ledger, 0o600)
                before = tree_state(self.home)
                self.assertEqual("refused", uninstall(self.paths).status)
                self.assertEqual(before, tree_state(self.home))

    def test_ledger_rejects_unhashable_values_without_crashing(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        original = json.loads(self.paths.ledger.read_text())

        def active_target(payload: dict[str, object]) -> None:
            payload["active"][0]["target"] = []

        def snapshot_state(payload: dict[str, object]) -> None:
            payload["last_transaction"]["before"][0]["state"] = {}

        def owned_directory(payload: dict[str, object]) -> None:
            payload["last_transaction"]["after_owned_dirs"] = [{}]

        for name, mutate in (
            ("active-target", active_target),
            ("snapshot-state", snapshot_state),
            ("owned-directory", owned_directory),
        ):
            with self.subTest(name=name):
                payload = json.loads(json.dumps(original))
                mutate(payload)
                self.paths.ledger.write_text(json.dumps(payload))
                os.chmod(self.paths.ledger, 0o600)
                before = tree_state(self.home)
                self.assertEqual("refused", uninstall(self.paths).status)
                self.assertEqual(before, tree_state(self.home))

    def test_backup_traversal_and_symlink_ancestor_ledgers_fail_closed(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        original = json.loads(self.paths.ledger.read_text())
        cases = ("/tmp/escape", "backups/../escape")
        for value in cases:
            with self.subTest(value=value):
                payload = json.loads(json.dumps(original))
                payload["last_transaction"]["backup_path"] = value
                self.paths.ledger.write_text(json.dumps(payload))
                os.chmod(self.paths.ledger, 0o600)
                before = tree_state(self.home)
                self.assertEqual("refused", uninstall(self.paths).status)
                self.assertEqual(before, tree_state(self.home))

        self.paths.ledger.write_text(json.dumps(original))
        os.chmod(self.paths.ledger, 0o600)
        skills = self.home / ".claude/skills"
        shutil.rmtree(skills)
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "sentinel").write_text("safe\n")
        skills.symlink_to(outside)
        before = tree_state(self.home)
        self.assertEqual("refused", uninstall(self.paths).status)
        self.assertEqual(before, tree_state(self.home))
        self.assertEqual("safe\n", (outside / "sentinel").read_text())

    def test_precommit_failpoints_restore_exact_state_and_leave_no_backup(self) -> None:
        for point in (
            "backup-created",
            "guidance-mutated",
            "link-mutated",
            "ledger-temp-written",
        ):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary).resolve() / "home"
                home.mkdir()
                personal = home / ".claude/CLAUDE.md"
                personal.parent.mkdir(parents=True)
                personal.write_text("personal\n")
                paths = resolve_paths(ROOT, home, home / ".codex", home / ".agents")
                before = tree_state(home)
                with mock.patch.dict(os.environ, {FAILPOINT_ENV: point}):
                    result = install(paths)
                self.assertEqual("refused", result.status, result.conflicts)
                self.assertEqual(before, tree_state(home))
                self.assertFalse(paths.ledger.exists())
                self.assertFalse(paths.backups.exists())

    def test_rollback_failpoint_restores_after_state_and_ledger_identity(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        before = tree_state(self.home)
        ledger_bytes = self.paths.ledger.read_bytes()
        ledger_mtime = self.paths.ledger.stat().st_mtime_ns
        with mock.patch.dict(os.environ, {FAILPOINT_ENV: "rollback-restored"}):
            result = rollback(self.paths)
        self.assertEqual("refused", result.status)
        self.assertEqual(before, tree_state(self.home))
        self.assertEqual(ledger_bytes, self.paths.ledger.read_bytes())
        self.assertEqual(ledger_mtime, self.paths.ledger.stat().st_mtime_ns)

    def test_postcommit_failpoints_leave_authoritative_state_and_are_recoverable(
        self,
    ) -> None:
        with mock.patch.dict(os.environ, {FAILPOINT_ENV: "ledger-replaced"}):
            committed = install(self.paths)
        self.assertEqual("drift", committed.status)
        self.assertTrue(self.paths.ledger.is_file())
        self.assertIn(
            "PASS: installed artifacts match the ownership ledger",
            inspect_install(self.paths),
        )

        with mock.patch.dict(os.environ, {FAILPOINT_ENV: "backup-prune"}):
            upgraded = install(self.paths, with_pgm=True)
        self.assertEqual("drift", upgraded.status)
        self.assertTrue(
            any("orphan backup" in item for item in inspect_install(self.paths, True))
        )
        cleaned = install(self.paths, with_pgm=True)
        self.assertEqual("noop", cleaned.status)
        self.assertIn(
            "PASS: installed artifacts match the ownership ledger",
            inspect_install(self.paths, True),
        )

    def test_orphan_backup_symlink_refuses_deterministically(self) -> None:
        self.assertEqual("ok", install(self.paths).status)
        outside = Path(self.temporary.name) / "outside-backup"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("safe\n")
        orphan = self.paths.backups / "orphan-link"
        orphan.symlink_to(outside, target_is_directory=True)
        before = tree_state(self.home)

        result = install(self.paths)

        self.assertEqual("refused", result.status)
        self.assertIn("orphan backup cannot be a symlink", " ".join(result.conflicts))
        self.assertTrue(inspect_install(self.paths)[0].startswith("FAIL:"))
        self.assertEqual("safe\n", sentinel.read_text())
        self.assertEqual(before, tree_state(self.home))

    def test_version_only_upgrade_is_visible_reversible_and_not_a_noop(self) -> None:
        checkout = self.copy_checkout("version-checkout")
        paths = resolve_paths(
            checkout,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )
        self.assertEqual("ok", install(paths).status)
        initial = json.loads(paths.ledger.read_text())
        pyproject = checkout / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace('version = "0.2.0"', 'version = "0.2.1"')
        )

        self.assertTrue(
            any(
                "installed toolkit version differs" in item
                for item in inspect_install(paths)
            )
        )
        upgraded = install(paths)
        self.assertEqual("upgrade", upgraded.operation)
        self.assertEqual("ok", upgraded.status, upgraded.conflicts)
        self.assertEqual(
            "0.2.1", json.loads(paths.ledger.read_text())["toolkit_version"]
        )
        restored = rollback(paths)
        self.assertEqual("ok", restored.status, restored.conflicts)
        self.assertEqual(
            initial["toolkit_version"],
            json.loads(paths.ledger.read_text())["toolkit_version"],
        )

    def test_0_1_command_ownership_migrates_without_touching_personal_commands(
        self,
    ) -> None:
        checkout = self.copy_checkout("legacy-command-checkout")
        paths = resolve_paths(
            checkout,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )
        self.assertEqual("ok", install(paths).status)
        command_dir = self.home / ".claude/commands"
        command_dir.mkdir(parents=True)
        target = command_dir / "fix-bug.md"
        source = checkout / "build/commands/fix-bug.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Legacy fix-bug adapter\n")
        target.symlink_to(source)
        personal = command_dir / "personal.md"
        personal.write_text("# Personal\n")
        ledger = json.loads(paths.ledger.read_text())
        ledger["toolkit_version"] = "0.1.0"
        ledger["active"].append(
            {
                "name": "command:fix-bug",
                "kind": "symlink",
                "target": str(target),
                "source": str(source),
                "link_target": str(source),
                "created": True,
            }
        )
        ledger["owned_dirs"].append(str(command_dir))
        ledger["last_transaction"] = None
        paths.ledger.write_text(json.dumps(ledger))
        os.chmod(paths.ledger, 0o600)
        before_ledger = paths.ledger.read_bytes()

        with mock.patch.dict(os.environ, {FAILPOINT_ENV: "backup-created"}):
            refused = install(paths)

        self.assertEqual("refused", refused.status)
        self.assertTrue(target.exists())
        self.assertEqual("# Legacy fix-bug adapter\n", target.read_text())
        self.assertEqual("# Personal\n", personal.read_text())
        self.assertEqual(before_ledger, paths.ledger.read_bytes())

        result = install(paths)

        self.assertEqual("ok", result.status, result.conflicts)
        self.assertEqual("upgrade", result.operation)
        self.assertFalse(target.exists())
        self.assertEqual("# Personal\n", personal.read_text())
        upgraded = json.loads(paths.ledger.read_text())
        self.assertNotIn(str(command_dir), upgraded["owned_dirs"])
        self.assertFalse(
            any(item["name"].startswith("command:") for item in upgraded["active"])
        )

        restored = rollback(paths)

        self.assertEqual("ok", restored.status, restored.conflicts)
        self.assertTrue(target.is_symlink())
        self.assertTrue(target.exists())
        self.assertEqual(str(source), os.readlink(target))
        self.assertEqual("# Legacy fix-bug adapter\n", target.read_text())
        self.assertEqual("# Personal\n", personal.read_text())
        rolled_back = json.loads(paths.ledger.read_text())
        self.assertTrue(
            any(item["name"] == "command:fix-bug" for item in rolled_back["active"])
        )

    def test_0_1_whole_command_link_keeps_personal_entries_and_rolls_back(
        self,
    ) -> None:
        checkout = self.copy_checkout("legacy-whole-command-checkout")
        legacy = checkout / "build/commands"
        legacy.mkdir(parents=True)
        (legacy / "fix-bug.md").write_text("# Legacy toolkit alias\n")
        (legacy / "personal.md").write_text("# Personal alias\n")
        external = checkout / "my-commands/personal.md"
        external.parent.mkdir()
        external.write_text("# External personal alias\n")
        (legacy / "personal-link.md").symlink_to("../../my-commands/personal.md")
        personal_directory = legacy / "personal-directory"
        personal_directory.mkdir()
        (personal_directory / "nested-link.md").symlink_to(
            "../../../my-commands/personal.md"
        )
        claude = self.home / ".claude"
        claude.mkdir(parents=True)
        commands = claude / "commands"
        commands.symlink_to(legacy)
        paths = resolve_paths(
            checkout,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )

        result = install(paths)

        self.assertEqual("ok", result.status, result.conflicts)
        self.assertTrue(commands.is_dir())
        self.assertFalse(commands.is_symlink())
        self.assertFalse((commands / "fix-bug.md").exists())
        self.assertEqual("# Personal alias\n", (commands / "personal.md").read_text())
        self.assertTrue((commands / "personal-link.md").is_symlink())
        self.assertEqual(
            "# External personal alias\n",
            (commands / "personal-link.md").read_text(),
        )
        self.assertEqual(
            "# External personal alias\n",
            (commands / "personal-directory/nested-link.md").read_text(),
        )
        self.assertEqual("# Legacy toolkit alias\n", (legacy / "fix-bug.md").read_text())
        self.assertEqual("# Personal alias\n", (legacy / "personal.md").read_text())

        restored = rollback(paths)

        self.assertEqual("ok", restored.status, restored.conflicts)
        self.assertTrue(commands.is_symlink())
        self.assertEqual("# Legacy toolkit alias\n", (commands / "fix-bug.md").read_text())
        self.assertEqual("# Personal alias\n", (commands / "personal.md").read_text())
        self.assertEqual(
            "# External personal alias\n",
            (commands / "personal-link.md").read_text(),
        )
        self.assertEqual(
            "# External personal alias\n",
            (commands / "personal-directory/nested-link.md").read_text(),
        )

    def test_0_1_command_inventory_is_independent_of_the_live_manifest(self) -> None:
        checkout = self.copy_checkout("legacy-inventory-checkout")
        manifest = checkout / "interfaces/workflows.json"
        payload = json.loads(manifest.read_text())
        payload["workflows"] = [
            item for item in payload["workflows"] if item["name"] != "fix-bug"
        ]
        manifest.write_text(json.dumps(payload))
        paths = resolve_paths(
            checkout,
            self.home,
            self.home / ".codex",
            self.home / ".agents",
        )

        names = {target.name for target in _legacy_command_targets(paths)}

        self.assertIn("command:fix-bug", names)
        self.assertIn("command:create-status-report", names)

    def test_concurrent_installs_serialize_to_one_change_and_one_noop(self) -> None:
        command = [
            str(ROOT / "bin/aitk"),
            "install",
            "--home",
            str(self.home),
            "--codex-home",
            str(self.home / ".codex"),
            "--agents-dir",
            str(self.home / ".agents"),
            "--json",
        ]
        processes = [
            subprocess.Popen(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(2)
        ]
        output = [process.communicate(timeout=20) for process in processes]
        self.assertEqual([0, 0], [process.returncode for process in processes], output)
        statuses = sorted(json.loads(stdout)["status"] for stdout, _ in output)
        self.assertEqual(["noop", "ok"], statuses)
        self.assertIn(
            "PASS: installed artifacts match the ownership ledger",
            inspect_install(self.paths),
        )

    def test_concurrent_installs_with_overlapping_roots_cannot_corrupt_state(
        self,
    ) -> None:
        base = [
            str(ROOT / "bin/aitk"),
            "--root",
            str(ROOT),
            "install",
            "--home",
            str(self.home),
            "--codex-home",
            str(self.home / ".codex"),
            "--json",
        ]
        commands = [
            base + ["--agents-dir", str(self.home / name)]
            for name in (".agents-one", ".agents-two")
        ]
        processes = [
            subprocess.Popen(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for command in commands
        ]
        output = [process.communicate(timeout=30) for process in processes]

        self.assertEqual(
            [0, 1], sorted(process.returncode for process in processes), output
        )
        statuses = sorted(json.loads(stdout)["status"] for stdout, _ in output)
        self.assertEqual(["ok", "refused"], statuses)
        ledger = json.loads(self.paths.ledger.read_text())
        self.assertEqual("installed", ledger["status"])
        for record in ledger["active"]:
            target = Path(record["target"])
            self.assertTrue(os.path.lexists(target), target)
            if record["kind"] == "symlink":
                self.assertTrue(target.is_symlink(), target)
                self.assertEqual(record["source"], os.readlink(target))

    def test_lifecycle_lock_directory_cannot_be_a_symlink(self) -> None:
        fake_tmp = Path(self.temporary.name) / "lock-tmp"
        outside = Path(self.temporary.name) / "outside-lock"
        fake_tmp.mkdir()
        outside.mkdir()
        outside.chmod(0o755)
        lock_root = fake_tmp / f"ai-toolkit-lifecycle-locks-{os.getuid()}"
        lock_root.symlink_to(outside, target_is_directory=True)
        before = tree_state(self.home)

        with mock.patch(
            "aitk.installer.tempfile.gettempdir", return_value=str(fake_tmp)
        ):
            result = install(self.paths)

        self.assertEqual("refused", result.status)
        self.assertIn("lock directory is unsafe", " ".join(result.conflicts))
        self.assertEqual(before, tree_state(self.home))
        self.assertEqual(0o755, stat.S_IMODE(outside.stat().st_mode))

    def test_moved_checkout_upgrade_and_rollback_restore_recorded_root(self) -> None:
        first = Path(self.temporary.name) / "checkout-one"
        second = Path(self.temporary.name) / "checkout-two"
        for checkout in (first, second):
            for name in (
                "config",
                "docs",
                "interfaces",
                "rules",
                "skills",
                "extensions",
            ):
                shutil.copytree(ROOT / name, checkout / name, symlinks=True)
            for filename in ("pyproject.toml", "PROJECT_TEMPLATE.md"):
                shutil.copy2(ROOT / filename, checkout / filename)
        first_paths = resolve_paths(
            first, self.home, self.home / ".codex", self.home / ".agents"
        )
        second_paths = resolve_paths(
            second, self.home, self.home / ".codex", self.home / ".agents"
        )
        self.assertEqual("ok", install(first_paths).status)
        self.assertEqual("upgrade", install(second_paths).operation)
        self.assertEqual(
            str(second / "skills/workflows"),
            os.readlink(self.home / ".agents/skills/workflows"),
        )

        restored = rollback(second_paths)

        self.assertEqual("ok", restored.status, restored.conflicts)
        self.assertEqual(
            str(first / "skills/workflows"),
            os.readlink(self.home / ".agents/skills/workflows"),
        )
        ledger = json.loads(self.paths.ledger.read_text())
        self.assertEqual(str(first), ledger["toolkit_root"])
        self.assertTrue(
            any(
                "another toolkit checkout" in item
                for item in inspect_install(second_paths)
            )
        )
        self.assertIn(
            "PASS: installed artifacts match the ownership ledger",
            inspect_install(first_paths),
        )

    def test_shell_wrapper_rejects_unsupported_python_before_mutation(self) -> None:
        fake = Path(self.temporary.name) / "python-old"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        env = os.environ.copy()
        env.update({"HOME": str(self.home), "PYTHON": str(fake)})
        result = subprocess.run(
            ["/bin/sh", str(ROOT / "install.sh")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("Python 3.11 or newer", result.stderr)
        self.assertEqual((), tree_state(self.home))

    def test_installed_doctor_pass_drift_fail_and_strict_exit_matrix(self) -> None:
        self.assertEqual("ok", install(self.paths).status)

        def installed_status(with_pgm: bool = False) -> str:
            return next(
                finding.status
                for finding in run_doctor(
                    ROOT,
                    installed_paths=self.paths,
                    with_pgm=with_pgm,
                )
                if finding.check == "installed-state"
            )

        self.assertEqual("PASS", installed_status())
        self.assertEqual("DRIFT", installed_status(with_pgm=True))
        target = self.home / ".agents/skills/workflows"
        target.unlink()
        self.assertEqual("FAIL", installed_status())

        command = [
            str(ROOT / "bin/aitk"),
            "doctor",
            "--installed",
            "--strict",
            "--home",
            str(self.home),
            "--codex-home",
            str(self.home / ".codex"),
            "--agents-dir",
            str(self.home / ".agents"),
            "--json",
        ]
        failed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, failed.returncode)
        self.assertEqual(
            "FAIL",
            next(
                item["status"]
                for item in json.loads(failed.stdout)["findings"]
                if item["check"] == "installed-state"
            ),
        )

    def test_lifecycle_cli_json_has_stable_schema(self) -> None:
        command = [
            str(ROOT / "bin/aitk"),
            "install",
            "--home",
            str(self.home),
            "--codex-home",
            str(self.home / ".codex"),
            "--agents-dir",
            str(self.home / ".agents"),
            "--json",
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {"operation", "status", "changed", "conflicts", "ledger"},
            set(json.loads(result.stdout)),
        )

        for action in ("uninstall", "rollback"):
            with self.subTest(action=action):
                lifecycle = subprocess.run(
                    [
                        str(ROOT / "bin/aitk"),
                        action,
                        "--home",
                        str(self.home),
                        "--codex-home",
                        str(self.home / ".codex"),
                        "--agents-dir",
                        str(self.home / ".agents"),
                        "--json",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, lifecycle.returncode, lifecycle.stderr)
                self.assertEqual(
                    {"operation", "status", "changed", "conflicts", "ledger"},
                    set(json.loads(lifecycle.stdout)),
                )


if __name__ == "__main__":
    unittest.main()
