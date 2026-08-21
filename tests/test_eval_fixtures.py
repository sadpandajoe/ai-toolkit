"""Validation harness for the model-evaluation fixture corpus.

Corpus and schema are specified in PLAN.md's "Evaluation gate" section
(Sequencing step 2a). Two fixture types, each with its own manifest shape,
a two-tier committed result-record schema (per-trial + per-condition
aggregate), and eight structural checks enforced here.

Deviation from PLAN.md's literal text, recorded per PLAN.md's own
instruction to record deviations rather than apply them silently: check (5)
("at least 3 trial records per condition") is enforced only for a
condition/provider lane that has *any* captured trial record. A lane with
zero captured records is "authored, not yet captured" (this is exactly
step 2a's state — schema-and-harness, no live calls) and passes; a lane
with 1-2 records fails loudly, matching the check's own stated rationale
("so a partially-captured fixture fails loudly"). The same treatment
applies to the pairing check (2): it is vacuously satisfied when both
`runs/` and `results/` are empty.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = ROOT / "tests" / "fixtures" / "eval-baselines"

# Boundaries whose dispatch_boundaries entry declares a non-empty `lenses`
# menu (interfaces/model-routing.json) — the only boundaries whose
# `routed_boundary` manifests carry a non-null `lens` field and whose
# directories are held to check (8)'s checklist.md identity requirement.
FAN_OUT_BOUNDARIES = {"review.pr-lenses"}

VALID_PROVIDERS = {"claude", "codex"}

ROUTED_MANIFEST_REQUIRED = {
    "boundary",
    "route",
    "provider",
    "model_selector",
    "cli_version",
    "effort_level",
}
SCENARIO_MANIFEST_REQUIRED = {"scenario", "providers", "cli_version"}
SCENARIO_MANIFEST_FORBIDDEN = {"route", "model_selector", "lens"}

PER_TRIAL_REQUIRED = {
    "boundary",
    "scenario",
    "route",
    "provider",
    "model_selector",
    "lens",
    "condition",
    "trial",
    "effort_level",
    "checklist_or_rubric_result",
}
AGGREGATE_REQUIRED = {
    "boundary",
    "scenario",
    "route",
    "provider",
    "model_selector",
    "lens",
    "condition",
    "effort_level",
    "trial_count",
    "verdict",
    "per_trial",
}

# Filenames match from the right: the suffix (``-trial-NN.json``,
# ``-aggregate.json``, or the bare run extension) is a fixed literal, so a
# greedy ``.+`` for the leading `condition` (which may itself contain
# hyphens, e.g. "after-item4") still resolves correctly.
ROUTED_TRIAL_RE = re.compile(r"^(?P<condition>.+)-trial-(?P<nn>\d+)\.json$")
ROUTED_AGGREGATE_RE = re.compile(r"^(?P<condition>.+)-aggregate\.json$")
ROUTED_RUN_RE = re.compile(r"^(?P<condition>.+)-(?P<nn>\d+)\.json$")

SCENARIO_TRIAL_RE = re.compile(
    r"^(?P<condition>.+)-(?P<provider>claude|codex)-trial-(?P<nn>\d+)\.json$"
)
SCENARIO_AGGREGATE_RE = re.compile(
    r"^(?P<condition>.+)-(?P<provider>claude|codex)-aggregate\.json$"
)
SCENARIO_RUN_RE = re.compile(
    r"^(?P<condition>.+)-(?P<provider>claude|codex)-(?P<nn>\d+)\.md$"
)
LAST_MD_RE = re.compile(r".*-last\.md$")


def hash_dir(path: Path) -> str:
    """Sorted relative paths + contents, so directory identity checks (6)-(8)
    are order-independent and catch any content or filename change."""
    sha = hashlib.sha256()
    if not path.is_dir():
        return sha.hexdigest()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file.relative_to(path).as_posix()
        sha.update(rel.encode("utf-8"))
        sha.update(b"\x00")
        sha.update(file.read_bytes())
        sha.update(b"\x00")
    return sha.hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def is_fan_out(manifest: dict) -> bool:
    return manifest.get("boundary") in FAN_OUT_BOUNDARIES


def discover_fixture_dirs() -> list[Path]:
    if not FIXTURES_ROOT.is_dir():
        return []
    return sorted(
        p for p in FIXTURES_ROOT.iterdir() if p.is_dir() and (p / "manifest.json").is_file()
    )


def fixture_type(manifest: dict) -> str:
    if "boundary" in manifest:
        return "routed_boundary"
    if "scenario" in manifest:
        return "end_to_end_scenario"
    raise ValueError("manifest has neither 'boundary' nor 'scenario' key")


def _trial_match(record: dict) -> bool:
    return all(item["match"] for item in record["checklist_or_rubric_result"])


def recompute_checklist_verdict(trial_records: list[dict]) -> str:
    """Zero-tolerance rule: any dropped required item, in any trial, fails."""
    for record in trial_records:
        for item in record["checklist_or_rubric_result"]:
            if not item["match"]:
                return "fail"
    return "pass"


def recompute_rubric_verdict(trial_records: list[dict]) -> str:
    """2-of-3-trials majority; each trial's own match is itself all-or-nothing."""
    matches = sum(1 for record in trial_records if _trial_match(record))
    return "pass" if matches * 2 >= len(trial_records) else "fail"


