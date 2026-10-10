"""PROJECT.md v2 routing snapshot: schema, derivation, budgets, legacy reads."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from aitk.project_state import (
    ATTEMPT_BUDGET,
    STATE_FILES,
    MAX_ESCALATIONS,
    BEGIN,
    END,
    ProjectStateError,
    advance_phase,
    classify_complexity,
    derive_execution_shape,
    ensure_excluded,
    exclude_entries,
    initialize,
    next_gate_status,
    normalize_complexity,
    parse_project_state,
    record_gate,
    set_fields,
    set_phases,
    show,
    update_phase,
)


ROOT = Path(__file__).resolve().parents[1]


class ClassificationDerivationTests(unittest.TestCase):
    def test_legacy_tiers_dual_read_upward(self) -> None:
        self.assertEqual("TRIVIAL", normalize_complexity("trivial"))
        self.assertEqual("STANDARD", normalize_complexity("MODERATE"))
        # A bare STANDARD is ambiguous between v1 and v2 and reads as v2.
        self.assertEqual("STANDARD", normalize_complexity("STANDARD"))
        self.assertEqual("COMPLEX", normalize_complexity("complex"))
        with self.assertRaises(ProjectStateError):
            normalize_complexity("HEAVY")

    def test_size_does_not_imply_complexity_and_hard_modifiers_force_complex(self) -> None:
        # Renaming a property across 80 files is XL but not COMPLEX.
        self.assertEqual("STANDARD", classify_complexity("STANDARD", ["codemod"]))
        # A one-line permission toggle is S but COMPLEX.
        self.assertEqual(
            "COMPLEX", classify_complexity("TRIVIAL", ["auth-security-permissions"])
        )

    def test_execution_shape_follows_size_and_phaseability(self) -> None:
        cases = {
            ("S", "unassessed"): "SINGLE_PHASE",
            ("M", "unassessed"): "SINGLE_PHASE",
            ("M", "phased"): "MULTI_PHASE",
            ("L", "none"): "SINGLE_PHASE",
            ("L", "repetitive"): "BATCHED",
            ("L", "phased"): "MULTI_PHASE",
            ("XL", "none"): "MULTI_PHASE",
            ("XL", "repetitive"): "BATCHED",
            ("XL", "phased"): "MULTI_PHASE",
        }
        for (size, phaseability), expected in cases.items():
            with self.subTest(size=size, phaseability=phaseability):
                self.assertEqual(expected, derive_execution_shape(size, phaseability))
        # L+ must run the phaseability check; it is never assumed.
        for size in ("L", "XL"):
            with self.assertRaises(ProjectStateError):
                derive_execution_shape(size, "unassessed")

    def test_retry_budget_is_initial_plus_one_informed_retry(self) -> None:
        self.assertEqual(2, ATTEMPT_BUDGET)
        self.assertEqual("RETRY", next_gate_status(1, same_failure=False))
        self.assertEqual("RETRY", next_gate_status(1, same_failure=True))
        self.assertEqual("ESCALATE", next_gate_status(2, same_failure=False))
        self.assertEqual("ESCALATE", next_gate_status(2, same_failure=True))
        self.assertEqual("ESCALATE", next_gate_status(3, same_failure=False))


class SnapshotLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name).resolve() / "PROJECT.md"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_init_appends_block_without_touching_existing_human_state(self) -> None:
        self.path.write_text("## Overview\nexisting notes\n")
        result = initialize(self.path, "fix-bug", "MODERATE", "M")
        self.assertTrue(result.changed)
        content = self.path.read_text()
        self.assertTrue(content.startswith("## Overview\nexisting notes\n"))
        self.assertEqual(1, content.count(BEGIN))
        self.assertEqual(1, content.count(END))
        snapshot = parse_project_state(content)
        assert snapshot is not None
        # Legacy MODERATE reads as v2 STANDARD.
        self.assertEqual("STANDARD", snapshot["complexity"])
        self.assertEqual("SINGLE_PHASE", snapshot["execution_shape"])
        self.assertEqual("PASS", snapshot["gate_status"])
        self.assertEqual({}, snapshot["attempts"])

    def test_repeat_init_is_a_noop_and_other_workflow_refuses(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "S")
        again = initialize(self.path, "fix-bug", "STANDARD", "S")
        self.assertFalse(again.changed)
        self.assertEqual("STANDARD", again.snapshot["complexity"])
        # A different classification is not silently ignored: the caller would
        # believe COMPLEX/XL was recorded while the snapshot still says STANDARD/S.
        with self.assertRaisesRegex(ProjectStateError, "already records STANDARD/S/unassessed.*`set`.*--replace"):
            initialize(self.path, "fix-bug", "COMPLEX", "XL", "phased")
        self.assertEqual(("STANDARD", "S"), (show(self.path).snapshot["complexity"], show(self.path).snapshot["size"]))
        with self.assertRaisesRegex(ProjectStateError, "--replace"):
            initialize(self.path, "create-feature", "STANDARD", "S")
        replaced = initialize(
            self.path, "create-feature", "COMPLEX", "XL", "phased", replace=True
        )
        self.assertEqual("create-feature", replaced.snapshot["workflow"])
        self.assertEqual("MULTI_PHASE", replaced.snapshot["execution_shape"])

    def test_large_single_phase_needs_the_phaseability_proof_recorded(self) -> None:
        with self.assertRaisesRegex(ProjectStateError, "requires a phaseability reason"):
            initialize(self.path, "create-feature", "STANDARD", "L", "none")
        proven = initialize(
            self.path, "create-feature", "STANDARD", "L", "none",
            phaseability_reason="one generated client; no unit verifies alone",
        )
        self.assertEqual("SINGLE_PHASE", proven.snapshot["execution_shape"])
        with self.assertRaisesRegex(ProjectStateError, "requires a phaseability reason"):
            set_fields(self.path, phaseability_reason="")

    def test_complexity_only_moves_upward_by_evidence(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        upgraded = set_fields(self.path, complexity="COMPLEX")
        self.assertEqual("COMPLEX", upgraded.snapshot["complexity"])
        with self.assertRaisesRegex(ProjectStateError, "never silently downgraded"):
            set_fields(self.path, complexity="TRIVIAL")

    def test_gate_budget_escalates_from_durable_attempt_counts(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        first = record_gate(self.path, "verification", "RETRY", "implementation")
        self.assertEqual("RETRY", first.snapshot["gate_status"])
        self.assertEqual({"implementation": 1}, first.snapshot["attempts"])
        second = record_gate(self.path, "verification", "RETRY", "implementation")
        self.assertEqual("ESCALATE", second.snapshot["gate_status"])
        # The exhausted owner hands the unit on: the next owner starts with a
        # fresh attempt budget and the ladder records the step.
        self.assertEqual({}, second.snapshot["attempts"])
        self.assertEqual({"implementation": 1}, second.snapshot["escalations"])
        with self.assertRaisesRegex(ProjectStateError, "cannot advance"):
            advance_phase(self.path, "review")
        passed = record_gate(self.path, "verification", "PASS", "implementation")
        self.assertEqual("PASS", passed.snapshot["gate_status"])
        self.assertEqual({}, passed.snapshot["escalations"])
        # Every outcome lands in the per-gate record the checkpoint runtime
        # reads, scoped to the phase and tracking the unit.
        self.assertEqual(
            {
                "classification": {"status": "PASS", "phase": "intake", "units": {}},
                "verification": {"status": "PASS", "phase": "intake", "units": {"implementation": "PASS"}},
            },
            passed.snapshot["gates"],
        )
        advanced = advance_phase(self.path, "review")
        self.assertEqual(("review", "PENDING"), (advanced.snapshot["current_phase"], advanced.snapshot["gate_status"]))
        # Advancing clears the phase-scoped gates: the next phase earns its own.
        self.assertEqual({"classification"}, set(advanced.snapshot["gates"]))
        # PENDING is not a pass: a phase whose gate was never recorded cannot be left.
        with self.assertRaisesRegex(ProjectStateError, "is PENDING; record a PASS"):
            advance_phase(self.path, "done")

    def test_same_failure_twice_escalates_even_with_budget_left(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        outcome = record_gate(self.path, "rca", "RETRY", "rca-alt", same_failure=True)
        self.assertEqual("RETRY", outcome.snapshot["gate_status"])
        outcome = record_gate(self.path, "rca", "RETRY", "rca-alt", same_failure=True)
        self.assertEqual("ESCALATE", outcome.snapshot["gate_status"])

    def test_same_failure_after_an_escalation_skips_the_new_owners_retry(self) -> None:
        """--same-failure has teeth across owners: the next owner does not get a
        free retry on a reason that already exhausted the previous one."""
        initialize(self.path, "fix-bug", "STANDARD", "M")
        record_gate(self.path, "verification", "RETRY", "fix")
        handed_on = record_gate(self.path, "verification", "RETRY", "fix")
        self.assertEqual(("ESCALATE", {"fix": 1}), (handed_on.snapshot["gate_status"], handed_on.snapshot["escalations"]))
        fresh_reason = record_gate(self.path, "verification", "RETRY", "fix")
        self.assertEqual(("RETRY", {"fix": 1}), (fresh_reason.snapshot["gate_status"], fresh_reason.snapshot["attempts"]))
        initialize(self.path, "fix-bug", "STANDARD", "M", replace=True)
        record_gate(self.path, "verification", "RETRY", "fix")
        record_gate(self.path, "verification", "RETRY", "fix")
        repeated = record_gate(self.path, "verification", "RETRY", "fix", same_failure=True)
        self.assertEqual(("ESCALATE", {}, {"fix": 2}), (repeated.snapshot["gate_status"], repeated.snapshot["attempts"], repeated.snapshot["escalations"]))
        self.assertEqual("ESCALATE", repeated.snapshot["gates"]["verification"]["status"])
        self.assertEqual({"fix": "ESCALATE"}, repeated.snapshot["gates"]["verification"]["units"])

    def test_rca_ladder_is_recordable_on_one_unit_and_ends_in_user_decision(self) -> None:
        """Parent retry, specialist REVISE, deep-rca, then the user: one unit."""
        initialize(self.path, "fix-bug", "COMPLEX", "M")
        statuses: list[str] = []
        for _ in range(MAX_ESCALATIONS):
            statuses.append(record_gate(self.path, "rca", "RETRY", "rca").snapshot["gate_status"])
            statuses.append(record_gate(self.path, "rca", "RETRY", "rca").snapshot["gate_status"])
        self.assertEqual(["RETRY", "ESCALATE"] * MAX_ESCALATIONS, statuses)
        snapshot = show(self.path).snapshot
        self.assertEqual({"rca": MAX_ESCALATIONS}, snapshot["escalations"])
        # A fourth owner does not exist: the ladder hands the decision to the user
        # instead of rejecting the snapshot.
        record_gate(self.path, "rca", "RETRY", "rca")
        final = record_gate(self.path, "rca", "RETRY", "rca")
        self.assertEqual("USER_DECISION", final.snapshot["gate_status"])
        self.assertEqual({"rca": MAX_ESCALATIONS}, final.snapshot["escalations"])
        # An explicit ESCALATE (the specialist answered ESCALATE) climbs the same ladder.
        initialize(self.path, "fix-bug", "COMPLEX", "M", replace=True)
        explicit = record_gate(self.path, "rca", "ESCALATE", "rca")
        self.assertEqual(("ESCALATE", {"rca": 1}), (explicit.snapshot["gate_status"], explicit.snapshot["escalations"]))

    def test_waiting_and_editorial_outcomes_never_charge_the_budget(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        for status in ("USER_DECISION", "BLOCKED"):
            outcome = record_gate(self.path, "plan", status, "plan")
            self.assertEqual(status, outcome.snapshot["gate_status"])
            self.assertEqual({}, outcome.snapshot["attempts"])
        editorial = record_gate(self.path, "plan", "RETRY", "plan", editorial=True)
        self.assertEqual("RETRY", editorial.snapshot["gate_status"])
        self.assertEqual({}, editorial.snapshot["attempts"])
        charged = record_gate(self.path, "plan", "RETRY", "plan")
        self.assertEqual({"plan": 1}, charged.snapshot["attempts"])

    def test_reclassify_resets_counters_because_the_problem_changed(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        record_gate(self.path, "verification", "RETRY", "slice-1")
        record_gate(self.path, "rca", "RETRY", "rca")
        record_gate(self.path, "rca", "RETRY", "rca")
        one = record_gate(self.path, "rca", "RECLASSIFY", "rca")
        self.assertEqual(("RECLASSIFY", {"slice-1": 1}, {}), (one.snapshot["gate_status"], one.snapshot["attempts"], one.snapshot["escalations"]))
        everything = record_gate(self.path, "classification", "RECLASSIFY")
        self.assertEqual(({}, {}), (everything.snapshot["attempts"], everything.snapshot["escalations"]))
        upgraded = set_fields(self.path, complexity="COMPLEX")
        self.assertEqual("COMPLEX", upgraded.snapshot["complexity"])

    def test_snapshot_without_gates_key_reads_as_unrecorded(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        content = self.path.read_text()
        body = content.split(BEGIN + "\n", 1)[1].split("\n" + END, 1)[0]
        payload = json.loads(body)
        del payload["gates"]
        self.path.write_text(content.replace(body, json.dumps(payload, indent=2, sort_keys=True)))
        self.assertEqual({}, show(self.path).snapshot["gates"])
        self.assertEqual(
            {"review": {"status": "PASS", "phase": "intake", "units": {}}},
            record_gate(self.path, "review", "PASS").snapshot["gates"],
        )

    def test_gate_record_aggregates_units_and_a_gate_wide_pass_clears_them(self) -> None:
        initialize(self.path, "create-feature", "COMPLEX", "L", "phased", phase="implement")
        record_gate(self.path, "review", "RETRY", "slice-2")
        one = record_gate(self.path, "review", "PASS", "slice-1")
        # The latest outcome is PASS but slice two is still open, so the
        # aggregate is not.
        self.assertEqual(
            {"status": "RETRY", "phase": "implement", "units": {"slice-2": "RETRY", "slice-1": "PASS"}},
            one.snapshot["gates"]["review"],
        )
        two = record_gate(self.path, "review", "PASS", "slice-2")
        self.assertEqual("PASS", two.snapshot["gates"]["review"]["status"])
        record_gate(self.path, "verification", "RETRY", "slice-1")
        whole = record_gate(self.path, "verification", "PASS")
        self.assertEqual(
            {"status": "PASS", "phase": "implement", "units": {}},
            whole.snapshot["gates"]["verification"],
        )
        # A stale record from another phase is replaced, not merged.
        payload = whole.snapshot["gates"]
        self.assertEqual("implement", payload["review"]["phase"])
        advance_phase(self.path, "verify")
        fresh = record_gate(self.path, "review", "PASS", "integrated")
        self.assertEqual(
            {"status": "PASS", "phase": "verify", "units": {"integrated": "PASS"}},
            fresh.snapshot["gates"]["review"],
        )

    def test_snapshot_without_escalations_key_reads_as_no_escalations(self) -> None:
        initialize(self.path, "fix-bug", "STANDARD", "M")
        content = self.path.read_text()
        start = content.index(BEGIN) + len(BEGIN)
        end = content.index(END)
        payload = json.loads(content[start:end])
        del payload["escalations"]
        self.path.write_text(content[:start] + "\n" + json.dumps(payload) + "\n" + content[end:])
        self.assertEqual({}, show(self.path).snapshot["escalations"])

    def test_template_heading_is_reused_instead_of_duplicated(self) -> None:
        self.path.write_text("## Overview\nnotes\n\n## Routing Snapshot\n<!-- managed by bin/aitk project-state -->\n\n## Notes\n-\n")
        initialize(self.path, "fix-bug", "STANDARD", "M")
        content = self.path.read_text()
        self.assertEqual(1, content.count("## Routing Snapshot"))
        self.assertLess(content.index("## Routing Snapshot"), content.index(BEGIN))
        self.assertLess(content.index(END), content.index("## Notes"))
        self.assertEqual("STANDARD", show(self.path).snapshot["complexity"])

    def test_phases_are_only_recorded_for_multi_phase_work(self) -> None:
        initialize(self.path, "create-feature", "COMPLEX", "XL", "phased")
        phases = [
            {"name": "layout", "complexity": "STANDARD", "size": "M", "status": "active"},
            {"name": "persistence", "complexity": "COMPLEX", "size": "L", "status": "pending"},
        ]
        result = set_phases(self.path, phases)
        self.assertEqual(phases, result.snapshot["phases"])
        # A phase is done only once its tree is recorded: that SHA is the next
        # phase's review base, so it lives in the snapshot, not in memory.
        with self.assertRaisesRegex(ProjectStateError, "without --sha"):
            update_phase(self.path, "layout", "done")
        done = update_phase(self.path, "layout", "done", tree="ABCDEF1234")
        self.assertEqual(("done", "abcdef1234"), (done.snapshot["phases"][0]["status"], done.snapshot["phases"][0]["tree"]))
        with self.assertRaisesRegex(ProjectStateError, "hex SHA"):
            update_phase(self.path, "persistence", "active", tree="not-a-sha")
        self.assertNotIn("tree", show(self.path).snapshot["phases"][1])
        initialize(self.path, "fix-bug", "STANDARD", "M", replace=True)
        with self.assertRaisesRegex(ProjectStateError, "MULTI_PHASE"):
            set_phases(self.path, phases)

    def test_malformed_block_fails_closed(self) -> None:
        self.path.write_text(f"{BEGIN}\n{{not json}}\n{END}\n")
        with self.assertRaisesRegex(ProjectStateError, "not valid JSON"):
            show(self.path)
        snapshot = {
            "schema_version": 2,
            "workflow": "fix-bug",
            "complexity": "STANDARD",
            "classification_confidence": "HIGH",
            "size": "L",
            "execution_shape": "SINGLE_PHASE",
            "phaseability": "phased",
            "phaseability_reason": "",
            "modifiers": [],
            "current_phase": "intake",
            "current_gate": "classification",
            "gate_status": "PASS",
            "attempts": {},
            "phases": [],
        }
        self.path.write_text(f"{BEGIN}\n{json.dumps(snapshot)}\n{END}\n")
        with self.assertRaisesRegex(ProjectStateError, "does not follow"):
            show(self.path)


class ProjectStateCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aitk.cli", "--root", str(ROOT), *arguments],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
        )

    def test_cli_round_trip_emits_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary).resolve()
            init = self.run_cli(
                "project-state",
                "init",
                "--workflow",
                "create-feature",
                "--complexity",
                "STANDARD",
                "--size",
                "L",
                "--phaseability",
                "repetitive",
                "--reason",
                "same rename across many files",
                "--json",
                cwd=cwd,
            )
            self.assertEqual(0, init.returncode, init.stderr)
            payload = json.loads(init.stdout)
            self.assertEqual("BATCHED", payload["snapshot"]["execution_shape"])
            self.assertEqual(str(cwd / "PROJECT.md"), payload["file"])
            gate = self.run_cli(
                "project-state", "gate", "--gate", "verification", "--status", "RETRY",
                "--unit", "wave-1", "--json", cwd=cwd,
            )
            self.assertEqual(0, gate.returncode, gate.stderr)
            self.assertEqual("RETRY", json.loads(gate.stdout)["snapshot"]["gate_status"])
            shown = self.run_cli("project-state", "show", cwd=cwd)
            self.assertEqual(0, shown.returncode, shown.stderr)
            self.assertIn("complexity=STANDARD", shown.stdout)
            self.assertIn("shape=BATCHED", shown.stdout)
            failed = self.run_cli(
                "project-state", "set", "--complexity", "TRIVIAL", cwd=cwd
            )
            self.assertEqual(1, failed.returncode)
            self.assertIn("never silently downgraded", failed.stderr)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", *arguments],
        text=True,
        capture_output=True,
        check=True,
    ).stdout


class ExcludeTests(unittest.TestCase):
    """Local workflow state never shows up in `git status` of the target repo."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_repo(self, name: str) -> Path:
        repo = self.base / name
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text("readme\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-q", "-m", "init")
        return repo

    def init_state(self, cwd: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "aitk.cli", "--root", str(ROOT), "project-state", "init",
                "--workflow", "fix-bug", "--complexity", "TRIVIAL", "--size", "S",
            ],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def assert_clean_with_state(self, checkout: Path) -> None:
        self.assertTrue((checkout / "PROJECT.md").is_file())
        (checkout / ".ai-toolkit").mkdir(exist_ok=True)
        (checkout / ".ai-toolkit" / "config.json").write_text("{}\n")
        for name in STATE_FILES:
            (checkout / name).write_text("state\n")
        self.assertEqual("", git(checkout, "status", "--porcelain", "--untracked-files=all"))

    def test_init_excludes_state_in_a_repository(self) -> None:
        repo = self.make_repo("repo")
        self.init_state(repo)
        exclude = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").strip())
        lines = exclude.read_text().splitlines()
        for entry in (*STATE_FILES, ".ai-toolkit/"):
            self.assertEqual(1, lines.count(entry), entry)
        self.assert_clean_with_state(repo)

    def test_init_excludes_state_in_a_linked_worktree(self) -> None:
        repo = self.make_repo("main-checkout")
        worktree = self.base / "linked"
        git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))
        self.assertTrue((worktree / ".git").is_file())
        self.init_state(worktree)
        self.assert_clean_with_state(worktree)
        self.assertEqual("", git(repo, "status", "--porcelain", "--untracked-files=all"))

    def test_ensure_excluded_is_idempotent_and_keeps_existing_lines(self) -> None:
        repo = self.make_repo("repo")
        exclude = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").strip())
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("# mine\n*.log\nPLAN.md")
        self.assertEqual(exclude, ensure_excluded(repo))
        first = exclude.read_text()
        self.assertTrue(first.startswith("# mine\n*.log\nPLAN.md\n"))
        self.assertEqual(1, first.splitlines().count("PLAN.md"))
        self.assertEqual(exclude, ensure_excluded(repo))
        self.assertEqual(first, exclude.read_text())
        for entry in exclude_entries():
            self.assertEqual(1, first.splitlines().count(entry), entry)

    def test_ensure_excluded_outside_a_repository_writes_nothing(self) -> None:
        outside = self.base / "plain"
        outside.mkdir()
        self.assertIsNone(ensure_excluded(outside))
        self.assertEqual([], list(outside.iterdir()))


