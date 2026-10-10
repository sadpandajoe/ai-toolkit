"""`aitk review plan` and `review merge`: the deterministic half of a review.

Each `review plan` decision local-review.md and pr-review.md describe in prose
has a case here (bases, the second-family triggers, the coverage check, the
lens cap that keeps adversarial on a security-sensitive diff, the verifier
family, degraded handling, yield demotions, `--kind pr`), as do `review
merge`'s dedupe, convergence and verifier list, and the `low-yield-lane`
observation `lane-yield` appends. The yield table itself is covered by
tests/test_lane_yield.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

from aitk.review_plan import (
    LANE_WINDOW,
    LENS_WINDOW,
    ChangedFile,
    Demotion,
    PlanInputs,
    ReviewPlanError,
    branch_base,
    classify,
    coverage_gaps,
    evaluate,
    families,
    lane_result,
    local_changes,
    merge,
    phase_base,
    plan,
    pr_changes,
    record_demotions,
    toolkit_sensitive,
)


ROOT = Path(__file__).resolve().parents[1]
TABLE = families(ROOT)
ENVIRONMENT = {
    **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def files(count: int, lines: int = 20, prefix: str = "app/module", suffix: str = ".py") -> tuple[ChangedFile, ...]:
    return tuple(ChangedFile(f"{prefix}{index}{suffix}", lines, 0) for index in range(count))


def inputs(**changes: object) -> PlanInputs:
    values: dict[str, object] = {"parent": "claude", "complexity": "STANDARD", "files": files(3)}
    values.update(changes)
    return PlanInputs(**values)  # type: ignore[arg-type]


def lanes(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(lane["lane"]): lane for lane in payload["lanes"]}  # type: ignore[union-attr]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=ENVIRONMENT
    ).stdout.strip()


class ClassifyTests(unittest.TestCase):
    def test_counts_leave_out_lockfiles_and_generated_files(self) -> None:
        facts = classify(
            [
                ChangedFile("api/views.py", 30, 10),
                ChangedFile("web/package-lock.json", 900, 800),
                ChangedFile("dist/bundle.min.js", 50, 0),
                ChangedFile("agents/claude/x.md", 5, 5, generated_header=True),
                ChangedFile("tests/test_views.py", 12, 0),
            ]
        )
        self.assertEqual((2, 52), (facts["files"], facts["changed_lines"]))
        self.assertEqual(
            {"web/package-lock.json": "lockfile", "dist/bundle.min.js": "generated", "agents/claude/x.md": "generated"},
            facts["excluded"],
        )
        self.assertEqual({"Backend": ["api/views.py"], "Tests": ["tests/test_views.py"]}, facts["domains"])

    def test_refactor_heuristic_titles_renames_and_net_neutral_churn(self) -> None:
        plain = [ChangedFile("app/a.py", 10, 2)]
        self.assertTrue(classify(plain, titles=["Refactor: split the loader"])["refactor_shaped"])
        self.assertTrue(classify(plain, titles=["Extract the parser"])["refactor_shaped"])
        self.assertFalse(classify(plain, titles=["Add the loader"])["refactor_shaped"])
        renamed = [ChangedFile("app/new.py", 0, 0, "renamed", old_path="app/old.py")]
        self.assertEqual("1 rename(s), tests unchanged", classify(renamed)["refactor_why"])
        churn = [ChangedFile("app/a.py", 105, 100)]
        self.assertTrue(classify(churn)["refactor_shaped"])
        self.assertFalse(classify(churn + [ChangedFile("tests/test_a.py", 5, 0)])["refactor_shaped"])
        self.assertFalse(classify([ChangedFile("app/a.py", 150, 50)])["refactor_shaped"])
        self.assertFalse(classify([ChangedFile("yarn.lock", 400, 400)])["refactor_shaped"])

    def test_escalation_phrases_and_a_bare_deep_quality_ask(self) -> None:
        for ask in ("please do a deep review", "Deep Quality Review this", "go thermonuclear"):
            with self.subTest(ask=ask):
                self.assertTrue(classify([], ask=ask)["deep_tier_escalation"])
        self.assertTrue(classify([], effort="ultra")["deep_tier_escalation"])
        self.assertEqual("--deep", classify([], deep=True)["escalation_why"])
        self.assertEqual(["adversarial"], classify([], adversarial=True)["explicit_asks"])
        bare = classify([], ask="a deep quality pass on the parser")
        self.assertFalse(bare["deep_tier_escalation"])
        self.assertEqual(["deep-quality"], bare["explicit_asks"])
        self.assertEqual([], classify([], ask="deep quality review")["explicit_asks"])
        self.assertTrue(classify([], ask="code judo this")["code_judo"])
        self.assertTrue(classify([], titles=["refactor the cache"])["code_judo"])

    def test_toolkit_sensitive_paths_count_only_in_the_toolkit(self) -> None:
        change = [ChangedFile("aitk/routing_policy.py", 3, 1), ChangedFile("agents/codex/x.toml", 1, 1)]
        self.assertFalse(classify(change)["security_sensitive"])
        facts = classify(change, toolkit=True)
        self.assertTrue(facts["security_sensitive"])
        self.assertEqual(["agents/codex/x.toml", "aitk/routing_policy.py"], facts["toolkit_sensitive_hits"])

    def test_the_code_list_covers_every_path_classify_diff_names(self) -> None:
        text = (ROOT / "skills/review/references/classify-diff.md").read_text()
        bullet = re.search(r"^   - \*\*Security-sensitive\*\*.*?(?=^   - \*\*)", text, re.MULTILINE | re.DOTALL)
        assert bullet is not None
        named = [token for token in re.findall(r"`([^`]+)`", bullet.group(0)) if "/" in token]
        self.assertTrue(named)
        for token in named:
            sample = token.replace("*", "x") + ("x.py" if token.endswith("/") else "")
            with self.subTest(path=token):
                self.assertTrue(toolkit_sensitive(sample), sample)

    def test_touch_weight_per_lens(self) -> None:
        facts = classify(
            [
                ChangedFile("api/auth/session.py", 40, 10),
                ChangedFile("web/components/Card.tsx", 20, 0),
                ChangedFile("app/new_module.py", 30, 0, "added"),
                ChangedFile("docs/notes.md", 5, 5),
            ]
        )
        self.assertEqual({"adversarial": 50, "deep-quality": 100, "architecture": 30}, facts["touch"])


class PlanTests(unittest.TestCase):
    def test_independent_lane_runs_on_the_other_provider(self) -> None:
        payload = plan(inputs(), TABLE)
        self.assertEqual("ready", payload["status"])
        self.assertEqual(
            {
                "lane": "independent",
                "boundary": "review.independent",
                "route": "review",
                "provider": "codex",
                "family": "sol",
                "lens": None,
                "note": None,
            },
            lanes(payload)["independent"],
        )
        self.assertEqual(
            {"route": "review", "provider": "claude", "family": "opus", "boundary": "review.verify-major"},
            payload["verifier"],
        )
        self.assertEqual("after-substantive-fix", payload["delta"])
        codex_parent = plan(inputs(parent="codex"), TABLE)
        self.assertEqual("claude", lanes(codex_parent)["independent"]["provider"])

    def test_second_family_triggers_on_complex_or_core(self) -> None:
        self.assertNotIn("second-family", lanes(plan(inputs(), TABLE)))
        for changes, triggers in (({"complexity": "COMPLEX"}, ["COMPLEX"]), ({"impact": "CORE"}, ["CORE"])):
            with self.subTest(**changes):
                payload = plan(inputs(**changes), TABLE)
                second = lanes(payload)["second-family"]
                self.assertEqual(("claude", "opus", "review.second-family"), (second["provider"], second["family"], second["boundary"]))
                self.assertEqual(triggers, payload["second_family"]["triggers"])
                self.assertIsNone(payload["verifier"])
                self.assertEqual("not needed: the second family ran", payload["verifier_note"])

    def test_a_demoted_second_family_drops_only_the_core_trigger(self) -> None:
        demoted = frozenset({"second-family"})
        core = plan(inputs(impact="CORE", demoted=demoted), TABLE)
        self.assertNotIn("second-family", lanes(core))
        self.assertIn("Second family: CORE trigger dropped (low yield; COMPLEX only)", core["disclosures"])
        self.assertIn("second-family", lanes(plan(inputs(complexity="COMPLEX", impact="CORE", demoted=demoted), TABLE)))

    def test_coverage_requires_every_counted_file_and_small_clean_diffs_add_no_lane(self) -> None:
        # The gates eval cases: a clean STANDARD verdict covering 4 of 7 files
        # reruns on the 3 it skipped; a clean small diff adds no second family.
        seven = files(7, lines=48) + (ChangedFile("poetry.lock", 4, 0), ChangedFile("app/gone.py", 0, 9, "deleted"))
        payload = plan(inputs(files=seven), TABLE)
        self.assertEqual([item.path for item in seven[:7]], payload["coverage"]["required"])
        self.assertNotIn("second-family", lanes(payload))
        verification = [f"read {path}" for path in payload["coverage"]["required"][:4]]
        self.assertEqual(payload["coverage"]["required"][4:], coverage_gaps(payload["coverage"]["required"], verification))
        self.assertNotIn("second-family", lanes(plan(inputs(files=files(2, lines=30)), TABLE)))

    def test_coverage_matches_paths_and_unique_file_names(self) -> None:
        required = ["app/a.py", "lib/util.py", "web/util.py"]
        self.assertEqual(["web/util.py"], coverage_gaps(required, ["ran pytest app/a.py", "read lib/util.py"]))
        self.assertEqual(["lib/util.py", "web/util.py"], coverage_gaps(required, ["read a.py and util.py"]))
        self.assertEqual([], coverage_gaps(["app/a.py"], ["checked a.py:12"]))

    def test_the_lens_cap_keeps_adversarial_on_a_security_sensitive_diff(self) -> None:
        heavy = (ChangedFile("app/big.py", 900, 880), ChangedFile("app/auth.py", 2, 0))
        payload = plan(
            inputs(files=heavy, security_sensitive=True, architecture=True, refactor=True), TABLE
        )
        self.assertEqual(["adversarial", "architecture"], payload["deep_lenses"]["launched"])
        self.assertEqual("deep-quality", payload["deep_lenses"]["dropped"]["lens"])
        adversarial = lanes(payload)["adversarial"]
        self.assertEqual(
            ("review.deep-lenses", "deep-review", "codex", "astra", "skills/review/references/adversarial.md"),
            (adversarial["boundary"], adversarial["route"], adversarial["provider"], adversarial["family"], adversarial["lens"]),
        )

    def test_without_security_the_least_touched_lens_is_dropped(self) -> None:
        changed = (
            ChangedFile("app/core.py", 400, 380),
            ChangedFile("app/new_layer.py", 60, 0, "added"),
            ChangedFile("app/token_store.py", 10, 0),
        )
        payload = plan(inputs(files=changed, ask="adversarial please", architecture=True, refactor=True), TABLE)
        self.assertEqual({"lens": "adversarial", "reason": "touched least (10 changed lines)"}, payload["deep_lenses"]["dropped"])
        self.assertLessEqual(len(payload["deep_lenses"]["launched"]), 2)

    def test_architecture_lens_needs_standard_or_complex(self) -> None:
        trivial = plan(inputs(complexity="TRIVIAL", architecture=True), TABLE)
        self.assertNotIn("architecture", trivial["deep_lenses"]["launched"])
        self.assertIn("architecture", plan(inputs(architecture=True), TABLE)["deep_lenses"]["launched"])

    def test_same_provider_fallback_and_the_single_family_verifier(self) -> None:
        payload = plan(inputs(reachable=frozenset({"claude"})), TABLE)
        self.assertEqual(("claude", "opus"), (lanes(payload)["independent"]["provider"], lanes(payload)["independent"]["family"]))
        self.assertIn("Independent review: same-provider", payload["disclosures"])
        self.assertEqual(
            {"route": "deep-review", "provider": "claude", "family": "fable", "boundary": "review.verify-major"},
            payload["verifier"],
        )
        refactor = plan(inputs(reachable=frozenset({"claude"}), refactor=True), TABLE)
        self.assertEqual("fable", lanes(refactor)["deep-quality"]["family"])
        self.assertIn("Deep lens deep-quality: codex unreachable, ran on fable", refactor["disclosures"])

    def test_a_security_sensitive_or_deep_tier_diff_without_the_other_provider_is_blocked(self) -> None:
        for changes in ({"security_sensitive": True}, {"ask": "deep review"}):
            with self.subTest(**changes):
                payload = plan(inputs(reachable=frozenset({"claude"}), **changes), TABLE)
                self.assertEqual("BLOCKED (degraded)", payload["status"])
                self.assertEqual([], payload["lanes"])
                self.assertIsNone(payload["verifier"])
                self.assertIn("--allow-degraded", payload["reason"])
        allowed = plan(inputs(reachable=frozenset({"claude"}), security_sensitive=True, allow_degraded=True), TABLE)
        self.assertEqual("ready", allowed["status"])
        self.assertIn("Independent review: same-provider (--allow-degraded, USER_DECISION)", allowed["disclosures"])
        nothing = plan(inputs(reachable=frozenset()), TABLE)
        self.assertEqual(("BLOCKED", "no review provider is reachable"), (nothing["status"], nothing["reason"]))

    def test_a_security_sensitive_second_family_without_its_provider_is_blocked(self) -> None:
        payload = plan(inputs(parent="codex", complexity="COMPLEX", security_sensitive=True, reachable=frozenset({"claude"})), TABLE)
        self.assertEqual("BLOCKED (degraded)", payload["status"])
        skipped = plan(inputs(parent="codex", complexity="COMPLEX", reachable=frozenset({"claude"})), TABLE)
        self.assertEqual("ready", skipped["status"])
        self.assertEqual("not run: codex unreachable", skipped["second_family"]["note"])

    def test_deep_tier_escalation_pins_complex_and_runs_deep(self) -> None:
        payload = plan(inputs(ask="thermonuclear"), TABLE)
        self.assertEqual("COMPLEX", payload["complexity"])
        self.assertIn("pinned by escalation", payload["complexity_note"])
        self.assertEqual(("deep-review", "astra"), (lanes(payload)["independent"]["route"], lanes(payload)["independent"]["family"]))
        self.assertEqual("fable", lanes(payload)["second-family"]["family"])
        self.assertIn("deep-quality", payload["deep_lenses"]["launched"])
        self.assertEqual("review.code-judo", lanes(payload)["code-judo"]["boundary"])

    def test_trivial_core_is_reviewed_as_standard_without_the_exception(self) -> None:
        core = plan(inputs(complexity="TRIVIAL", impact="CORE"), TABLE)
        self.assertEqual("STANDARD", core["complexity"])
        self.assertFalse(core["exception_available"])
        self.assertIn("independent", lanes(core))
        trivial = plan(inputs(complexity="TRIVIAL"), TABLE)
        self.assertTrue(trivial["exception_available"])
        self.assertEqual("none", trivial["delta"])
        self.assertIn("independent", lanes(trivial))

    def test_yield_demotions_defer_lenses_cap_majors_and_narrow_the_delta(self) -> None:
        demoted = frozenset({"deep-quality", "verify-major", "delta"})
        payload = plan(inputs(refactor=True, demoted=demoted), TABLE)
        self.assertEqual([{"lens": "deep-quality", "reason": "deferred (low yield)"}], payload["deep_lenses"]["deferred"])
        self.assertNotIn("deep-quality", lanes(payload))
        self.assertIsNone(payload["verifier"])
        self.assertEqual("demoted: single-source majors default to [minor]", payload["verifier_note"])
        self.assertEqual("after-major-fix", payload["delta"])
        asked = plan(inputs(refactor=True, ask="deep quality on this", demoted=demoted), TABLE)
        self.assertIn("deep-quality", lanes(asked))

    def test_pr_kind_uses_the_pr_boundaries_and_no_delta(self) -> None:
        payload = plan(inputs(kind="pr", impact="CORE", security_sensitive=True), TABLE)
        self.assertEqual(
            {"review.pr-independent", "review.pr-second-family", "review.pr-deep-lenses"},
            {lane["boundary"] for lane in payload["lanes"]},
        )
        self.assertEqual("none", payload["delta"])
        self.assertFalse(payload["exception_available"])

    def test_rejects_unknown_inputs(self) -> None:
        for changes in ({"parent": "gemini"}, {"kind": "batch"}, {"impact": "HIGH"}, {"complexity": "MODERATE"}):
            with self.subTest(**changes):
                with self.assertRaises(ReviewPlanError):
                    plan(inputs(**changes), TABLE)


class DiffCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve() / "repo"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True, env=ENVIRONMENT)
        (self.repo / "app").mkdir()
        (self.repo / "app/old.py").write_text("".join(f"line {n}\n" for n in range(40)))
        (self.repo / "app/keep.py").write_text("a\nb\n")
        (self.repo / "app/drop.py").write_text("x\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def test_tracked_untracked_renamed_deleted_and_state_files(self) -> None:
        git(self.repo, "mv", "app/old.py", "app/new.py")
        git(self.repo, "rm", "-q", "app/drop.py")
        (self.repo / "app/keep.py").write_text("a\nb\nc\n")
        (self.repo / "app/fresh.py").write_text("1\n2\n3\n")
        (self.repo / "app/blob.bin").write_bytes(b"\0\1\2")
        (self.repo / "app/gen.py").write_text("# Code generated by protoc. DO NOT EDIT.\nx = 1\n")
        (self.repo / "PROJECT.md").write_text("state\n")
        (self.repo / ".ai-toolkit").mkdir()
        (self.repo / ".ai-toolkit/metrics.jsonl").write_text("{}\n")
        changes = {item.path: item for item in local_changes(self.repo, self.base)}
        self.assertEqual(
            {"app/blob.bin", "app/drop.py", "app/fresh.py", "app/gen.py", "app/keep.py", "app/new.py"}, set(changes)
        )
        self.assertEqual(("renamed", "app/old.py"), (changes["app/new.py"].status, changes["app/new.py"].old_path))
        self.assertEqual(("deleted", 1), (changes["app/drop.py"].status, changes["app/drop.py"].deleted))
        self.assertEqual((1, 0, "modified"), (changes["app/keep.py"].added, changes["app/keep.py"].deleted, changes["app/keep.py"].status))
        self.assertEqual((3, "added"), (changes["app/fresh.py"].added, changes["app/fresh.py"].status))
        self.assertTrue(changes["app/blob.bin"].binary)
        self.assertTrue(changes["app/gen.py"].generated_header)

    def test_bases_phase_tree_then_branch_merge_base(self) -> None:
        remote = self.repo.parent / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True, env=ENVIRONMENT)
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "checkout", "-q", "-b", "feat")
        (self.repo / "app/keep.py").write_text("changed\n")
        git(self.repo, "commit", "-q", "-am", "phase one")
        self.assertEqual(self.base, branch_base(self.repo))
        tree = git(self.repo, "rev-parse", "HEAD")
        snapshot = {
            "current_phase": "two",
            "phases": [
                {"name": "one", "status": "done", "tree": tree},
                {"name": "two", "status": "active"},
                {"name": "three", "status": "done", "tree": "f" * 40},
            ],
        }
        self.assertEqual(tree, phase_base(snapshot))
        self.assertIsNone(phase_base({"current_phase": "one", "phases": snapshot["phases"]}))
        self.assertIsNone(phase_base(None))

    def test_pr_changes_read_gh_pr_view(self) -> None:
        stub = self.repo.parent / "bin"
        stub.mkdir()
        gh = stub / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "echo '{\"title\": \"Refactor the loader\", \"baseRefName\": \"main\", "
            "\"files\": [{\"path\": \"app/a.py\", \"additions\": 3, \"deletions\": 1}]}'\n"
        )
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        env = {**ENVIRONMENT, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        changed, title, base = pr_changes(self.repo, "12", env)
        self.assertEqual(([ChangedFile("app/a.py", 3, 1)], "Refactor the loader", "main"), (changed, title, base))
        gh.write_text("#!/bin/sh\necho 'not json'\n")
        with self.assertRaises(ReviewPlanError):
            pr_changes(self.repo, "12", env)


def envelope(boundary: str, provider: str, route: str, findings: list[str], verification: list[str] | None = None) -> dict[str, object]:
    return {
        "command": "model-run",
        "dry_run": False,
        "boundary": boundary,
        "provider": provider,
        "route": route,
        "request": {"family": TABLE[route][provider]},
        "result": {"status": "completed", "summary": "s", "findings": findings, "verification": verification or []},
    }


class MergeTests(unittest.TestCase):
    def test_dedupes_by_file_and_line_and_counts_convergence(self) -> None:
        independent = lane_result(
            envelope("review.independent", "codex", "review", ["[major] app/a.py:10 races on the cache", "[minor] app/b.py:3 shadowed name"])
        )
        second = lane_result(
            envelope("review.second-family", "claude", "review", ["[minor] app/a.py:10 the cache write is unguarded", "[nitpick] app/c.py:1 naming"])
        )
        payload = merge([independent, second], TABLE)
        by_key = {entry["key"]: entry for entry in payload["findings"]}
        self.assertEqual(["app/a.py:10", "app/b.py:3", "app/c.py:1"], list(by_key))
        self.assertEqual(("major", ["independent", "second-family"], True), (by_key["app/a.py:10"]["severity"], by_key["app/a.py:10"]["lanes"], by_key["app/a.py:10"]["convergent"]))
        self.assertEqual({"independent": {"raised": 2, "converged": 1}, "second-family": {"raised": 1, "converged": 1}}, payload["lanes"])
        self.assertEqual([], payload["verify"])

    def test_single_source_majors_go_to_the_other_family_unless_settled(self) -> None:
        independent = lane_result(
            envelope("review.independent", "codex", "review", ["[major] app/a.py:10 x", "[major] app/b.py:4 y", "[minor] app/c.py:2 z"])
        )
        payload = merge([independent], TABLE, reproduced=["app/b.py:4"])
        self.assertEqual(
            [{"finding": "app/a.py:10", "lane": "independent", "route": "review", "provider": "claude", "family": "opus"}],
            payload["verify"],
        )
        self.assertEqual("accepted: reproduced or its locking assertion failed", payload["settled"][0]["outcome"])
        with_second = merge(
            [independent, lane_result(envelope("review.second-family", "claude", "review", []))], TABLE
        )
        self.assertEqual([], with_second["verify"])
        self.assertTrue(all("second family ran" in item["outcome"] for item in with_second["settled"]))
        demoted = merge([independent], TABLE, demoted=["verify-major"])
        self.assertEqual([], demoted["verify"])
        self.assertIn("low-yield-lane for independent", demoted["settled"][0]["outcome"])

    def test_one_family_moves_the_verifier_to_the_deep_route_or_caps(self) -> None:
        opus = lane_result(envelope("review.independent", "claude", "review", ["[major] app/a.py:1 x"]))
        moved = merge([opus], TABLE, reachable=["claude"])
        self.assertEqual(("deep-review", "claude", "fable"), (moved["verify"][0]["route"], moved["verify"][0]["provider"], moved["verify"][0]["family"]))
        fable = lane_result(envelope("review.independent", "claude", "deep-review", ["[major] app/a.py:1 x"]))
        capped = merge([fable], TABLE, reachable=["claude"])
        self.assertEqual([], capped["verify"])
        self.assertIn("single family", capped["settled"][0]["outcome"])

    def test_a_clean_whole_span_lane_must_cover_the_changed_files(self) -> None:
        required = [f"app/m{index}.py" for index in range(7)]
        clean = lane_result(envelope("review.independent", "codex", "review", [], [f"read {path}" for path in required[:4]]))
        lens = lane_result(envelope("review.deep-lenses", "codex", "deep-review", [], ["read app/m0.py"]), "adversarial")
        payload = merge([clean, lens], TABLE, coverage_required=required)
        self.assertEqual({"independent": required[4:]}, payload["coverage_rerun"])
        found = lane_result(envelope("review.independent", "codex", "review", ["[minor] app/m1.py:2 x"], []))
        self.assertEqual({}, merge([found], TABLE, coverage_required=required)["coverage_rerun"])

    def test_rejects_non_reviewer_and_unfinished_lanes(self) -> None:
        with self.assertRaisesRegex(ReviewPlanError, "verifier and delta results"):
            lane_result(envelope("review.verify-major", "claude", "review", []))
        failed = envelope("review.independent", "codex", "review", [])
        failed["result"]["status"] = "blocked"  # type: ignore[index]
        with self.assertRaisesRegex(ReviewPlanError, "did not complete"):
            lane_result(failed)
        with self.assertRaisesRegex(ReviewPlanError, "no worker result"):
            lane_result({**failed, "dry_run": True, "result": None})
        twice = lane_result(envelope("review.deep-lenses", "codex", "deep-review", []), "adversarial")
        with self.assertRaisesRegex(ReviewPlanError, "once"):
            merge([twice, twice], TABLE)


def metrics_event(**lanes: dict[str, int]) -> str:
    return json.dumps({"command": "review-code", "review": {"lanes": lanes}}) + "\n"


class LowYieldObservationTests(unittest.TestCase):
    def test_demotions_append_one_observation_each(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            demotion = Demotion("adversarial", LENS_WINDOW, LENS_WINDOW, {"raised": 8, "accepted": 0}, "opt-in only")
            self.assertEqual(["adversarial"], record_demotions(work, [demotion]))
            self.assertEqual([], record_demotions(work, [demotion]))
            changed = Demotion("adversarial", LENS_WINDOW, LENS_WINDOW, {"raised": 9, "accepted": 0}, "opt-in only")
            self.assertEqual(["adversarial"], record_demotions(work, [changed]))
            lines = [json.loads(line) for line in (work / ".ai-toolkit/observations.jsonl").read_text().splitlines()]
            self.assertEqual(["low-yield-lane", "low-yield-lane"], [line["kind"] for line in lines])
            self.assertEqual("review-code", lines[0]["workflow"])
            self.assertIn("adversarial below its yield threshold", lines[0]["detail"])

    def test_lane_yield_cli_queues_the_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            metrics = work / ".ai-toolkit" / "metrics.jsonl"
            metrics.parent.mkdir()
            metrics.write_text(metrics_event(delta={"not_fixed": 0}) * LANE_WINDOW)
            self.assertEqual(["delta"], [item.lane for item in evaluate([json.loads(line) for line in metrics.read_text().splitlines()])])
            run = subprocess.run(
                [str(ROOT / "bin/aitk"), "lane-yield", "--json"], cwd=work, text=True, capture_output=True, check=False
            )
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual(["delta"], json.loads(run.stdout)["observations"])
            again = subprocess.run(
                [str(ROOT / "bin/aitk"), "lane-yield", "--json"], cwd=work, text=True, capture_output=True, check=False
            )
            self.assertEqual([], json.loads(again.stdout)["observations"])


@unittest.skipUnless(shutil.which("git"), "git is required")
class ReviewCliTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.work)], check=True, env=ENVIRONMENT)
        (self.work / "a.py").write_text("x = 1\n")
        git(self.work, "add", "a.py")
        git(self.work, "commit", "-q", "-m", "base")
        (self.work / "a.py").write_text("x = 2\n")
        (self.work / "b.py").write_text("y = 1\n")

    def aitk(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "bin/aitk"), *arguments], cwd=self.work, text=True, capture_output=True, check=False, env=ENVIRONMENT
        )

    def test_plan_and_merge_round_trip(self) -> None:
        planned = self.aitk(
            "review", "plan", "--parent", "codex", "--complexity", "STANDARD", "--base", "HEAD",
            "--unreachable", "codex", "--unreachable", "claude", "--json",
        )
        self.assertEqual(3, planned.returncode, planned.stderr)
        payload = json.loads(planned.stdout)
        self.assertEqual(("BLOCKED", []), (payload["status"], payload["reachable"]))
        self.assertEqual(["a.py", "b.py"], payload["coverage"]["required"])
        self.assertEqual({"Backend": ["a.py", "b.py"]}, payload["classification"]["domains"])
        blocked = self.aitk(
            "review", "plan", "--parent", "claude", "--complexity", "STANDARD", "--base", "HEAD",
            "--unreachable", "codex", "--unreachable", "claude",
        )
        self.assertEqual(3, blocked.returncode)
        self.assertTrue(blocked.stdout.startswith("## Review Plan\nStatus: BLOCKED"), blocked.stdout)
        plan_file = self.work.parent / "plan.json"
        plan_file.write_text(json.dumps({**payload, "reachable": ["codex", "claude"]}))
        result = self.work.parent / "independent.json"
        result.write_text(json.dumps(envelope("review.independent", "codex", "review", [], ["read a.py"])))
        merged = self.aitk("review", "merge", "--plan", str(plan_file), "--result", str(result), "--json")
        self.assertEqual(0, merged.returncode, merged.stderr)
        self.assertEqual({"independent": ["b.py"]}, json.loads(merged.stdout)["coverage_rerun"])
        bad = self.aitk("review", "merge", "--plan", str(plan_file), "--result", str(self.work / "missing.json"))
        self.assertEqual(1, bad.returncode)
        self.assertIn("cannot read result", bad.stderr)

    def test_plan_needs_a_parent_outside_claude_code(self) -> None:
        env = {key: value for key, value in ENVIRONMENT.items() if key != "CLAUDECODE"}
        run = subprocess.run(
            [str(ROOT / "bin/aitk"), "review", "plan", "--complexity", "STANDARD", "--base", "HEAD"],
            cwd=self.work, text=True, capture_output=True, check=False, env=env,
        )
        self.assertEqual(1, run.returncode)
        self.assertIn("pass --parent", run.stderr)


if __name__ == "__main__":
    unittest.main()
