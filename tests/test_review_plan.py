"""`aitk review plan` and `review merge`: the deterministic half of a review.

Each `review plan` decision local-review.md and pr-review.md describe in prose
has a case here (bases, the second-family triggers, the coverage check, the
lens cap that keeps adversarial on a security-sensitive diff, the verifier
family, degraded handling, yield demotions, `--kind pr`), as do `review
merge`'s dedupe, convergence and verifier list, and the `low-yield-lane`
observation `lane-yield` appends, and the yield thresholds `lane-yield`
applies to the metrics file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from aitk.review_plan import (
    DEEP_LENSES,
    LANE_WINDOW,
    LENS_WINDOW,
    SECOND_FAMILY_CORE_LINES,
    ChangedFile,
    Demotion,
    PlanInputs,
    ReviewPlanError,
    branch_base,
    classify,
    core_paths,
    coverage_gaps,
    evaluate,
    excluded_reason,
    exception_refusal,
    families,
    is_toolkit_pr,
    is_toolkit_repository,
    lane_result,
    load_events,
    local_changes,
    merge,
    phase_base,
    plan,
    pr_changes,
    pr_metadata,
    record_demotions,
    render_plan,
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


GH_STUB = """#!{python}
import json, os, sys
directory = os.environ["GH_STUB_DIR"]
argv = sys.argv[1:]
with open(os.path.join(directory, "calls.jsonl"), "a") as log:
    log.write(json.dumps(argv) + "\\n")
config = json.load(open(os.path.join(directory, "config.json")))
if argv[:2] == ["pr", "view"]:
    key = "pr"
elif argv[:2] == ["api", "graphql"]:
    key = "graphql"
elif argv[:1] == ["api"]:
    key = "files"
else:
    sys.exit(2)
entry = config.get(key, {{"fail": "no stubbed response for " + key}})
if isinstance(entry, dict) and "fail" in entry:
    sys.stderr.write(entry["fail"])
    sys.exit(1)