class EvalFixtureHarnessLogicTests(unittest.TestCase):
    """Exercises the recompute/hash logic directly against synthetic
    records, independent of the committed corpus — this is what stands in
    for the "does the harness actually work" check while step 2a captures
    zero real trials to validate it against."""

    def test_hash_dir_is_stable_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a").mkdir()
            (base / "a" / "one.txt").write_text("hello")
            (base / "a" / "sub").mkdir()
            (base / "a" / "sub" / "two.txt").write_text("world")
            first = hash_dir(base / "a")
            second = hash_dir(base / "a")
            self.assertEqual(first, second)

            (base / "a" / "sub" / "two.txt").write_text("world!")
            self.assertNotEqual(first, hash_dir(base / "a"))

    def test_hash_dir_is_order_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "x").mkdir()
            (base / "x" / "z.txt").write_text("z")
            (base / "x" / "a.txt").write_text("a")
            (base / "y").mkdir()
            (base / "y" / "a.txt").write_text("a")
            (base / "y" / "z.txt").write_text("z")
            self.assertEqual(hash_dir(base / "x"), hash_dir(base / "y"))

    def test_checklist_verdict_is_zero_tolerance(self) -> None:
        all_pass = [
            {"checklist_or_rubric_result": [{"finding_id": "f1", "match": True}]},
            {"checklist_or_rubric_result": [{"finding_id": "f1", "match": True}]},
        ]
        self.assertEqual(recompute_checklist_verdict(all_pass), "pass")

        one_drop = [
            {"checklist_or_rubric_result": [{"finding_id": "f1", "match": True}]},
            {"checklist_or_rubric_result": [{"finding_id": "f1", "match": False}]},
        ]
        self.assertEqual(recompute_checklist_verdict(one_drop), "fail")

    def test_rubric_verdict_is_two_of_three_majority(self) -> None:
        two_of_three = [
            {"checklist_or_rubric_result": [{"finding_id": "r1", "match": True}]},
            {"checklist_or_rubric_result": [{"finding_id": "r1", "match": True}]},
            {
                "checklist_or_rubric_result": [
                    {"finding_id": "r1", "match": True},
                    {"finding_id": "r2", "match": False},
                ]
            },
        ]
        self.assertEqual(recompute_rubric_verdict(two_of_three), "pass")

        one_of_three = [
            {"checklist_or_rubric_result": [{"finding_id": "r1", "match": True}]},
            {
                "checklist_or_rubric_result": [
                    {"finding_id": "r1", "match": True},
                    {"finding_id": "r2", "match": False},
                ]
            },
            {"checklist_or_rubric_result": [{"finding_id": "r1", "match": False}]},
        ]
        self.assertEqual(recompute_rubric_verdict(one_of_three), "fail")

    def test_trial_match_is_all_or_nothing_within_a_trial(self) -> None:
        partial = {
            "checklist_or_rubric_result": [
                {"finding_id": "r1", "match": True},
                {"finding_id": "r2", "match": False},
            ]
        }
        self.assertFalse(_trial_match(partial))


