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
from aitk.project_state import (
    BEGIN as SNAPSHOT_BEGIN,
    END as SNAPSHOT_END,
    ProjectStateError,
    advance_phase,
    initialize as initialize_snapshot,
    parse_project_state,
    record_gate,
)
from aitk.workflows import load_workflows


ROOT = Path(__file__).resolve().parents[1]
DIGEST_A = "sha256:" + "a" * 64
SNAPSHOT_GATES = ("verification", "review")


def pass_gates(path: Path, workflow: str, *gates: str) -> None:
    """Record the snapshot gates a reservation is allowed to rely on.

    Two records, one truth: ``reserve`` refuses an effect the contract gates on
    ``verification`` or ``review`` unless the routing snapshot in the same file
    shows that gate ``PASS``, so a test that reserves such an effect records the
    gates the way a workflow would.
    """
    initialize_snapshot(path, workflow, "STANDARD", "M")
    for gate in gates or SNAPSHOT_GATES:
        record_gate(path, gate, "PASS")


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
        self.directory = Path(self.temporary.name).resolve()
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
        pass_gates(path, "create-feature")
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
        lock_root = fake_tmp / f"ai-toolkit-artifact-locks-{os.getuid()}"
        lock_root.symlink_to(outside, target_is_directory=True)
        path = self.directory / "PROJECT.md"

        with mock.patch(
            "aitk.artifact_lock.tempfile.gettempdir", return_value=str(fake_tmp)
        ):
            with self.assertRaisesRegex(CheckpointError, "lock directory is unsafe"):
                initialize(ROOT, "create-feature", path)
            # The snapshot runtime shares the lock and refuses the same directory.
            with self.assertRaisesRegex(ProjectStateError, "lock directory is unsafe"):
                initialize_snapshot(path, "create-feature", "STANDARD", "M")

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
        pass_gates(path, "create-feature")
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
                pass_gates(path, workflow)
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
        pass_gates(path, "address-feedback")
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
        pass_gates(path, "create-feature")
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
                pass_gates(path, "create-feature")
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

    def test_gated_effects_require_the_snapshot_gates_to_pass(self) -> None:
        """Two records, one truth is enforced, not narrated."""
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        with self.assertRaisesRegex(CheckpointError, "no snapshot exists"):
            reserve(ROOT, "create-feature", path, "commit_sha", "commit-1")
        initialize_snapshot(path, "create-feature", "STANDARD", "M")
        with self.assertRaisesRegex(CheckpointError, "verification=unrecorded; review=unrecorded"):
            reserve(ROOT, "create-feature", path, "commit_sha", "commit-1")
        record_gate(path, "verification", "PASS")
        record_gate(path, "review", "RETRY", "slice-1")
        with self.assertRaisesRegex(CheckpointError, r"review=RETRY \(unit slice-1\)"):
            reserve(ROOT, "create-feature", path, "commit_sha", "commit-1")
        self.assertEqual(0, len(validate(ROOT, "create-feature", path).effects))
        record_gate(path, "review", "PASS", "slice-1")
        reserved = reserve(ROOT, "create-feature", path, "commit_sha", "commit-1")
        self.assertEqual("pending", reserved.effects[0]["status"])
        # The snapshot and the checkpoint share one file and neither write
        # disturbs the other block.
        self.assertEqual(1, path.read_text().count(BEGIN))
        self.assertIn("aitk-project-state", path.read_text())
        # Every durable effect is gated on verification or review, so there is
        # no reservation the snapshot check does not cover.
        for contract in self.contracts.values():
            if contract["resumable"] and contract["idempotency_keys"]:
                self.assertTrue(
                    set(SNAPSHOT_GATES) & set(contract["authorization"]["gates"]),
                    contract["name"],
                )
        # A workflow gated on one of the two needs only that one.
        single = self.directory / "watch.md"
        initialize(ROOT, "watch-pr", single)
        pass_gates(single, "watch-pr", "verification")
        self.assertEqual(1, len(reserve(ROOT, "watch-pr", single, "provider_operation", "poll-1").effects))
        # An unreadable snapshot fails closed rather than reading as "no gates".
        broken = self.directory / "broken.md"
        initialize(ROOT, "create-feature", broken)
        pass_gates(broken, "create-feature")
        broken.write_text(broken.read_text().replace('"gates":', '"gates":"x",'))
        with self.assertRaisesRegex(CheckpointError, "routing snapshot is unreadable"):
            reserve(ROOT, "create-feature", broken, "commit_sha", "commit-1")

    def test_gate_record_is_scoped_to_phase_and_unit(self) -> None:
        """A PASS from another phase or another slice never authorizes an effect."""
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        initialize_snapshot(path, "create-feature", "COMPLEX", "L", "phased", phase="implement")
        record_gate(path, "verification", "PASS")
        # Slice two is still open: a PASS on slice one does not read as PASS.
        record_gate(path, "review", "RETRY", "slice-2")
        record_gate(path, "review", "PASS", "slice-1")
        with self.assertRaisesRegex(CheckpointError, r"review=RETRY \(unit slice-2\)"):
            reserve(ROOT, "create-feature", path, "commit_sha", "phase-1")
        record_gate(path, "review", "PASS", "slice-2")
        reserve(ROOT, "create-feature", path, "commit_sha", "phase-1")
        # The next phase starts with no verification or review: the old PASS
        # is cleared on advance, so the integrated review cannot ride on a
        # per-unit PASS from the previous phase.
        advance_phase(path, "verify")
        with self.assertRaisesRegex(CheckpointError, r"phase verify \(verification=unrecorded; review=unrecorded\)"):
            reserve(ROOT, "create-feature", path, "published_pr", "pr-phase-1")
        snapshot = parse_project_state(path.read_text())
        assert snapshot is not None
        self.assertEqual({"classification"}, set(snapshot["gates"]))
        # A record whose phase does not match the current phase is refused
        # even when advance did not clear it (a hand-edited or older snapshot).
        record_gate(path, "verification", "PASS")
        record_gate(path, "review", "PASS")
        content = path.read_text()
        body = content.split(SNAPSHOT_BEGIN + "\n", 1)[1].split("\n" + SNAPSHOT_END, 1)[0]
        payload = json.loads(body)
        payload["gates"]["review"]["phase"] = "implement"
        path.write_text(content.replace(body, json.dumps(payload, indent=2, sort_keys=True)))
        with self.assertRaisesRegex(CheckpointError, "review=PASS recorded in phase implement, not verify"):
            reserve(ROOT, "create-feature", path, "published_pr", "pr-phase-1")

    def test_snapshot_and_checkpoint_writers_share_one_lock(self) -> None:
        """Gate records and reservations rewrite the same file; neither may drop the other."""
        path = self.directory / "PROJECT.md"
        initialize(ROOT, "create-feature", path)
        pass_gates(path, "create-feature")
        aitk = str(ROOT / "bin/aitk")
        commands = [
            [aitk, "checkpoint", "reserve", "--workflow", "create-feature", "--file", str(path),
             "--key", "commit_sha", "--operation-id", operation]
            for operation in ("commit-one", "commit-two")
        ] + [
            [aitk, "project-state", "gate", "--file", str(path), "--gate", "rca", "--status", "PASS",
             "--unit", unit]
            for unit in ("unit-a", "unit-b", "unit-c", "unit-d")
        ]
        processes = [
            subprocess.Popen(command, cwd=self.directory, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for command in commands
        ]
        results = [process.communicate(timeout=20) for process in processes]
        self.assertEqual([0] * len(commands), [process.returncode for process in processes], results)

        final = validate(ROOT, "create-feature", path)
        self.assertEqual({"commit-one", "commit-two"}, {str(item["operation_id"]) for item in final.effects})
        snapshot = parse_project_state(path.read_text())
        assert snapshot is not None
        self.assertEqual(
            {"unit-a": "PASS", "unit-b": "PASS", "unit-c": "PASS", "unit-d": "PASS"},
            snapshot["gates"]["rca"]["units"],
        )
        self.assertEqual("PASS", snapshot["gates"]["verification"]["status"])
        self.assertEqual(1, path.read_text().count(BEGIN))

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
