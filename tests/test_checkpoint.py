from __future__ import annotations

from collections import deque
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from aitk.checkpoint import (
    BEGIN,
    END,
    CheckpointError,
    advance,
    apply,
    canonical_json,
    initialize,
    parse_checkpoint,
    reconcile_pending,
    reserve,
    validate,
    validate_transition,
)
from aitk.conformance import contract_digest, contracts_by_name
from aitk.workflows import load_workflows


ROOT = Path(__file__).resolve().parents[1]
DIGEST_A = "sha256:" + "a" * 64


def machine_payload(path: Path) -> dict[str, object]:
    content = path.read_text()
    body = content.split(BEGIN + "\n", 1)[1].split("\n" + END, 1)[0]
    return json.loads(body)


def replace_payload(path: Path, payload: dict[str, object]) -> None:
    content = path.read_text()
    start = content.index(BEGIN)
    finish = content.index(END) + len(END)
    path.write_text(
        content[:start]
        + BEGIN
        + "\n"
        + canonical_json(payload)
        + "\n"
        + END
        + content[finish:]
    )


def shortest_phase_path(contract: dict[str, object], target: str) -> list[str]:
    first = str(contract["phases"][0])
    queue: deque[tuple[str, list[str]]] = deque([(first, [])])
    seen = {first}
    edges: dict[str, list[str]] = {}
    for transition in contract["transitions"]:
        source, destination = transition["from"], transition["to"]
        if not str(destination).startswith("$"):
            edges.setdefault(str(source), []).append(str(destination))
    while queue:
        current, path = queue.popleft()
        if current == target:
            return path
        for destination in edges.get(current, []):
            if destination not in seen:
                seen.add(destination)
                queue.append((destination, path + [destination]))
    raise AssertionError(f"unreachable phase: {target}")


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.contracts = contracts_by_name(ROOT)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_every_durable_phase_round_trips_in_a_fresh_process(self) -> None:
        durable = [
            workflow
            for workflow in load_workflows(ROOT, include_pgm=True)
            if workflow.execution_class == "durable"
        ]
        self.assertEqual(15, len(durable))
        for workflow in durable:
            contract = self.contracts[workflow.name]
            for phase in contract["resume_from"]:
                with self.subTest(workflow=workflow.name, phase=phase):
                    path = self.directory / f"{workflow.name}-{phase}.md"
                    initialize(
                        ROOT,
                        workflow.name,
                        path,
                        include_pgm=workflow.owner_skill == "pgm",
                    )
                    for target in shortest_phase_path(contract, str(phase)):
                        advance(
                            ROOT,
                            workflow.name,
                            path,
                            target,
                            include_pgm=workflow.owner_skill == "pgm",
                        )
                    command = [
                        str(ROOT / "bin/aitk"),
                        "checkpoint",
                        "validate",
                        "--workflow",
                        workflow.name,
                        "--file",
                        str(path),
                        "--json",
                    ]
                    if workflow.owner_skill == "pgm":
                        command.append("--with-pgm")
                    result = subprocess.run(
                        command,
                        cwd=self.directory,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(phase, json.loads(result.stdout)["phase"])

    def test_init_preserves_human_content_and_replaces_one_existing_block(self) -> None:
        path = self.directory / "PROJECT.md"
        path.write_text("# Human state\n\nkeep this\n")
        first = initialize(ROOT, "create-feature", path)
        self.assertEqual(0, first.generation)
        self.assertIn("# Human state", path.read_text())
        self.assertEqual(1, path.read_text().count(BEGIN))
        advanced = advance(ROOT, "create-feature", path, "implement")
        second = initialize(ROOT, "create-feature", path)
        self.assertFalse(second.changed)
        self.assertEqual(advanced.generation, second.generation)
        self.assertEqual("implement", second.phase)
        self.assertEqual(1, path.read_text().count(BEGIN))
        self.assertIn("keep this", path.read_text())

        with self.assertRaisesRegex(CheckpointError, "another durable workflow"):
            initialize(ROOT, "fix-bug", path)
        self.assertEqual("create-feature", machine_payload(path)["workflow"])

    def test_init_replacement_refuses_pending_effects(self) -> None:
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        reserve(ROOT, "create-feature", path, "commit_sha", "commit-pending")

        with self.assertRaisesRegex(CheckpointError, "pending effects"):
            initialize(
                ROOT,
                "create-feature",
                path,
                replace_existing=True,
            )

        apply(
            ROOT,
            "create-feature",
            path,
            "commit_sha",
            "commit-pending",
            DIGEST_A,
        )
        replaced = initialize(
            ROOT,
            "fix-bug",
            path,
            replace_existing=True,
        )
        self.assertTrue(replaced.changed)
        self.assertEqual("fix-bug", replaced.workflow)
        self.assertEqual(0, replaced.generation)

    def test_checkpoint_paths_reject_symlinks_without_outside_mutation(self) -> None:
        outside = self.directory / "outside"
        outside.mkdir()
        outside_file = outside / "PROJECT.md"
        outside_file.write_text("safe\n")

        leaf = self.directory / "leaf.md"
        leaf.symlink_to(outside_file)
        with self.assertRaisesRegex(CheckpointError, "symlink"):
            initialize(ROOT, "create-feature", leaf)
        self.assertEqual("safe\n", outside_file.read_text())

        linked_parent = self.directory / "linked"
        linked_parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(CheckpointError, "symlink"):
            initialize(ROOT, "create-feature", linked_parent / "PROJECT.md")
        self.assertEqual("safe\n", outside_file.read_text())

    def test_checkpoint_lock_directory_cannot_be_a_symlink(self) -> None:
        fake_tmp = self.directory / "tmp"
        outside = self.directory / "outside-lock"
        fake_tmp.mkdir()
        outside.mkdir()
        outside.chmod(0o755)
        lock_root = fake_tmp / f"ai-toolkit-checkpoint-locks-{os.getuid()}"
        lock_root.symlink_to(outside, target_is_directory=True)
        path = self.directory / "PROJECT.md"

        with mock.patch(
            "aitk.checkpoint.tempfile.gettempdir", return_value=str(fake_tmp)
        ):
            with self.assertRaisesRegex(CheckpointError, "lock directory is unsafe"):
                initialize(ROOT, "create-feature", path)

        self.assertFalse(path.exists())
        self.assertEqual(0o755, outside.stat().st_mode & 0o777)

    def test_phase_and_generation_transition_rules_reject_replay(self) -> None:
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        before = machine_payload(path)
        contract = self.contracts["create-feature"]
        after = copy.deepcopy(before)
        after["phase"] = "implement"
        for generation in (0, 2, 10):
            with self.subTest(generation=generation):
                candidate = copy.deepcopy(after)
                candidate["generation"] = generation
                with self.assertRaisesRegex(CheckpointError, "exactly one"):
                    validate_transition(before, candidate, contract)
        with self.assertRaisesRegex(CheckpointError, "illegal"):
            advance(ROOT, "create-feature", path, "verify")
        self.assertEqual(
            1, advance(ROOT, "create-feature", path, "implement").generation
        )

    def test_reserve_apply_and_identical_replay_are_idempotent(self) -> None:
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        reserved = reserve(ROOT, "create-feature", path, "commit_sha", "commit-123")
        self.assertEqual(1, reserved.generation)
        repeated_reserve = reserve(
            ROOT, "create-feature", path, "commit_sha", "commit-123"
        )
        self.assertFalse(repeated_reserve.changed)
        self.assertEqual(1, repeated_reserve.generation)
        applied = apply(
            ROOT, "create-feature", path, "commit_sha", "commit-123", DIGEST_A
        )
        self.assertEqual(2, applied.generation)
        replay = apply(
            ROOT, "create-feature", path, "commit_sha", "commit-123", DIGEST_A
        )
        self.assertFalse(replay.changed)
        self.assertEqual(2, replay.generation)
        with self.assertRaisesRegex(CheckpointError, "cannot be changed"):
            apply(
                ROOT,
                "create-feature",
                path,
                "commit_sha",
                "commit-123",
                "sha256:" + "b" * 64,
            )
        second = reserve(ROOT, "create-feature", path, "commit_sha", "commit-456")
        self.assertEqual(3, second.generation)
        self.assertEqual(2, len(second.effects))

    def test_repeatable_provider_effects_are_instance_scoped(self) -> None:
        for workflow in ("address-feedback", "review-pr", "watch-pr"):
            with self.subTest(workflow=workflow):
                path = self.directory / f"{workflow}.md"
                initialize(ROOT, workflow, path)
                first = reserve(ROOT, workflow, path, "provider_operation", "round-1")
                first = apply(
                    ROOT,
                    workflow,
                    path,
                    "provider_operation",
                    "round-1",
                    DIGEST_A,
                )
                second = reserve(ROOT, workflow, path, "provider_operation", "round-2")
                self.assertEqual(2, len(second.effects))
                self.assertEqual("applied", first.effects[0]["status"])
                self.assertEqual("pending", second.effects[1]["status"])
                replay = reserve(ROOT, workflow, path, "provider_operation", "round-2")
                self.assertFalse(replay.changed)
                applied_replay = reserve(
                    ROOT, workflow, path, "provider_operation", "round-1"
                )
                self.assertFalse(applied_replay.changed)

    def test_repeatable_effect_crash_windows_reconcile_each_operation_once(
        self,
    ) -> None:
        path = self.directory / "feedback.md"
        initialize(ROOT, "address-feedback", path)
        observed: dict[str, str] = {}
        calls: list[str] = []

        def execute(operation_id: str) -> str:
            if operation_id not in observed:
                calls.append(operation_id)
                observed[operation_id] = (
                    "sha256:" + hashlib.sha256(operation_id.encode()).hexdigest()
                )
            return observed[operation_id]

        reserve(ROOT, "address-feedback", path, "provider_operation", "round-1")
        apply(
            ROOT,
            "address-feedback",
            path,
            "provider_operation",
            "round-1",
            execute("round-1"),
        )
        reserve(ROOT, "address-feedback", path, "provider_operation", "round-2")
        execute("round-2")  # crash after provider effect, before checkpoint apply
        reserve(ROOT, "address-feedback", path, "provider_operation", "round-3")

        for effect in validate(ROOT, "address-feedback", path).effects:
            if effect["status"] != "pending":
                continue
            operation_id = str(effect["operation_id"])
            action, digest = reconcile_pending(
                self.contracts["address-feedback"],
                effect,
                lambda value: observed.get(value),
            )
            if action == "retry-same-operation-id":
                digest = execute(operation_id)
            self.assertIsNotNone(digest)
            apply(
                ROOT,
                "address-feedback",
                path,
                "provider_operation",
                operation_id,
                str(digest),
            )

        final = validate(ROOT, "address-feedback", path)
        self.assertEqual(3, len(final.effects))
        self.assertTrue(all(item["status"] == "applied" for item in final.effects))
        self.assertEqual(["round-1", "round-2", "round-3"], calls)

    def test_concurrent_reservations_are_serialized_without_lost_updates(self) -> None:
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        base = [
            str(ROOT / "bin/aitk"),
            "checkpoint",
            "reserve",
            "--workflow",
            "create-feature",
            "--file",
            str(path),
            "--key",
            "commit_sha",
            "--operation-id",
        ]
        processes = [
            subprocess.Popen(
                base + [operation],
                cwd=self.directory,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for operation in ("commit-one", "commit-two")
        ]
        results = [process.communicate(timeout=10) for process in processes]
        self.assertEqual([0, 0], [process.returncode for process in processes], results)

        final = validate(ROOT, "create-feature", path)
        self.assertEqual(2, final.generation)
        self.assertEqual(
            {"commit-one", "commit-two"},
            {str(item["operation_id"]) for item in final.effects},
        )

    def test_effect_crash_windows_reconcile_to_one_operation(self) -> None:
        class Sink:
            def __init__(self) -> None:
                self.values: dict[str, str] = {}
                self.calls = 0

            def lookup(self, operation_id: str) -> str | None:
                return self.values.get(operation_id)

            def execute(self, operation_id: str) -> str:
                if operation_id not in self.values:
                    self.calls += 1
                    self.values[operation_id] = (
                        "sha256:" + hashlib.sha256(operation_id.encode()).hexdigest()
                    )
                return self.values[operation_id]

        for crash in ("before-reserve", "after-reserve", "after-effect", "after-apply"):
            with self.subTest(crash=crash):
                path = self.directory / f"{crash}.md"
                sink = Sink()
                initialize(ROOT, "create-feature", path)
                if crash != "before-reserve":
                    reserve(ROOT, "create-feature", path, "commit_sha", "commit-crash")
                if crash in {"after-effect", "after-apply"}:
                    digest = sink.execute("commit-crash")
                if crash == "after-apply":
                    apply(
                        ROOT,
                        "create-feature",
                        path,
                        "commit_sha",
                        "commit-crash",
                        digest,
                    )

                resumed = validate(ROOT, "create-feature", path)
                if not resumed.effects:
                    resumed = reserve(
                        ROOT, "create-feature", path, "commit_sha", "commit-crash"
                    )
                effect = resumed.effects[0]
                if effect["status"] == "pending":
                    action, observed = reconcile_pending(
                        self.contracts["create-feature"], effect, sink.lookup
                    )
                    if action == "inspect-artifact" and observed is None:
                        observed = sink.execute(str(effect["operation_id"]))
                    self.assertIsNotNone(observed)
                    apply(
                        ROOT,
                        "create-feature",
                        path,
                        str(effect["key"]),
                        str(effect["operation_id"]),
                        str(observed),
                    )
                final = validate(ROOT, "create-feature", path)
                self.assertEqual("applied", final.effects[0]["status"])
                self.assertEqual(1, sink.calls)

    def test_manual_stop_and_provider_reconciliation_never_retry_blindly(self) -> None:
        manual = self.contracts["test-pr"]
        effect = {
            "key": "browser_effect",
            "operation_id": "browser-1",
            "status": "pending",
            "result_digest": None,
        }
        self.assertEqual(
            ("stop-for-user", None),
            reconcile_pending(manual, effect, lambda _: None),
        )
        provider = self.contracts["address-feedback"]
        effect["key"] = "provider_operation"
        self.assertEqual(
            ("retry-same-operation-id", None),
            reconcile_pending(provider, effect, lambda _: None),
        )
        self.assertEqual(
            ("apply-observed", DIGEST_A),
            reconcile_pending(provider, effect, lambda _: DIGEST_A),
        )

    def test_malformed_stale_and_noncanonical_blocks_are_rejected(self) -> None:
        contract = self.contracts["create-feature"]
        valid_path = self.directory / "valid.md"
        initialize(ROOT, "create-feature", valid_path)
        valid = machine_payload(valid_path)
        mutations: list[tuple[str, object]] = [
            ("unknown-field", lambda value: value.update({"extra": True})),
            ("bool-schema", lambda value: value.update({"schema_version": True})),
            ("bool-generation", lambda value: value.update({"generation": True})),
            ("unknown-phase", lambda value: value.update({"phase": "unknown"})),
            (
                "stale-digest",
                lambda value: value.update({"contract_digest": "sha256:" + "0" * 64}),
            ),
            (
                "unknown-effect",
                lambda value: value["effects"].append(
                    {
                        "key": "unknown",
                        "operation_id": "operation-1",
                        "status": "pending",
                        "result_digest": None,
                    }
                ),
            ),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                payload = copy.deepcopy(valid)
                mutate(payload)
                with self.assertRaises(CheckpointError):
                    parse_checkpoint(
                        f"{BEGIN}\n{canonical_json(payload)}\n{END}\n",
                        "create-feature",
                        contract,
                    )
        with self.assertRaisesRegex(CheckpointError, "canonical"):
            parse_checkpoint(
                f"{BEGIN}\n{json.dumps(valid)}\n{END}\n",
                "create-feature",
                contract,
            )
        for content in (
            canonical_json(valid),
            f"{BEGIN}\n{canonical_json(valid)}\n{END}\n{BEGIN}\n{canonical_json(valid)}\n{END}",
            f"{END}\n{canonical_json(valid)}\n{BEGIN}",
        ):
            with self.assertRaises(CheckpointError):
                parse_checkpoint(content, "create-feature", contract)

    def test_contract_digest_is_canonical_and_semantic_changes_go_stale(self) -> None:
        contract = self.contracts["create-feature"]
        reordered = dict(reversed(list(contract.items())))
        self.assertEqual(contract_digest(contract), contract_digest(reordered))
        changed = copy.deepcopy(contract)
        changed["phases"] = list(changed["phases"]) + ["changed"]
        self.assertNotEqual(contract_digest(contract), contract_digest(changed))
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        with self.assertRaisesRegex(CheckpointError, "stale"):
            parse_checkpoint(path.read_text(), "create-feature", changed)

    def test_cli_json_schema_and_refusal_exit_codes(self) -> None:
        path = self.directory / "PROJECT.md"
        init = subprocess.run(
            [
                str(ROOT / "bin/aitk"),
                "checkpoint",
                "init",
                "--workflow",
                "create-feature",
                "--file",
                str(path),
                "--json",
            ],
            cwd=self.directory,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, init.returncode, init.stderr)
        self.assertEqual(
            {"workflow", "phase", "generation", "effects", "file"},
            set(json.loads(init.stdout)),
        )
        refused = subprocess.run(
            [
                str(ROOT / "bin/aitk"),
                "checkpoint",
                "advance",
                "--workflow",
                "create-feature",
                "--file",
                str(path),
                "--to",
                "verify",
            ],
            cwd=self.directory,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, refused.returncode)
        self.assertIn("illegal checkpoint transition", refused.stderr)

    def test_default_live_artifact_is_in_the_calling_project(self) -> None:
        result = subprocess.run(
            [
                str(ROOT / "bin/aitk"),
                "checkpoint",
                "init",
                "--workflow",
                "create-feature",
                "--json",
            ],
            cwd=self.directory,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        expected = self.directory / "PROJECT.md"
        self.assertEqual(str(expected), json.loads(result.stdout)["file"])
        self.assertTrue(expected.is_file())
        self.assertNotEqual(str(ROOT / "PROJECT.md"), json.loads(result.stdout)["file"])


if __name__ == "__main__":
    unittest.main()