print(entry["raw"] if isinstance(entry, dict) and "raw" in entry else json.dumps(entry))
"""
BASE_OID = "a" * 40


def pr_json(changed: int, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "title": "Refactor the loader",
        "number": 12,
        "url": "https://github.com/acme/widgets/pull/12",
        "baseRefName": "main",
        "baseRefOid": BASE_OID,
        "changedFiles": changed,
    }
    values.update(changes)
    return values


def rest(name: str, added: int = 0, deleted: int = 0, status: str = "modified", previous: str | None = None) -> dict[str, object]:
    entry: dict[str, object] = {"filename": name, "additions": added, "deletions": deleted, "status": status}
    if previous is not None:
        entry["previous_filename"] = previous
    return entry


def graphql_json(commit: str | None = "Commit", manifest: str | None = "Blob", package: str | None = "Tree") -> dict[str, object]:
    def node(name: str | None) -> dict[str, str] | None:
        return {"__typename": name} if name else None

    return {"data": {"repository": {"commit": node(commit), "manifest": node(manifest), "package": node(package)}}}


class GhStub:
    """An executable `gh` on PATH that answers by argv from a JSON file and logs every call."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory / "gh-stub"
        self.directory.mkdir()
        gh = self.directory / "gh"
        gh.write_text(GH_STUB.format(python=sys.executable))
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.env = {
            **ENVIRONMENT,
            "GH_STUB_DIR": str(self.directory),
            "PATH": f"{self.directory}{os.pathsep}{os.environ['PATH']}",
        }

    def configure(self, **config: object) -> None:
        (self.directory / "config.json").write_text(json.dumps(config))

    def calls(self) -> list[list[str]]:
        log = self.directory / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


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

    def test_core_paths_is_a_fact_on_every_changed_file(self) -> None:
        facts = classify([ChangedFile("poetry.lock", 0, 0, "renamed", old_path="app/auth.py"), ChangedFile("app/util.py", 1, 0)])
        self.assertEqual((1, 1), (facts["files"], facts["changed_lines"]))
        self.assertEqual({"poetry.lock": "lockfile"}, facts["excluded"])
        self.assertEqual(["app/auth.py"], facts["core_paths"])
        header = classify([ChangedFile("app/auth.py", 2, 0, generated_header=True)])
        self.assertEqual((0, 0), (header["files"], header["changed_lines"]))
        self.assertEqual(["app/auth.py"], header["core_paths"])

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

    def test_core_second_family_needs_forty_lines_or_a_core_path(self) -> None:
        self.assertEqual(40, SECOND_FAMILY_CORE_LINES)

        def core(changed: tuple[ChangedFile, ...], **more: object) -> dict[str, object]:
            return plan(inputs(impact="CORE", files=changed, **more), TABLE)

        small = core(files(1, lines=12))
        self.assertNotIn("second-family", lanes(small))
        self.assertEqual({"triggers": [], "note": "not required", "core_why": None}, small["second_family"])
        disclosure = "Second family: CORE impact not run (12 changed lines < 40, no auth, payment or data-integrity path)"
        self.assertIn(disclosure, small["disclosures"])
        self.assertIn(f"Disclosed: {disclosure}", render_plan(small))
        complex_small = core(files(1, lines=12), complexity="COMPLEX")
        self.assertEqual("COMPLEX", lanes(complex_small)["second-family"]["note"])
        self.assertEqual(["COMPLEX"], complex_small["second_family"]["triggers"])
        self.assertFalse([line for line in complex_small["disclosures"] if "CORE impact not run" in line])
        forty = core(files(2, lines=20))
        self.assertEqual("CORE (40 changed lines)", lanes(forty)["second-family"]["note"])
        self.assertEqual("40 changed lines", forty["second_family"]["core_why"])
        self.assertNotIn("second-family", lanes(core(files(2, lines=19))))
        both = core(files(2, lines=20), complexity="COMPLEX")
        self.assertEqual("COMPLEX and CORE (40 changed lines)", lanes(both)["second-family"]["note"])
        # A content header the diff author writes does not hide churn from the threshold.
        headed = core((ChangedFile("app/render.py", 300, 0, generated_header=True),))
        self.assertEqual(["CORE"], headed["second_family"]["triggers"])
        self.assertEqual("300 changed lines", headed["second_family"]["core_why"])
        self.assertNotIn("second-family", lanes(core((ChangedFile("app/render.min.js", 300, 0),))))

        auth, util = "app/auth.py", ChangedFile("app/util.py", 1, 0)
        paths = (
            ((ChangedFile("app/auth/login.py", 3, 1),), "app/auth/login.py", 4),
            ((ChangedFile("app/helpers.py", 0, 0, "renamed", old_path=auth),), auth, 0),
            ((ChangedFile("poetry.lock", 0, 0, "renamed", old_path=auth), util), auth, 1),
            ((ChangedFile("build/helpers.py", 0, 0, "renamed", old_path=auth), util), auth, 1),
            ((ChangedFile(auth, 2, 0, generated_header=True),), auth, 0),
            ((ChangedFile("app/auth/evil.min.js", 300, 0, "added"), util), "app/auth/evil.min.js", 1),
        )
        for changed, named, counted in paths:
            with self.subTest(named=named, files=[item.path for item in changed]):
                payload = core(changed)
                self.assertEqual(f"CORE (path {named})", lanes(payload)["second-family"]["note"])
                self.assertEqual(f"path {named}", payload["second_family"]["core_why"])
                self.assertEqual(counted, payload["classification"]["changed_lines"])

        toolkit_rename = (ChangedFile("uv.lock", 0, 0, "renamed", old_path="hooks/x.sh"),)
        for changed, name in ((toolkit_rename, "hooks/x.sh"), ((ChangedFile("hooks/x.sh", 2, 0),), "hooks/x.sh")):
            with self.subTest(toolkit=True, files=[item.path for item in changed]):
                self.assertEqual(f"CORE (path {name})", lanes(core(changed, toolkit=True))["second-family"]["note"])
                self.assertNotIn("second-family", lanes(core(changed, toolkit=False)))
        self.assertNotIn("second-family", lanes(core((ChangedFile("components/Chart.tsx", 10, 5),))))

        demoted = core(files(1, lines=12), demoted=frozenset({"second-family"}))
        self.assertIn(disclosure, demoted["disclosures"])
        self.assertNotIn("Second family: CORE trigger dropped (low yield; COMPLEX only)", demoted["disclosures"])

    def test_core_paths_match_auth_payment_and_data_integrity_segments(self) -> None:
        def hits(*changed: ChangedFile, toolkit: bool = False) -> list[str]:
            return core_paths(changed, toolkit)

        for path in (
            "app/auth/login.py", "billing/invoice.py", "db/migrations/0001.py", "app/models.py",
            "app/models/user.py", "src/db.ts", "api/schema.graphql", "app/checkout/cart.tsx",
        ):
            with self.subTest(positive=path):
                self.assertEqual([path], hits(ChangedFile(path, 1, 0)))
        for path in (
            "components/Chart.tsx", "README.md", "app/views/dashboard.py", "feedback/views.py",
            "adb/tool.py", "ml/model_training.py", "interfaces/model-routing.json",
        ):
            with self.subTest(negative=path):
                self.assertEqual([], hits(ChangedFile(path, 1, 0)))
        self.assertEqual(["billing/poetry.lock"], hits(ChangedFile("billing/poetry.lock", 5, 5)))
        self.assertEqual(
            ["app/auth.py"], hits(ChangedFile("app/helpers.py", 0, 0, "renamed", old_path="app/auth.py"))
        )
        self.assertEqual(
            ["app/auth/login.py"], hits(ChangedFile("app/auth/login.py", 0, 0, "renamed", old_path="app/entry.py"))
        )
        self.assertEqual(
            ["app/auth/login.py", "app/login.py"],
            hits(ChangedFile("app/auth/login.py", 0, 0, "renamed", old_path="app/login.py")),
        )
        self.assertEqual([], hits(ChangedFile("app/b.py", 0, 0, "renamed", old_path="app/a.py")))
        for destination in ("poetry.lock", "build/helpers.py"):
            with self.subTest(destination=destination):
                self.assertEqual(
                    ["app/auth.py"], hits(ChangedFile(destination, 0, 0, "renamed", old_path="app/auth.py"))
                )
        self.assertEqual(
            ["app/auth.generated.py", "app/auth.py"],
            hits(ChangedFile("app/auth.generated.py", 0, 0, "renamed", old_path="app/auth.py")),
        )
        self.assertEqual(["app/auth.py"], hits(ChangedFile("app/auth.py", 2, 0, generated_header=True)))
        self.assertEqual(
            ["app/auth/new.py"], hits(ChangedFile("app/auth/new.py", 40, 0, "added", generated_header=True))
        )
        self.assertEqual(["app/auth.py"], hits(ChangedFile("app/auth.py", 0, 80, "deleted")))
        self.assertEqual(["app/auth/key.bin"], hits(ChangedFile("app/auth/key.bin", 0, 0, "added", binary=True)))
        self.assertEqual(["app/auth/evil.min.js"], hits(ChangedFile("app/auth/evil.min.js", 300, 0, "added")))
        for change, named in (
            (ChangedFile("scripts/x.sh", 0, 0, "renamed", old_path="hooks/x.sh"), "hooks/x.sh"),
            (ChangedFile("uv.lock", 0, 0, "renamed", old_path="hooks/x.sh"), "hooks/x.sh"),
            (ChangedFile("hooks/x.sh", 2, 0, generated_header=True), "hooks/x.sh"),
            (ChangedFile("agents/claude/aitk-planner.md", 5, 5, generated_header=True), "agents/claude/aitk-planner.md"),
        ):
            with self.subTest(toolkit=named, path=change.path):
                self.assertEqual([named], hits(change, toolkit=True))
                self.assertEqual([], hits(change, toolkit=False))

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
        auth = plan(inputs(complexity="TRIVIAL", files=(ChangedFile("app/auth.py", 2, 0),)), TABLE)
        self.assertFalse(auth["exception_available"])
        self.assertEqual("STANDARD", auth["impact"])
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