def make_repo(base: Path, name: str = "repo") -> Path:
    repo = base / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "app.py").write_text("print('one')\n")
    git(repo, "add", "app.py")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def envelope(tree: str | None, result: dict[str, object] | None = None, **changes: object) -> dict[str, object]:
    """A `model-run` envelope as a completed reviewer lane prints it."""
    from aitk.project_state import result_digest

    result = result or {"status": "completed", "summary": "clean", "findings": [], "verification": ["app.py"]}
    payload: dict[str, object] = {
        "command": "model-run",
        "dry_run": False,
        "route": "review",
        "boundary": "review.independent",
        "provider": "codex",
        "result": result,
        "result_digest": result_digest(result),
        "reviewed_tree": tree,
        "error": None,
    }
    payload.update(changes)
    return payload


class EvidenceRecordTests(unittest.TestCase):
    """P3: verification runs and reviewer records back the gates (PY-14)."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.repo = make_repo(self.base)
        self.path = self.repo / "PROJECT.md"
        initialize(self.path, "fix-bug", "STANDARD", "S")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_working_tree_sha_matches_the_commit_and_ignores_state(self) -> None:
        from aitk.project_state import working_tree_sha

        index = (self.repo / ".git" / "index").read_bytes()
        clean = working_tree_sha(self.repo)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD^{tree}").strip(), clean)
        # State files and .ai-toolkit never enter the tree.
        (self.repo / "PLAN.md").write_text("plan\n")
        (self.repo / ".ai-toolkit").mkdir()
        (self.repo / ".ai-toolkit" / "metrics.jsonl").write_text("{}\n")
        self.assertEqual(clean, working_tree_sha(self.repo))
        # An uncommitted edit changes the tree; committing it gives the same SHA.
        (self.repo / "app.py").write_text("print('two')\n")
        (self.repo / "new.py").write_text("x = 1\n")
        edited = working_tree_sha(self.repo)
        self.assertNotEqual(clean, edited)
        self.assertEqual(index, (self.repo / ".git" / "index").read_bytes(), "the real index moved")
        git(self.repo, "add", "app.py", "new.py")
        git(self.repo, "commit", "-q", "-m", "two")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD^{tree}").strip(), edited)
        self.assertEqual(edited, working_tree_sha(self.repo / ".ai-toolkit"))
        self.assertIsNone(working_tree_sha(self.base))

    def test_verify_run_records_pass_only_on_exit_zero(self) -> None:
        from aitk.project_state import gate_blockers, verify_run, working_tree_sha

        failed = verify_run(self.path, "echo boom; exit 3", cwd=self.repo, unit="fix")
        self.assertEqual("RETRY", failed.status)
        record = failed.result.snapshot["gates"]["verification"]
        self.assertEqual(3, record["run"]["exit_code"])
        self.assertIn("boom", record["run"]["output_tail"])
        self.assertEqual(working_tree_sha(self.repo), record["run"]["tree"])
        self.assertEqual(1, failed.result.snapshot["attempts"]["fix"])
        self.assertTrue(gate_blockers(failed.result.snapshot, ["verification"]))
        passed = verify_run(self.path, "printf 'line\\n%.0s' $(seq 40); echo done", cwd=self.repo, unit="fix")
        self.assertEqual("PASS", passed.status)
        tail = passed.run["output_tail"]
        self.assertTrue(tail.endswith("done"))
        self.assertLessEqual(len(tail.splitlines()), 20)
        self.assertEqual([], gate_blockers(passed.result.snapshot, ["verification"]))
        self.assertFalse(passed.tree_changed)
        changed = verify_run(self.path, "echo more >> app.py", cwd=self.repo)
        self.assertTrue(changed.tree_changed)

    def test_strength_defaults_to_strong_only_for_the_acceptance_command(self) -> None:
        from aitk.project_state import verify_run

        (self.repo / "PLAN.md").write_text(
            "## Implementation Plan\n#### Slice 1: x\n- Acceptance: `python3 -c 'pass'`\n"
        )
        self.assertEqual("STRONG", verify_run(self.path, "python3  -c 'pass'", cwd=self.repo).run["strength"])
        self.assertEqual("PARTIAL", verify_run(self.path, "true", cwd=self.repo).run["strength"])
        self.assertEqual(
            "STRONG", verify_run(self.path, "true", cwd=self.repo, strength="STRONG").run["strength"]
        )
        self.path.write_text(self.path.read_text() + "\nRegression check: `test -f app.py` fails before\n")
        self.assertEqual("STRONG", verify_run(self.path, "test -f app.py", cwd=self.repo).run["strength"])

    def test_a_pass_without_evidence_does_not_count_and_clears_old_evidence(self) -> None:
        from aitk.project_state import gate_blockers, verify_run

        bare = record_gate(self.path, "verification", "PASS").snapshot
        self.assertEqual(["verification=PASS with no recorded run (record it with `bin/aitk verify --run`)"],
                         gate_blockers(bare, ["verification"]))
        self.assertEqual([], gate_blockers(bare, ["verification"], require_records=False))
        verify_run(self.path, "true", cwd=self.repo)
        again = record_gate(self.path, "verification", "PASS").snapshot
        self.assertNotIn("run", again["gates"]["verification"])
        review = record_gate(self.path, "review", "PASS").snapshot
        self.assertIn("no reviewer record", gate_blockers(review, ["review"])[0])

    def test_review_result_records_digest_and_tree_and_refuses_bad_envelopes(self) -> None:
        from aitk.project_state import gate_blockers, review_from_envelopes, working_tree_sha

        tree = working_tree_sha(self.repo)
        review = review_from_envelopes([envelope(tree)])
        self.assertEqual(tree, review["tree"])
        self.assertEqual("review.independent", review["results"][0]["boundary"])
        snapshot = record_gate(self.path, "review", "PASS", review=review).snapshot
        self.assertEqual([], gate_blockers(snapshot, ["review"]))
        good = envelope(tree)
        tampered = dict(good, result={**good["result"], "summary": "edited"})
        for label, bad, message in (
            ("tampered", tampered, "does not match its recorded digest"),
            ("dry run", envelope(tree, dry_run=True), "dry-run"),
            ("error", envelope(tree, error={"code": "x", "message": "y"}), "records an error"),
            ("blocked", envelope(tree, {"status": "blocked", "summary": "s", "findings": [], "verification": []}),
             "did not complete"),
            ("no tree", envelope(None), "does not name the tree"),
            ("other command", envelope(tree, command="model-route"), "JSON envelope"),
        ):
            with self.subTest(label):
                with self.assertRaisesRegex(ProjectStateError, message):
                    review_from_envelopes([bad])
        with self.assertRaisesRegex(ProjectStateError, "different trees"):
            review_from_envelopes([envelope(tree), envelope("a" * 40)])

    def test_cli_records_review_results_and_exceptions(self) -> None:
        from aitk.project_state import working_tree_sha

        envelope_path = self.base / "envelope.json"
        envelope_path.write_text(json.dumps(envelope(working_tree_sha(self.repo))))
        aitk = [sys.executable, "-m", "aitk.cli", "--root", str(ROOT)]
        environment = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}

        def run(*arguments: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([*aitk, *arguments], cwd=self.repo, text=True, capture_output=True,
                                  check=False, env=environment)

        recorded = run("project-state", "gate", "--gate", "review", "--status", "PASS",
                       "--result", str(envelope_path), "--format", "block")
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertIn("## Gate: review", recorded.stdout)
        self.assertIn("review.independent (codex)", recorded.stdout)
        misplaced = run("project-state", "gate", "--gate", "verification", "--status", "PASS",
                        "--result", str(envelope_path))
        self.assertEqual(1, misplaced.returncode)
        self.assertIn("use --gate review", misplaced.stderr)
        refused = run("project-state", "gate", "--gate", "review", "--status", "PASS", "--exception", "micro-fix")
        self.assertEqual(1, refused.returncode)
        self.assertIn("passing verification run", refused.stderr)
        verified = run("verify", "--run", "true")
        self.assertEqual(0, verified.returncode, verified.stderr)
        self.assertIn("## Gate: verification", verified.stdout)
        self.assertIn("Strength: PARTIAL", verified.stdout)
        allowed = run("project-state", "gate", "--gate", "review", "--status", "PASS",
                      "--exception", "micro-fix", "--json")
        self.assertEqual(0, allowed.returncode, allowed.stderr)
        record = json.loads(allowed.stdout)["snapshot"]["gates"]["review"]["review"]
        self.assertEqual("micro-fix", record["exception"])
        failed = run("verify", "--run", "exit 4", "--json")
        self.assertEqual(1, failed.returncode)
        self.assertEqual(4, json.loads(failed.stdout)["run"]["exit_code"])

    def test_format_block_prints_the_complexity_and_gate_blocks(self) -> None:
        from aitk.project_state import complexity_block, gate_block

        snapshot = show(self.path).snapshot
        block = complexity_block(snapshot, "one handler, known pattern")
        self.assertEqual(
            [
                "## Complexity Gate",
                "Complexity: STANDARD",
                "Size: S",
                "Shape: SINGLE_PHASE — S/M default",
                "Confidence: HIGH",
                "Modifiers: none",
                "Reason: one handler, known pattern",
            ],
            block.splitlines(),
        )
        after = record_gate(self.path, "rca", "RETRY", "rca").snapshot
        text = gate_block(snapshot, after, "rca", "rca", evidence="hypothesis disproven")
        self.assertIn("Status: RETRY", text)
        self.assertIn("Attempt: 1/2 on rca", text)
        self.assertIn("Evidence: hypothesis disproven", text)
        self.assertNotIn("Strength:", text)
        escalated = record_gate(self.path, "rca", "RETRY", "rca").snapshot
        text = gate_block(after, escalated, "rca", "rca", next_step="route to the RCA specialist")
        self.assertIn("Status: ESCALATE", text)
        self.assertIn("(escalation 1/3)", text)
        self.assertIn("Next: route to the RCA specialist", text)

    def test_reclassify_and_repeated_failures_append_observations(self) -> None:
        queue = self.repo / ".ai-toolkit" / "observations.jsonl"
        record_gate(self.path, "verification", "RETRY", "fix")
        self.assertFalse(queue.exists(), "a first failure is routine progress")
        record_gate(self.path, "verification", "RETRY", "fix", same_failure=True, reason="same import error")
        record_gate(self.path, "phase-exit", "RECLASSIFY", "decomposition")
        lines = [json.loads(line) for line in queue.read_text().splitlines()]
        self.assertEqual(["gate-repeat", "reclassify"], [line["kind"] for line in lines])
        self.assertEqual("same import error", lines[0]["detail"])
        self.assertEqual("fix-bug", lines[1]["workflow"])
        self.assertIn("decomposition", lines[1]["detail"])
        for line in lines:
            self.assertIn("timestamp", line)
        self.assertIn(".ai-toolkit/", (self.repo / ".git" / "info" / "exclude").read_text())

    def test_observe_appends_one_whitelisted_line(self) -> None:
        aitk = [sys.executable, "-m", "aitk.cli", "--root", str(ROOT)]
        environment = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}
        written = subprocess.run(
            [*aitk, "observe", "--kind", "user-correction", "--detail", "the user rejected the plan's scope",
             "--eval-candidate", "--json"],
            cwd=self.repo / ".git", text=True, capture_output=True, check=False, env=environment,
        )
        self.assertEqual(1, written.returncode, "outside the work tree there is no snapshot to name the workflow")
        written = subprocess.run(
            [*aitk, "observe", "--kind", "user-correction", "--detail", "the user rejected the plan's scope",
             "--eval-candidate", "--json"],
            cwd=self.repo, text=True, capture_output=True, check=False, env=environment,
        )
        self.assertEqual(0, written.returncode, written.stderr)
        line = json.loads((self.repo / ".ai-toolkit" / "observations.jsonl").read_text())
        self.assertEqual("fix-bug", line["workflow"])
        self.assertTrue(line["eval_candidate"])
        unknown = subprocess.run(
            [*aitk, "observe", "--kind", "progress", "--detail", "x"],
            cwd=self.repo, text=True, capture_output=True, check=False, env=environment,
        )
        self.assertEqual(2, unknown.returncode)

    def test_operations_are_recorded_once_and_checked_before_a_repeat(self) -> None:
        from aitk.project_state import operation_recorded, record_operation

        thread = "reply:PRRT_kwDOAbC=12"
        self.assertIsNone(operation_recorded(self.path, thread))
        self.assertTrue(record_operation(self.path, thread).changed)
        self.assertFalse(record_operation(self.path, thread).changed)
        self.assertIsNotNone(operation_recorded(self.path, thread))
        with self.assertRaises(ProjectStateError):
            record_operation(self.path, "reply:has space")
        aitk = [sys.executable, "-m", "aitk.cli", "--root", str(ROOT), "project-state", "op"]
        environment = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}
        fresh = subprocess.run([*aitk, "--check", "push:abc1234"], cwd=self.repo, text=True,
                               capture_output=True, check=False, env=environment)
        self.assertEqual(3, fresh.returncode, fresh.stderr)
        subprocess.run([*aitk, "--id", "push:abc1234"], cwd=self.repo, check=True,
                       capture_output=True, env=environment)
        # A resumed session finds the operation and skips it.
        again = subprocess.run([*aitk, "--check", "push:abc1234"], cwd=self.repo, text=True,
                               capture_output=True, check=False, env=environment)
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn("skip it", again.stdout)

    def test_project_file_is_found_in_the_cwd_then_the_git_root(self) -> None:
        from aitk.project_state import state_file

        nested = self.repo / "pkg" / "src"
        nested.mkdir(parents=True)
        self.assertEqual(self.path, state_file(None, nested))
        local = nested / "PROJECT.md"
        local.write_text("# local\n")
        self.assertEqual(local, state_file(None, nested))
        linked = self.base / "linked"
        linked.symlink_to(self.repo, target_is_directory=True)
        self.assertEqual(self.path, state_file(None, linked))
        outside = self.base / "outside"
        outside.mkdir()
        self.assertEqual(outside / "PROJECT.md", state_file(None, outside))

    def test_transport_and_state_agree_on_the_result_digest(self) -> None:
        from aitk.project_state import result_digest
        from aitk.routing_transport import _result_digest

        result = {"status": "completed", "summary": "é", "findings": ["[minor] a.py:1 x"], "verification": []}
        self.assertEqual(result_digest(result), _result_digest(result))
        self.assertIsNone(_result_digest(None))


if __name__ == "__main__":
    unittest.main()