class EvalFixtureCorpusTests(unittest.TestCase):
    """Checks (1)-(8) against the committed tests/fixtures/eval-baselines/
    corpus, per PLAN.md's Validation harness bullet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_dirs = discover_fixture_dirs()
        cls.manifests: dict[str, dict] = {}
        for path in cls.fixture_dirs:
            cls.manifests[path.name] = _load_json(path / "manifest.json")

    def test_corpus_is_present(self) -> None:
        self.assertTrue(
            self.fixture_dirs,
            "no fixture directories found under tests/fixtures/eval-baselines/",
        )

    # --- check (1): manifest.json parses and has the required keys ---

    def test_manifests_have_required_keys(self) -> None:
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            with self.subTest(fixture=path.name):
                kind = fixture_type(manifest)
                if kind == "routed_boundary":
                    missing = ROUTED_MANIFEST_REQUIRED - manifest.keys()
                    self.assertFalse(missing, f"missing keys: {missing}")
                    self.assertIn(manifest["provider"], VALID_PROVIDERS)
                    if is_fan_out(manifest):
                        self.assertIsInstance(
                            manifest.get("lens"),
                            str,
                            "fan-out boundary must name a singular lens",
                        )
                    else:
                        self.assertIn(
                            manifest.get("lens"),
                            (None,),
                            "non-fan-out boundary must not name a lens",
                        )
                else:
                    missing = SCENARIO_MANIFEST_REQUIRED - manifest.keys()
                    self.assertFalse(missing, f"missing keys: {missing}")
                    present_forbidden = SCENARIO_MANIFEST_FORBIDDEN & manifest.keys()
                    self.assertFalse(
                        present_forbidden,
                        f"end_to_end_scenario manifest must not declare {present_forbidden}",
                    )
                    self.assertTrue(manifest["providers"], "providers list must be non-empty")
                    for provider in manifest["providers"]:
                        self.assertIn(provider, VALID_PROVIDERS)
                        self.assertIn(provider, manifest["cli_version"])

    # --- check (2): pairing between runs/ and results/ trial records ---

    def test_runs_and_results_are_paired(self) -> None:
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            kind = fixture_type(manifest)
            with self.subTest(fixture=path.name):
                runs_dir = path / "runs"
                results_dir = path / "results"
                run_keys = set()
                if runs_dir.is_dir():
                    for f in runs_dir.iterdir():
                        if not f.is_file() or LAST_MD_RE.match(f.name):
                            continue
                        run_re = SCENARIO_RUN_RE if kind == "end_to_end_scenario" else ROUTED_RUN_RE
                        m = run_re.match(f.name)
                        self.assertIsNotNone(m, f"unrecognized runs/ filename: {f.name}")
                        run_keys.add(m.groupdict()["condition"] + "|" + m.groupdict().get("provider", "") + "|" + m.groupdict()["nn"])

                trial_keys = set()
                if results_dir.is_dir():
                    for f in results_dir.iterdir():
                        if not f.is_file() or "-trial-" not in f.name:
                            continue
                        trial_re = SCENARIO_TRIAL_RE if kind == "end_to_end_scenario" else ROUTED_TRIAL_RE
                        m = trial_re.match(f.name)
                        self.assertIsNotNone(m, f"unrecognized results/ trial filename: {f.name}")
                        trial_keys.add(m.groupdict()["condition"] + "|" + m.groupdict().get("provider", "") + "|" + m.groupdict()["nn"])

                self.assertEqual(
                    run_keys,
                    trial_keys,
                    f"runs/ and results/ trial records are not paired 1:1 in {path.name}",
                )

    # --- checks (3)/(4): per-trial and aggregate record schema + verdict recompute ---

    def test_trial_and_aggregate_records_conform(self) -> None:
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            kind = fixture_type(manifest)
            results_dir = path / "results"
            if not results_dir.is_dir():
                continue
            with self.subTest(fixture=path.name):
                trial_re = SCENARIO_TRIAL_RE if kind == "end_to_end_scenario" else ROUTED_TRIAL_RE
                agg_re = SCENARIO_AGGREGATE_RE if kind == "end_to_end_scenario" else ROUTED_AGGREGATE_RE

                trials_by_group: dict[str, list[dict]] = {}
                for f in sorted(results_dir.iterdir()):
                    if not f.is_file():
                        continue
                    m = trial_re.match(f.name)
                    if not m:
                        continue
                    record = _load_json(f)
                    missing = PER_TRIAL_REQUIRED - record.keys()
                    self.assertFalse(missing, f"{f.name}: missing keys {missing}")
                    self.assertNotIn("verdict", record, f"{f.name}: per-trial record must not carry a verdict")
                    group = m.groupdict()["condition"] + "|" + m.groupdict().get("provider", "")
                    trials_by_group.setdefault(group, []).append(record)

                for f in sorted(results_dir.iterdir()):
                    if not f.is_file():
                        continue
                    m = agg_re.match(f.name)
                    if not m:
                        continue
                    record = _load_json(f)
                    missing = AGGREGATE_REQUIRED - record.keys()
                    self.assertFalse(missing, f"{f.name}: missing keys {missing}")
                    group = m.groupdict()["condition"] + "|" + m.groupdict().get("provider", "")

                    if record["verdict"] == "skipped":
                        self.assertEqual(record["per_trial"], [], f"{f.name}: skipped verdict must carry no trials")
                        self.assertIn("note", record, f"{f.name}: skipped verdict must carry a note")
                        continue

                    self.assertNotIn("note", record, f"{f.name}: note is only valid on a skipped verdict")
                    constituents = [
                        t for t in trials_by_group.get(group, [])
                        if t["trial"] in record["per_trial"]
                    ]
                    self.assertEqual(
                        len(constituents),
                        len(record["per_trial"]),
                        f"{f.name}: aggregate references trial numbers with no matching record",
                    )
                    recompute = recompute_rubric_verdict if kind == "end_to_end_scenario" else recompute_checklist_verdict
                    self.assertEqual(
                        record["verdict"],
                        recompute(constituents),
                        f"{f.name}: recorded verdict does not match recomputed verdict",
                    )

                    if kind == "routed_boundary":
                        self.assertIn("evidence_sha256", record)
                        self.assertEqual(
                            record["evidence_sha256"],
                            hash_dir(path / "evidence"),
                            f"{f.name}: evidence_sha256 is stale relative to evidence/",
                        )
                    else:
                        self.assertIn("containment_sha256", record)
                        self.assertEqual(
                            record["containment_sha256"],
                            hash_dir(path / "containment"),
                            f"{f.name}: containment_sha256 is stale relative to containment/",
                        )

    # --- check (5): minimum 3 trial records per condition[/provider] that has any capture ---

    def test_minimum_trials_per_captured_condition(self) -> None:
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            kind = fixture_type(manifest)
            results_dir = path / "results"
            if not results_dir.is_dir():
                continue
            with self.subTest(fixture=path.name):
                trial_re = SCENARIO_TRIAL_RE if kind == "end_to_end_scenario" else ROUTED_TRIAL_RE
                agg_re = SCENARIO_AGGREGATE_RE if kind == "end_to_end_scenario" else ROUTED_AGGREGATE_RE

                counts: dict[str, int] = {}
                for f in results_dir.iterdir():
                    m = trial_re.match(f.name) if f.is_file() else None
                    if not m:
                        continue
                    group = m.groupdict()["condition"] + "|" + m.groupdict().get("provider", "")
                    counts[group] = counts.get(group, 0) + 1

                skipped_groups = set()
                for f in results_dir.iterdir():
                    m = agg_re.match(f.name) if f.is_file() else None
                    if not m:
                        continue
                    if _load_json(f)["verdict"] == "skipped":
                        skipped_groups.add(m.groupdict()["condition"] + "|" + m.groupdict().get("provider", ""))

                for group, count in counts.items():
                    if group in skipped_groups:
                        continue
                    self.assertGreaterEqual(
                        count,
                        3,
                        f"{path.name}: condition/provider {group!r} has {count} captured trial(s), "
                        "below the minimum of 3 for a lane that has begun capture",
                    )

    # --- check (6): every aggregate under one fixture (and provider, for a scenario)
    # shares the same evidence_sha256/containment_sha256 ---

    def test_aggregates_share_one_evidence_hash_per_fixture(self) -> None:
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            kind = fixture_type(manifest)
            results_dir = path / "results"
            if not results_dir.is_dir():
                continue
            with self.subTest(fixture=path.name):
                agg_re = SCENARIO_AGGREGATE_RE if kind == "end_to_end_scenario" else ROUTED_AGGREGATE_RE
                hash_key = "containment_sha256" if kind == "end_to_end_scenario" else "evidence_sha256"
                seen: dict[str, str] = {}
                for f in results_dir.iterdir():
                    m = agg_re.match(f.name) if f.is_file() else None
                    if not m:
                        continue
                    record = _load_json(f)
                    if hash_key not in record:
                        continue
                    provider = m.groupdict().get("provider", "")
                    prior = seen.get(provider)
                    if prior is not None:
                        self.assertEqual(
                            prior,
                            record[hash_key],
                            f"{path.name} (provider={provider!r}): aggregate {hash_key} diverges across conditions",
                        )
                    seen[provider] = record[hash_key]

    # --- check (7): cross-directory evidence/ identity for a boundary split into
    # multiple (route, provider) directories ---

    def test_multi_directory_boundaries_share_evidence(self) -> None:
        by_boundary: dict[str, list[Path]] = {}
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            if fixture_type(manifest) != "routed_boundary":
                continue
            by_boundary.setdefault(manifest["boundary"], []).append(path)

        for boundary, dirs in by_boundary.items():
            if len(dirs) < 2:
                continue
            with self.subTest(boundary=boundary):
                hashes = {d.name: hash_dir(d / "evidence") for d in dirs}
                distinct = set(hashes.values())
                self.assertEqual(
                    len(distinct),
                    1,
                    f"{boundary}: evidence/ diverges across directories: {hashes}",
                )

    # --- check (8): cross-directory checklist.md identity for a fan-out boundary ---

    def test_fan_out_boundaries_share_checklist(self) -> None:
        by_boundary: dict[str, list[Path]] = {}
        for path in self.fixture_dirs:
            manifest = self.manifests[path.name]
            if fixture_type(manifest) != "routed_boundary":
                continue
            if not is_fan_out(manifest):
                continue
            by_boundary.setdefault(manifest["boundary"], []).append(path)

        for boundary, dirs in by_boundary.items():
            with self.subTest(boundary=boundary):
                self.assertGreaterEqual(
                    len(dirs),
                    2,
                    f"{boundary}: declared fan-out but fewer than 2 directories found",
                )
                hashes = {
                    d.name: hashlib.sha256((d / "checklist.md").read_bytes()).hexdigest()
                    for d in dirs
                }
                distinct = set(hashes.values())
                self.assertEqual(
                    len(distinct),
                    1,
                    f"{boundary}: checklist.md diverges across directories: {hashes}",
                )


if __name__ == "__main__":
    unittest.main()