class ReviewExceptionTests(unittest.TestCase):
    def refusal(self, kind: str, *changed: ChangedFile, toolkit: bool = False) -> str | None:
        return exception_refusal(kind, changed, toolkit=toolkit)

    def both_refuse(self, text: str, *changed: ChangedFile, toolkit: bool = False) -> None:
        for kind in ("micro-fix", "zero-logic"):
            with self.subTest(kind=kind, files=[item.path for item in changed]):
                self.assertIn(text, self.refusal(kind, *changed, toolkit=toolkit) or "")

    def test_micro_fix_is_one_file_of_ten_lines_or_fewer(self) -> None:
        self.assertIsNone(self.refusal("micro-fix", ChangedFile("app/a.py", 6, 4)))
        self.assertIn("at most 10 changed lines; app/a.py has 11", self.refusal("micro-fix", ChangedFile("app/a.py", 6, 5)))
        two = self.refusal("micro-fix", ChangedFile("app/a.py", 1, 0), ChangedFile("app/b.py", 1, 0))
        self.assertIn("exactly one changed file; this diff has 2: app/a.py, app/b.py", two)
        self.assertIsNone(self.refusal("micro-fix", ChangedFile("app/a.py", 1, 0), ChangedFile("poetry.lock", 90, 90)))
        self.assertIn("binary", self.refusal("micro-fix", ChangedFile("app/a.bin", 0, 0, "modified", binary=True)))
        self.assertIsNone(self.refusal("zero-logic", *files(3, lines=100)))
        self.assertIsNone(self.refusal("micro-fix", ChangedFile("app/b.py", 0, 0, "renamed", old_path="app/a.py")))

    def test_an_empty_diff_or_only_lockfiles_has_nothing_to_except(self) -> None:
        for kind in ("micro-fix", "zero-logic"):
            self.assertIn("nothing to except", self.refusal(kind) or "")
            self.assertIn("nothing to except", self.refusal(kind, ChangedFile("poetry.lock", 50, 50)) or "")

    def test_a_core_path_is_refused_whatever_its_name_or_header(self) -> None:
        self.both_refuse("CORE path", ChangedFile("app/auth.py", 2, 0))
        self.both_refuse(
            "CORE path (app/auth.py)", ChangedFile("app/helpers.py", 0, 0, "renamed", old_path="app/auth.py")
        )
        util = ChangedFile("app/util.py", 1, 0)
        self.both_refuse(
            "CORE path (app/auth.py)", ChangedFile("poetry.lock", 0, 0, "renamed", old_path="app/auth.py"), util
        )
        self.both_refuse(
            "CORE path (app/auth.py)", ChangedFile("build/helpers.py", 0, 0, "renamed", old_path="app/auth.py"), util
        )
        self.both_refuse("CORE path (app/auth.py)", ChangedFile("app/auth.py", 2, 0, generated_header=True))
        self.both_refuse("CORE path (billing/poetry.lock)", ChangedFile("billing/poetry.lock", 5, 5))
        self.both_refuse("CORE path (app/auth/evil.min.js)", ChangedFile("app/auth/evil.min.js", 300, 0, "added"), util)
        self.assertNotIn("nothing to except", self.refusal("micro-fix", ChangedFile("billing/poetry.lock", 5, 5)))

    def test_toolkit_endpoints_are_refused_only_in_the_toolkit(self) -> None:
        for change, named in (
            (ChangedFile("hooks/x.sh", 2, 0), "hooks/x.sh"),
            (ChangedFile("scripts/x.sh", 0, 0, "renamed", old_path="hooks/x.sh"), "hooks/x.sh"),
            (ChangedFile("uv.lock", 0, 0, "renamed", old_path="hooks/x.sh"), "hooks/x.sh"),
            (ChangedFile("hooks/x.sh", 2, 0, generated_header=True), "hooks/x.sh"),
        ):
            for kind in ("micro-fix", "zero-logic"):
                with self.subTest(kind=kind, path=change.path):
                    self.assertIn(f"CORE path ({named})", self.refusal(kind, change, toolkit=True) or "")
                    self.assertIsNone(self.refusal(kind, change, toolkit=False))

    def test_the_count_ignores_the_header_and_keeps_a_non_excluded_source(self) -> None:
        util = ChangedFile("app/util.py", 1, 0)
        moved = ChangedFile("build/x.py", 0, 0, "renamed", old_path="app/views/x.py")
        self.assertIn("exactly one changed file; this diff has 2", self.refusal("micro-fix", moved, util) or "")
        self.assertIsNone(self.refusal("zero-logic", moved, util))
        big = ChangedFile("app/views/big.py", 500, 0, generated_header=True)
        self.assertIn("this diff has 2", self.refusal("micro-fix", big, util) or "")
        self.assertIn("app/views/big.py has 500", self.refusal("micro-fix", big) or "")
        self.assertIsNone(self.refusal("zero-logic", big))


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

    def test_a_rename_into_an_excluded_name_keeps_its_source(self) -> None:
        git(self.repo, "mv", "app/old.py", "poetry.lock")
        changes = {item.path: item for item in local_changes(self.repo, self.base)}
        self.assertEqual("app/old.py", changes["poetry.lock"].old_path)
        self.assertEqual("renamed", changes["poetry.lock"].status)
        self.assertEqual("lockfile", excluded_reason(changes["poetry.lock"]))


def toolkit_repository(parent: Path, name: str = "toolkit") -> tuple[Path, str]:
    """A repository with a committed routing manifest and `aitk/`; returns it and its `git write-tree` SHA."""
    repo = parent / name
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=ENVIRONMENT)
    (repo / "interfaces").mkdir()
    (repo / "interfaces/model-routing.json").write_text('{"routes": []}\n' * 20)
    (repo / "aitk").mkdir()
    (repo / "aitk/__init__.py").write_text("")
    (repo / "hooks").mkdir()
    (repo / "hooks/x.sh").write_text("echo x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "toolkit")
    return repo, git(repo, "write-tree")


class ToolkitIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()

    def lane_note(self, repo: Path, base: str) -> str | None:
        changed = local_changes(repo, base)
        toolkit = is_toolkit_repository(repo, base, files=changed)
        payload = plan(inputs(impact="CORE", files=tuple(changed), toolkit=toolkit), TABLE)
        self.assertLess(payload["classification"]["changed_lines"], 40)
        return lanes(payload).get("second-family", {}).get("note")  # type: ignore[return-value]

    def test_toolkit_identity_survives_sentinel_changes(self) -> None:
        manifest = "interfaces/model-routing.json"
        expected = f"CORE (path {manifest})"
        repo, _tree = toolkit_repository(self.parent, "rename")
        (repo / "build").mkdir()
        git(repo, "mv", manifest, "build/model-routing.json")
        self.assertFalse((repo / manifest).exists())
        self.assertTrue(is_toolkit_repository(repo, "HEAD", files=local_changes(repo, "HEAD")))
        self.assertEqual(expected, self.lane_note(repo, "HEAD"))

        repo, _tree = toolkit_repository(self.parent, "deleted")
        git(repo, "rm", "-q", manifest)
        self.assertTrue(is_toolkit_repository(repo, "HEAD", files=local_changes(repo, "HEAD")))
        self.assertEqual(expected, self.lane_note(repo, "HEAD"))

        repo, _tree = toolkit_repository(self.parent, "both")
        shutil.rmtree(repo / "aitk")
        shutil.rmtree(repo / "interfaces")
        self.assertTrue(is_toolkit_repository(repo, "HEAD"))
        self.assertEqual(expected, self.lane_note(repo, "HEAD"))

        # HEAD no longer has the sentinels; only the earlier base does, and a
        # `git write-tree` SHA (what phase_base supplies) is a tree, not a commit.
        repo, tree = toolkit_repository(self.parent, "committed")
        commit = git(repo, "rev-parse", "HEAD")
        git(repo, "rm", "-q", "-r", manifest, "aitk")
        git(repo, "commit", "-q", "-m", "remove the sentinels")
        self.assertFalse(is_toolkit_repository(repo, "HEAD"))
        self.assertFalse(is_toolkit_repository(repo))
        self.assertTrue(is_toolkit_repository(repo, tree))
        self.assertTrue(is_toolkit_repository(repo, commit))
        self.assertEqual(f"CORE (path {manifest})", self.lane_note(repo, tree))

    def test_identity_reads_origin_when_the_short_base_has_no_local_ref(self) -> None:
        repo, _tree = toolkit_repository(self.parent, "remote-only")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(repo, "checkout", "-q", "-b", "work")
        git(repo, "rm", "-q", "-r", "interfaces/model-routing.json", "aitk")
        git(repo, "commit", "-q", "-m", "remove the sentinels")
        git(repo, "branch", "-q", "-D", "main")
        self.assertFalse(is_toolkit_repository(repo, "HEAD"))
        self.assertTrue(is_toolkit_repository(repo, "main"))

    def test_a_normal_repository_and_an_unresolvable_base_are_not_the_toolkit(self) -> None:
        repo = self.parent / "plain"
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=ENVIRONMENT)
        (repo / "app.py").write_text("x = 1\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        self.assertFalse(is_toolkit_repository(repo, "main", files=local_changes(repo, "main")))
        self.assertFalse(is_toolkit_repository(repo, "no-such-base"))
        self.assertFalse(is_toolkit_repository(None, "main"))
        moved = ChangedFile("build/model-routing.json", 0, 0, "renamed", old_path="interfaces/model-routing.json")
        self.assertTrue(is_toolkit_repository(repo, "main", files=[moved]))
        toolkit, _tree = toolkit_repository(self.parent)
        self.assertTrue(is_toolkit_repository(toolkit, "no-such-base"))


class PrCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cwd = self.root / "checkout"
        self.cwd.mkdir()
        self.gh = GhStub(self.root)

    def collect(self, reference: str = "12") -> tuple[list[ChangedFile], str, str]:
        return pr_changes(self.cwd, reference, self.gh.env)

    def test_pr_changes_read_metadata_and_paginated_rest_files(self) -> None:
        pages = [
            [rest("app/b.py", 3, 1), rest("app/new.py", 5, 0, "added")],
            [
                rest("app/gone.py", 0, 9, "removed"),
                rest("poetry.lock", 0, 0, "renamed", "app/auth.py"),
                rest("app/copy.py", 2, 0, "copied", "app/b.py"),
                rest("app/c.py", 1, 1, "changed"),
                rest("app/d.py", 0, 0, "unchanged"),
            ],
        ]
        self.gh.configure(pr=pr_json(7), files=pages)
        changed, title, base = self.collect("12")
        self.assertEqual(("Refactor the loader", "main"), (title, base))
        self.assertEqual(
            [
                ChangedFile("app/b.py", 3, 1, "modified"),
                ChangedFile("app/c.py", 1, 1, "modified"),
                ChangedFile("app/copy.py", 2, 0, "added"),
                ChangedFile("app/d.py", 0, 0, "modified"),
                ChangedFile("app/gone.py", 0, 9, "deleted"),
                ChangedFile("app/new.py", 5, 0, "added"),
                ChangedFile("poetry.lock", 0, 0, "renamed", False, "app/auth.py"),
            ],
            changed,
        )
        view, listing = self.gh.calls()
        self.assertEqual(
            ["pr", "view", "12", "--json", "title,number,url,baseRefName,baseRefOid,changedFiles"], view
        )
        self.assertEqual(
            ["api", "--hostname", "github.com", "--paginate", "--slurp", "repos/acme/widgets/pulls/12/files?per_page=100"],
            listing,
        )

    def test_numeric_url_and_branch_references_use_the_resolved_identity(self) -> None:
        self.gh.configure(
            pr=pr_json(1, number=99, url="https://ghe.example.com/org/repo/pull/99", baseRefName="release"),
            files=[[rest("app/a.py", 1, 0)]],
        )
        for reference in ("99", "https://ghe.example.com/org/repo/pull/99", "feature/x"):
            with self.subTest(reference=reference):
                (self.gh.directory / "calls.jsonl").unlink(missing_ok=True)
                self.assertEqual(([ChangedFile("app/a.py", 1, 0)], "Refactor the loader", "release"), self.collect(reference))
                view, listing = self.gh.calls()
                self.assertEqual(reference, view[2])
                self.assertEqual("ghe.example.com", listing[listing.index("--hostname") + 1])
                self.assertEqual("repos/org/repo/pulls/99/files?per_page=100", listing[-1])
        metadata = pr_metadata(self.cwd, "feature/x", self.gh.env)
        (self.gh.directory / "calls.jsonl").unlink()
        pr_changes(self.cwd, "feature/x", self.gh.env, metadata=metadata)
        self.assertEqual(["api"], [call[0] for call in self.gh.calls()])

    def test_pr_rename_from_auth_to_an_excluded_destination_keeps_the_core_lane(self) -> None:
        for destination in ("poetry.lock", "build/helpers.py"):
            with self.subTest(destination=destination):
                self.gh.configure(
                    pr=pr_json(2), files=[[rest(destination, 0, 0, "renamed", "app/auth.py"), rest("app/util.py", 1, 0)]]
                )
                changed, _title, _base = self.collect()
                moved = next(item for item in changed if item.path == destination)
                self.assertEqual(("renamed", "app/auth.py"), (moved.status, moved.old_path))
                payload = plan(inputs(kind="pr", impact="CORE", files=tuple(changed)), TABLE)
                self.assertEqual(1, payload["classification"]["changed_lines"])
                self.assertEqual(["app/auth.py"], payload["classification"]["core_paths"])
                self.assertEqual("CORE (path app/auth.py)", lanes(payload)["second-family"]["note"])
                self.assertEqual("review.pr-second-family", lanes(payload)["second-family"]["boundary"])

    def test_pr_toolkit_identity_uses_the_immutable_base(self) -> None:
        metadata = pr_metadata_for(self, 1)
        unrelated = self.root / "elsewhere"
        unrelated.mkdir()
        sentinels_intact = (ChangedFile("hooks/x.sh", 2, 0),)
        self.gh.configure(graphql=graphql_json())
        (self.gh.directory / "calls.jsonl").unlink()
        self.assertTrue(is_toolkit_pr(unrelated, metadata, files=sentinels_intact, env=self.gh.env))
        (call,) = self.gh.calls()
        self.assertEqual(["api", "graphql", "--hostname", "github.com"], call[:4])
        pairs = {call[index + 1].split("=", 1)[0]: call[index + 1].split("=", 1)[1] for index in range(len(call)) if call[index] == "-f"}
        self.assertEqual(BASE_OID, pairs["oid"])
        self.assertEqual(f"{BASE_OID}:interfaces/model-routing.json", pairs["manifest"])
        self.assertEqual(f"{BASE_OID}:aitk", pairs["package"])
        self.assertEqual(("acme", "widgets"), (pairs["owner"], pairs["name"]))
        self.assertNotIn("main", pairs.values())
        payload = plan(inputs(kind="pr", impact="CORE", files=sentinels_intact, toolkit=True), TABLE)
        self.assertEqual("CORE (path hooks/x.sh)", lanes(payload)["second-family"]["note"])
        # A changed manifest endpoint is evidence on its own: no lookup is made.
        (self.gh.directory / "calls.jsonl").unlink()
        self.gh.configure()
        for moved in (
            ChangedFile("build/model-routing.json", 0, 0, "renamed", old_path="interfaces/model-routing.json"),
            ChangedFile("interfaces/model-routing.json", 0, 20, "deleted"),
        ):
            self.assertTrue(is_toolkit_pr(unrelated, metadata, files=(moved,), env=self.gh.env))
        self.assertEqual([], self.gh.calls())
        # A non-toolkit base, or one missing either sentinel, is not the toolkit.
        for response in (graphql_json(manifest=None, package=None), graphql_json(package=None), graphql_json(manifest=None)):
            self.gh.configure(graphql=response)
            self.assertFalse(is_toolkit_pr(self.cwd, metadata, files=sentinels_intact, env=self.gh.env))
        absent = plan(inputs(kind="pr", impact="CORE", files=sentinels_intact, toolkit=False), TABLE)
        self.assertNotIn("second-family", lanes(absent))

    def test_pr_collection_and_identity_fail_closed(self) -> None:
        good_pages = [[rest("app/a.py", 1, 0), rest("app/b.py", 1, 0)], [rest("poetry.lock", 0, 0, "renamed", "app/auth.py")]]
        self.gh.configure(pr=pr_json(3), files=good_pages)
        self.assertEqual(3, len(self.collect()[0]))
        cases = {
            "pr view fails": {"pr": {"fail": "boom"}, "files": good_pages},
            "metadata not json": {"pr": {"raw": "not json"}, "files": good_pages},
            "metadata not an object": {"pr": [1], "files": good_pages},
            "metadata without a base oid": {"pr": {k: v for k, v in pr_json(3).items() if k != "baseRefOid"}, "files": good_pages},
            "metadata with a short oid": {"pr": pr_json(3, baseRefOid="abc"), "files": good_pages},
            "metadata url not a pull": {"pr": pr_json(3, url="https://github.com/acme/widgets/issues/12"), "files": good_pages},
            "metadata number differs from the url": {"pr": pr_json(3, number=13), "files": good_pages},
            "metadata count not an integer": {"pr": pr_json("3"), "files": good_pages},
            "files fail": {"pr": pr_json(3), "files": {"fail": "HTTP 403"}},
            "files not json": {"pr": pr_json(3), "files": {"raw": "<html>"}},
            "files not a list of pages": {"pr": pr_json(3), "files": {"message": "x"}},
            "a page is not a list": {"pr": pr_json(3), "files": [{"a": 1}]},
            "an entry is not an object": {"pr": pr_json(3), "files": [["app/a.py"]]},
            "an entry has no filename": {"pr": pr_json(1), "files": [[{"additions": 1, "deletions": 0, "status": "added"}]]},
            "an entry has a bad count": {"pr": pr_json(1), "files": [[rest("app/a.py", -1, 0)]]},
            "an unknown status": {"pr": pr_json(1), "files": [[rest("app/a.py", 1, 0, "teleported")]]},
            "a rename without its source": {"pr": pr_json(1), "files": [[rest("poetry.lock", 0, 0, "renamed")]]},
            "a rename with an empty source": {"pr": pr_json(1), "files": [[rest("poetry.lock", 0, 0, "renamed", "")]]},
            "duplicate destinations": {"pr": pr_json(2), "files": [[rest("app/a.py", 1, 0), rest("app/a.py", 2, 0)]]},
            "fewer files than the PR changes": {"pr": pr_json(4), "files": good_pages},
            "only the pages before the rename": {"pr": pr_json(3), "files": good_pages[:1]},
            "more files than the PR changes": {"pr": pr_json(2), "files": good_pages},
        }
        for name, config in cases.items():
            with self.subTest(name):
                self.gh.configure(**config)
                with self.assertRaises(ReviewPlanError):
                    self.collect()
        metadata = pr_metadata_for(self, 3)
        identity = {
            "command failure": {"fail": "HTTP 502"},
            "not json": {"raw": "nope"},
            "graphql errors": {"errors": [{"message": "boom"}], "data": None},
            "no repository": {"data": {"repository": None}},
            "missing base commit": graphql_json(commit=None),
            "a manifest that is not an object": {"data": {"repository": {"commit": {"__typename": "Commit"}, "manifest": "Blob", "package": None}}},
            "a missing alias": {"data": {"repository": {"commit": {"__typename": "Commit"}, "manifest": None}}},
            "no data": {},
        }
        for name, response in identity.items():
            with self.subTest(identity=name):
                self.gh.configure(graphql=response)
                with self.assertRaises(ReviewPlanError):
                    is_toolkit_pr(self.cwd, metadata, files=[ChangedFile("hooks/x.sh", 1, 0)], env=self.gh.env)


def pr_metadata_for(case: PrCollectionTests, changed: int):  # type: ignore[no-untyped-def]
    case.gh.configure(pr=pr_json(changed))
    return pr_metadata(case.cwd, "12", case.gh.env)


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

    def test_pr_plan_keeps_protected_rename_endpoints_and_toolkit_identity(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        gh = GhStub(Path(temporary.name))
        util = rest("app/util.py", 1, 0)
        manifest = "interfaces/model-routing.json"
        plain = graphql_json(manifest=None, package=None)
        cases = (
            ("auth to a lockfile", [rest("poetry.lock", 0, 0, "renamed", "app/auth.py"), util], plain, "app/auth.py", 1),
            ("auth to build", [rest("build/helpers.py", 0, 0, "renamed", "app/auth.py"), util], plain, "app/auth.py", 1),
            ("manifest renamed", [rest("build/model-routing.json", 0, 0, "renamed", manifest), util], None, manifest, 1),
            ("manifest deleted", [rest(manifest, 0, 12, "removed"), util], None, manifest, 13),
            ("toolkit base", [rest("hooks/x.sh", 2, 0)], graphql_json(), "hooks/x.sh", 2),
            ("other base", [rest("hooks/x.sh", 2, 0)], plain, None, 2),
        )
        for name, listing, identity, named, counted in cases:
            with self.subTest(name):
                (gh.directory / "calls.jsonl").unlink(missing_ok=True)
                # A changed manifest endpoint needs no base lookup: a lookup would fail the plan.
                lookup = identity or {"fail": "no base lookup expected"}
                gh.configure(pr=pr_json(len(listing)), files=[listing], graphql=lookup)
                run = subprocess.run(
                    [
                        str(ROOT / "bin/aitk"), "review", "plan", "--kind", "pr", "--pr", "12", "--parent", "claude",
                        "--complexity", "STANDARD", "--impact", "CORE", "--unreachable", "codex",
                        "--unreachable", "claude", "--json",
                    ],
                    cwd=self.work, text=True, capture_output=True, check=False, env=gh.env,
                )
                self.assertEqual(3, run.returncode, run.stderr)
                payload = json.loads(run.stdout)
                self.assertEqual(counted, payload["classification"]["changed_lines"])
                second = payload["second_family"]
                if named:
                    self.assertEqual(["CORE"], second["triggers"])
                    self.assertEqual(f"path {named}", second["core_why"])
                    self.assertIn(named, payload["classification"]["core_paths"])
                else:
                    self.assertEqual(([], None, []), (second["triggers"], second["core_why"], payload["classification"]["core_paths"]))
                    self.assertTrue(any("CORE impact not run" in line for line in payload["disclosures"]))
                # Metadata is resolved once and reused for files and identity.
                calls = gh.calls()
                self.assertEqual(1, sum(call[:2] == ["pr", "view"] for call in calls))
                self.assertEqual(1, sum(call[:1] == ["api"] and "graphql" not in call for call in calls))
                self.assertEqual(0 if identity is None else 1, sum(call[:2] == ["api", "graphql"] for call in calls))

    def test_plan_needs_a_parent_outside_claude_code(self) -> None:
        env = {key: value for key, value in ENVIRONMENT.items() if key != "CLAUDECODE"}
        run = subprocess.run(
            [str(ROOT / "bin/aitk"), "review", "plan", "--complexity", "STANDARD", "--base", "HEAD"],
            cwd=self.work, text=True, capture_output=True, check=False, env=env,
        )
        self.assertEqual(1, run.returncode)
        self.assertIn("pass --parent", run.stderr)



def event(**lanes: dict[str, int]) -> dict[str, object]:
    return {"command": "review-code", "review": {"lanes": lanes}}


class LaneYieldTests(unittest.TestCase):
    def test_lanes_below_their_window_are_not_judged(self) -> None:
        events = [event(adversarial={"raised": 3, "accepted": 0})] * (LENS_WINDOW - 1)
        events += [event(**{"second-family": {"raised": 2, "accepted": 0}})] * (LANE_WINDOW - 1)
        self.assertEqual([], evaluate(events))

    def test_deep_lens_is_demoted_on_low_yield_and_independent_never_is(self) -> None:
        low = [event(adversarial={"raised": 4, "accepted": 0}, independent={"raised": 1, "accepted": 0})]
        demotions = evaluate(low * LENS_WINDOW + [event(independent={"raised": 0, "accepted": 0})] * LANE_WINDOW)
        self.assertEqual(["adversarial"], [item.lane for item in demotions])
        self.assertEqual({"raised": 20, "accepted": 0}, demotions[0].observed)
        # One accepted in four raised keeps the lens: the threshold is "fewer than".
        healthy = [event(**{"lenses/deep-quality.md": {"raised": 4, "accepted": 1}})] * LENS_WINDOW
        self.assertEqual([], evaluate(healthy))
        for lens in DEEP_LENSES:
            self.assertIn(lens, ("adversarial", "deep-quality", "architecture"))

    def test_second_family_verifier_and_delta_apply_their_own_thresholds(self) -> None:
        idle = event(
            **{
                "second-family": {"raised": 3, "accepted": 3, "converged": 3, "refuted": 0},
                "verify-major": {"confirmed": 0, "refuted": 1},
                "delta": {"not_fixed": 0, "introduced": 0},
            }
        )
        demoted = {item.lane: item for item in evaluate([idle] * LANE_WINDOW)}
        self.assertEqual({"second-family", "verify-major", "delta"}, set(demoted))
        self.assertIn("COMPLEX only", demoted["second-family"].consequence)
        self.assertIn("[minor]", demoted["verify-major"].consequence)
        self.assertIn("[major] fix", demoted["delta"].consequence)
        earning = event(
            **{
                "second-family": {"raised": 2, "accepted": 1, "converged": 0},
                "verify-major": {"confirmed": 1},
                "delta": {"not_fixed": 1},
            }
        )
        # Only the most recent window counts, so one good run inside it clears
        # the second family and the delta lane; the verifier is judged on the
        # rate over what it verified, so one confirmed against nine refuted
        # still demotes and three in ten does not.
        self.assertEqual(
            ["verify-major"],
            [item.lane for item in evaluate([idle] * (LANE_WINDOW - 1) + [earning])],
        )
        self.assertEqual([], evaluate([idle] * (LANE_WINDOW - 3) + [earning] * 3))
        # A rate, not a count: one confirmed and nothing refuted is a perfect
        # record, and a window that verified nothing is not judged at all.
        quiet = event(**{"verify-major": {"confirmed": 0, "refuted": 0}})
        self.assertEqual([], evaluate([quiet] * (LANE_WINDOW - 1) + [earning]))
        self.assertEqual([], evaluate([quiet] * LANE_WINDOW))

    def test_malformed_lines_and_missing_file_read_as_no_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metrics.jsonl"
            self.assertEqual([], load_events(path))
            path.write_text('not json\n[1,2]\n{"review": {"lanes": "bad"}}\n' + json.dumps(event(delta={"not_fixed": "x"})) + "\n")
            events = load_events(path)
            self.assertEqual(2, len(events))
            self.assertEqual([], evaluate(events))

    def test_cli_reports_demotions_as_json_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary).resolve()
            metrics = cwd / ".ai-toolkit" / "metrics.jsonl"
            metrics.parent.mkdir()
            metrics.write_text("".join(json.dumps(event(architecture={"raised": 2, "accepted": 0})) + "\n" for _ in range(LENS_WINDOW)))
            # Run the module through this interpreter: a pinned PATH would pick the
            # system python3 on macOS, which bin/aitk rightly refuses.
            base = [sys.executable, "-m", "aitk.cli", "--root", str(ROOT), "lane-yield"]
            env = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}
            as_json = subprocess.run(base + ["--json"], cwd=cwd, text=True, capture_output=True, check=False, env=env)
            self.assertEqual(0, as_json.returncode, as_json.stderr)
            payload = json.loads(as_json.stdout)
            self.assertEqual(str(metrics), payload["metrics"])
            self.assertEqual(["architecture"], [item["lane"] for item in payload["demotions"]])
            as_text = subprocess.run(base, cwd=cwd, text=True, capture_output=True, check=False, env=env)
            self.assertEqual(0, as_text.returncode, as_text.stderr)
            self.assertIn("architecture: demoted over last 5 runs (raised=10, accepted=0)", as_text.stdout)
            empty = subprocess.run(base + ["--metrics", str(cwd / "missing.jsonl")], cwd=cwd, text=True, capture_output=True, check=False, env=env)
            self.assertEqual(0, empty.returncode, empty.stderr)
            self.assertIn("no lane below its yield threshold", empty.stdout)


if __name__ == "__main__":
    unittest.main()
