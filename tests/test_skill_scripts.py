"""Skill and toolkit scripts: real git fixtures for the cherry-pick audits, node smoke tests for the QA recorder and the Preset host classifier."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "cherry-pick" / "scripts"


class Repo:
    """A scratch repository with deterministic commit dates."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.clock = 1_700_000_000
        path.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *arguments: str, author_date: str | None = None) -> str:
        self.clock += 60
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_AUTHOR_DATE": author_date or f"@{self.clock} +0000",
            "GIT_COMMITTER_DATE": f"@{self.clock} +0000",
        }
        result = subprocess.run(
            ["git", "-C", str(self.path), *arguments],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(self, message: str, files: dict[str, str | None], author_date: str | None = None) -> str:
        for name, content in files.items():
            target = self.path / name
            if content is None:
                self.git("rm", "-q", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self.git("add", name)
        self.git("commit", "-q", "-m", message, author_date=author_date)
        return self.git("rev-parse", "HEAD")

    def short(self, sha: str) -> str:
        return self.git("rev-parse", "--short", sha)


def run(script: str, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


class ScriptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.repo = Repo(self.base / "repo")

    def tearDown(self) -> None:
        self.temporary.cleanup()


class BatchDepsTests(ScriptTestCase):
    def test_a_merge_commit_lists_the_files_it_brings_in(self) -> None:
        repo = self.repo
        repo.commit("base", {"README.md": "base\n"})
        repo.git("checkout", "-q", "-b", "feature")
        repo.commit("feature work", {"feature.py": "VALUE = 1\n"})
        repo.git("checkout", "-q", "main")
        other = repo.commit("other", {"other.py": "OTHER = 1\n"})
        repo.git("merge", "-q", "--no-ff", "-m", "Merge feature", "feature")
        merge = repo.git("rev-parse", "HEAD")

        result = run("batch-deps.sh", merge, other, cwd=repo.path)
        self.assertEqual(0, result.returncode, result.stderr)
        section = re.search(
            rf"^### {repo.short(merge)}\n(.*?)(?=^#)", result.stdout, re.M | re.S
        ).group(1)
        self.assertIn("- feature.py", section)
        self.assertNotIn("other.py", section)

    def test_order_follows_the_source_branch_first_parent_line(self) -> None:
        repo = self.repo
        repo.commit("base", {"README.md": "base\n"})
        repo.git("branch", "release")
        # Landed first, authored last; landed second, authored first.
        first = repo.commit("first landed", {"a.py": "A = 1\n"}, author_date="2024-03-01T12:00:00+00:00")
        second = repo.commit("second landed", {"a.py": "A = 2\n"}, author_date="2024-01-01T12:00:00-05:00")
        repo.git("checkout", "-q", "-b", "topic")
        inner = repo.commit("inside a merged branch", {"b.py": "B = 1\n"}, author_date="2023-01-01T00:00:00+00:00")
        repo.git("checkout", "-q", "main")
        repo.git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic")

        result = run(
            "batch-deps.sh", "--source", "main", "--target", "release", inner, second, first, cwd=repo.path
        )
        self.assertEqual(0, result.returncode, result.stderr)
        order = result.stdout.split("## Execution Order", 1)[1]
        self.assertIn("first-parent position on main", order)
        positions = [order.index(repo.short(sha)) for sha in (first, second, inner)]
        self.assertEqual(sorted(positions), positions, order)
        # The pair sharing a.py is an edge.
        self.assertRegex(result.stdout, r"1 shared file\(s\)\n\s+a\.py")

    def test_rejects_an_unknown_commit(self) -> None:
        self.repo.commit("base", {"README.md": "base\n"})
        result = run("batch-deps.sh", "HEAD", "deadbeef", cwd=self.repo.path)
        self.assertEqual(2, result.returncode)


class ReleaseAuditTests(ScriptTestCase):
    def test_trailing_pr_number_wins_and_reverts_do_not_count(self) -> None:
        repo = self.repo
        repo.commit("base", {"README.md": "base\n"})
        repo.git("branch", "release")
        repo.commit("fix: handle issue #45 in parser (#123)", {"a.py": "A = 1\n"})
        repo.commit("feat: new chart (#124)", {"b.py": "B = 1\n"})
        repo.commit("chore: bump version (#45)", {"c.py": "C = 1\n"})
        repo.commit("Merge pull request #125 from fork/branch", {"d.py": "D = 1\n"})
        repo.git("checkout", "-q", "release")
        repo.commit("fix: handle issue #45 in parser (#123)", {"a.py": "A = 1\n"})
        # Picked under a subject without the PR number, then reverted: only the
        # revert's subject names #124.
        repo.commit("feat: new chart", {"b.py": "B = 1\n"})
        repo.commit('Revert "feat: new chart (#124)"', {"b.py": None})

        result = run("release-audit.sh", "release", "main", cwd=repo.path)
        self.assertEqual(0, result.returncode, result.stderr)
        rows = {
            line.split("\t")[3]: (line.split("\t")[0], line.split("\t")[2])
            for line in result.stdout.splitlines()[1:]
        }
        self.assertEqual(("PRESENT-BY-PR", "123"), rows["fix: handle issue #45 in parser (#123)"])
        # Reverted on the release branch: still missing there.
        self.assertEqual(("MISSING", "124"), rows["feat: new chart (#124)"])
        # #45 is an issue reference in a target subject, not a PR on it.
        self.assertEqual(("MISSING", "45"), rows["chore: bump version (#45)"])
        self.assertEqual(("MISSING", "125"), rows["Merge pull request #125 from fork/branch"])


BASE_MODULE = "".join(f"line_{index} = {index}\n" for index in range(1, 11))


class ScopeAuditTests(ScriptTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo = self.repo
        repo.commit("base", {"app.py": BASE_MODULE, "util.py": "def compute(value):\n    return value * 1\n"})
        repo.git("branch", "release")
        self.neighbour = repo.commit(
            "neighbour: change line one", {"app.py": BASE_MODULE.replace("line_1 = 1", "line_1 = 100")}
        )
        self.source = repo.commit(
            "source: change line seven",
            {"app.py": BASE_MODULE.replace("line_1 = 1", "line_1 = 100").replace("line_7 = 7", "line_7 = 700")},
        )
        repo.git("checkout", "-q", "release")

    def audit(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        # -C makes the cwd irrelevant.
        return run("scope-audit.sh", "-C", str(self.repo.path), *arguments, cwd=self.base)

    def test_an_exact_pick_is_clean(self) -> None:
        self.repo.commit("pick", {"app.py": BASE_MODULE.replace("line_7 = 7", "line_7 = 700")})
        result = self.audit(self.source)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Extra lines: none", result.stdout)
        self.assertIn("Missing lines: none", result.stdout)
        self.assertIn("CLEAN", result.stdout)
        # Without -C, from inside the repository, the result is the same.
        inside = run("scope-audit.sh", self.source, cwd=self.repo.path)
        self.assertEqual(0, inside.returncode, inside.stdout + inside.stderr)

    def test_a_conflict_resolved_toward_the_source_leaks_a_neighbours_line(self) -> None:
        self.repo.commit(
            "pick resolved toward source",
            {"app.py": BASE_MODULE.replace("line_1 = 1", "line_1 = 100").replace("line_7 = 7", "line_7 = 700")},
        )
        result = self.audit(self.source, "HEAD")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        extra = result.stdout.split("### Extra lines", 1)[1].split("###", 1)[0]
        self.assertIn("app.py: +line_1 = 100", extra)
        self.assertIn("app.py: -line_1 = 1", extra)
        self.assertIn(self.repo.short(self.neighbour), extra)
        self.assertIn("neighbour: change line one", extra)
        self.assertNotIn("line_7", extra)
        self.assertNotIn("20%", result.stdout)

    def test_moved_code_carrying_a_neighbours_change_is_flagged(self) -> None:
        repo = self.repo
        repo.git("checkout", "-q", "main")
        neighbour = repo.commit(
            "neighbour: change compute", {"util.py": "def compute(value):\n    return value * 2\n"}
        )
        repo.git("mv", "util.py", "helpers.py")
        repo.git("commit", "-q", "-m", "source: move util to helpers")
        move = repo.git("rev-parse", "HEAD")
        repo.git("checkout", "-q", "release")
        repo.commit(
            "pick the move",
            {"util.py": None, "helpers.py": "def compute(value):\n    return value * 2\n"},
        )
        result = self.audit(move)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        moved = result.stdout.split("### Moved-code check", 1)[1]
        self.assertIn("helpers.py (from util.py)", moved)
        self.assertIn("MOVED-CODE LEAK", moved)
        self.assertIn("+    return value * 2", moved)
        self.assertIn(repo.short(neighbour), moved)

        # Moving the target's own version carries nothing.
        repo.git("reset", "-q", "--hard", "HEAD^")
        repo.commit(
            "pick the move, adapted",
            {"util.py": None, "helpers.py": "def compute(value):\n    return value * 1\n"},
        )
        adapted = self.audit(move)
        self.assertIn("no neighbour changes carried", adapted.stdout)
        self.assertNotIn("MOVED-CODE LEAK", adapted.stdout)

    def test_rejects_an_unknown_commit(self) -> None:
        result = self.audit("deadbeef")
        self.assertEqual(2, result.returncode)
        self.assertRegex(result.stderr, re.compile("not a valid commit"))


NODE = shutil.which("node")
HOSTS = ROOT / "scripts" / "preset" / "hosts.mjs"
RECORD = ROOT / "scripts" / "qa" / "record.mjs"

# The table in rules/preset-environments.md, as scripts/preset/hosts.mjs reads it.
HOST_FIXTURE = {
    "localhost:8088": "local",
    "http://127.0.0.1:3000/": "local",
    "0.0.0.0": "local",
    "https://ws1.us1a.app-stg.preset.io/superset/welcome/": "staging",
    "manage.app-stg.preset.io": "staging",
    "https://manage.app-stg.preset.io/login/?next=https%3A%2F%2Fws1.us1a.app.preset.io%2F": "staging",
    "https://ws1.us1a.app-dev.preset.io": "dev",
    "manage.app-dev.preset.io": "dev",
    "https://ws1.us1a.app.preset.io/": "production",
    "manage.app.preset.io": "production",
    "app.preset.io": "production",
    "WS1.US1A.APP.PRESET.IO.": "production",
    # Old patterns and look-alikes: unknown, which callers treat as production.
    "ws1.stg.preset.io": "unknown",
    "manager.stg.preset.io": "unknown",
    "app-stg.preset.io.example.com": "unknown",
    "evilapp-stg.preset.io": "unknown",
    "example.com": "unknown",
    "": "unknown",
}


def node(*arguments: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, *arguments],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


@unittest.skipIf(NODE is None, "node is not installed")
class NodeScriptTests(unittest.TestCase):
    def test_scripts_parse(self) -> None:
        for script in (HOSTS, RECORD):
            with self.subTest(script=script.name):
                result = node("--check", str(script))
                self.assertEqual(0, result.returncode, result.stderr)

    def test_hosts_classify_the_rule_table(self) -> None:
        result = node(str(HOSTS), *HOST_FIXTURE)
        self.assertEqual(0, result.returncode, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(HOST_FIXTURE), len(lines), result.stdout)
        for (value, expected), line in zip(HOST_FIXTURE.items(), lines):
            with self.subTest(host=value):
                self.assertEqual(expected, json.loads(line)["environment"])

    def test_the_rule_lists_every_pattern_the_classifier_knows(self) -> None:
        rule = (ROOT / "rules" / "preset-environments.md").read_text()
        for pattern in (
            "*.app-stg.preset.io",
            "manage.app-stg.preset.io",
            "*.app-dev.preset.io",
            "manage.app-dev.preset.io",
            "*.app.preset.io",
            "manage.app.preset.io",
            "scripts/preset/hosts.mjs",
        ):
            self.assertIn(f"`{pattern}`", rule)

    def record(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as home:
            # No credentials and no Playwright reach the script from the caller.
            env = {"PATH": os.environ.get("PATH", ""), "HOME": home}
            return node(str(RECORD), *arguments, cwd=Path(home), env=env)

    def test_record_help_and_usage(self) -> None:
        help_result = self.record("--help")
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("usage: record.mjs --url", help_result.stdout)
        for arguments in (
            (),
            ("--url", "http://localhost:8088", "--role", "admin"),
            ("--url", "http://localhost:8088", "--role", "admin", "--source-id", "sc-1", "--name", "a b", "--flow", "f.mjs"),
            ("--bogus",),
        ):
            with self.subTest(arguments=arguments):
                result = self.record(*arguments)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertIn("usage: record.mjs", result.stderr)

    def test_record_refuses_production_and_unknown_hosts(self) -> None:
        for url in ("https://ws1.us1a.app.preset.io/", "https://manage.app.preset.io", "https://example.com"):
            with self.subTest(url=url):
                result = self.record(
                    "--url", url, "--role", "viewer", "--source-id", "sc-NNNNN", "--name", "smoke", "--flow", "flow.mjs"
                )
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertIn("refusing", result.stderr)

    def test_record_needs_the_flow_file_and_staging_credentials(self) -> None:
        missing = self.record(
            "--url", "http://localhost:8088", "--role", "admin", "--source-id", "pr-1", "--name", "smoke",
            "--flow", "no-such-flow.mjs",
        )
        self.assertEqual(2, missing.returncode, missing.stderr)
        self.assertIn("flow file not found", missing.stderr)
        with tempfile.TemporaryDirectory() as directory:
            flow = Path(directory) / "flow.mjs"
            flow.write_text("export default async () => {};\n")
            staging = self.record(
                "--url", "https://ws1.us1a.app-stg.preset.io/", "--role", "viewer", "--source-id", "sc-NNNNN",
                "--name", "smoke", "--flow", str(flow),
            )
        self.assertEqual(2, staging.returncode, staging.stderr)
        self.assertIn("PRESET_STG_BOT_LOGIN", staging.stderr)

    def test_record_keeps_its_safety_properties(self) -> None:
        source = RECORD.read_text()
        self.assertIn("from '../preset/hosts.mjs'", source)
        self.assertIn("`${host}-${options.role}.json`", source)
        self.assertIn("!url.pathname.startsWith('/login')", source)
        self.assertIn("url.hostname === host", source)
        self.assertEqual(1, source.count("--disable-blink-features=AutomationControlled"))
        self.assertIn("recordVideo", source)
        self.assertIn("__qa_cursor__", source)
        self.assertNotRegex(source, r"console\.(log|error)\([^)]*(password|creds|login)\b")
        self.assertFalse((ROOT / "skills/qa/references/browser-recording/record-flow.template.mjs").exists())



def executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


GH_PR_STUB = """#!/usr/bin/env python3
import json, os, sys
prs = json.loads(os.environ["GH_PRS"])
args = sys.argv[1:]
if args[:2] != ["pr", "view"] or args[2] not in prs:
    sys.exit(1)
print(json.dumps(prs[args[2]]))
"""


class BatchPreflightTests(ScriptTestCase):
    """NW-21: one TSV row per request; a PR number or a -x marker on the target counts as applied."""

    def setUp(self) -> None:
        super().setUp()
        repo = self.repo
        repo.commit("base", {"base.txt": "base\n"})
        repo.git("branch", "release")
        self.one = repo.commit("Fix one (#101)", {"one.txt": "1\n"})
        self.two = repo.commit("Fix two (#102)", {"two.txt": "2\n"})
        repo.git("checkout", "-q", "-b", "side")
        repo.commit("Side work", {"side.txt": "s\n"})
        repo.git("checkout", "-q", "main")
        repo.git("merge", "-q", "--no-ff", "side", "-m", "Merge pull request #103 from someone/side")
        self.merge = repo.git("rev-parse", "HEAD")
        self.four = repo.commit("Fix four (#104)", {"four.txt": "4\n"})
        self.five = repo.commit("Tidy docs", {"docs.txt": "d\n"})
        repo.git("checkout", "-q", "release")
        repo.commit("Fix one (#101)", {"one.txt": "1\n"})
        repo.commit(f"Backport fix two\n\n(cherry picked from commit {self.two})", {"two.txt": "2\n"})
        repo.commit("Fix four (#104)", {"four.txt": "4\n"})
        repo.commit('Revert "Fix four (#104)"', {"four.txt": None})
        repo.commit("Tidy docs", {"docs.txt": "d\n"})
        repo.git("checkout", "-q", "main")
        self.bin = executable(self.base / "gh", GH_PR_STUB).parent
        prs = {
            "101": {"number": 101, "title": "Fix one", "state": "MERGED", "mergeCommit": {"oid": self.one}},
            "105": {"number": 105, "title": "Still open", "state": "OPEN", "mergeCommit": None},
        }
        self.env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "GH_PRS": json.dumps(prs)}

    def preflight(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS / "batch-preflight.sh"), *arguments],
            cwd=self.repo.path, env=self.env, text=True, capture_output=True, check=False, timeout=60,
        )

    def test_rows_follow_the_one_evidence_rule(self) -> None:
        result = self.preflight(
            "release", "101", self.two, "#105", "#999", self.merge, self.four, self.five, "deadbeefcafe"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual("status\trequest\tpr\tsha\tparents\tevidence\ttitle", lines[0])
        rows = [line.split("\t") for line in lines[1:]]
        self.assertEqual(
            [
                ["ALREADY_APPLIED", "101", "101", self.one, "1", "target first-parent has #101", "Fix one"],
                ["ALREADY_APPLIED", self.two, "102", self.two, "1", "cherry-pick -x marker", "Fix two (#102)"],
                ["NOT_MERGED", "#105", "105", "-", "-", "state OPEN", "Still open"],
                ["PREFLIGHT_BLOCKED", "#999", "999", "-", "-", "gh pr view failed", "-"],
                ["NEEDS_INVESTIGATION", self.merge, "103", self.merge, "2", "-", "Merge pull request #103 from someone/side"],
                ["NEEDS_INVESTIGATION", self.four, "104", self.four, "1", "title-match (advisory)", "Fix four (#104)"],
                ["NEEDS_INVESTIGATION", self.five, "-", self.five, "1", "title-match (advisory)", "Tidy docs"],
                ["PREFLIGHT_BLOCKED", "deadbeefcafe", "-", "-", "-", "unknown commit", "-"],
            ],
            rows,
        )

    def test_usage_and_unknown_target(self) -> None:
        self.assertEqual(2, self.preflight("release").returncode)
        missing = self.preflight("no-such-branch", "101")
        self.assertEqual(2, missing.returncode)
        self.assertIn("unknown target branch", missing.stderr)



GH_MEASURE_STUB = """#!/usr/bin/env python3
import json, os, sys
prs = json.loads(os.environ["GH_PRS"])
args = sys.argv[1:]
if args[:2] != ["pr", "view"] or args[2] not in prs or args[3:5] != ["--repo", os.environ["GH_REPO_EXPECTED"]]:
    sys.exit(1)
print(json.dumps(prs[args[2]]))
"""


class UnblockMeasureTests(unittest.TestCase):
    """NW-26: per-candidate size, the migration flag and the easy / heavy / risky rating, from a stub gh."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.bin = executable(self.base / "gh", GH_MEASURE_STUB).parent

        def files(count: int, *extra: str) -> list[dict[str, object]]:
            paths = [f"src/module_{index}.py" for index in range(count)] + list(extra)
            return [{"path": path, "additions": 1, "deletions": 0} for path in paths]

        self.prs = {
            "11": {"number": 11, "title": "Small fix", "changedFiles": 3, "additions": 20,
                   "deletions": 4, "files": files(3)},
            "12": {"number": 12, "title": "Big\tfeature\nwork", "changedFiles": 40, "additions": 900,
                   "deletions": 100, "files": files(40)},
            "13": {"number": 13, "title": "Add a column", "changedFiles": 2, "additions": 30,
                   "deletions": 0, "files": files(1, "superset/migrations/versions/2024_add_column.py")},
            "14": {"number": 14, "title": "Huge refactor", "changedFiles": 120, "additions": 5000,
                   "deletions": 4000, "files": files(100)},
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def measure(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GH_PRS": json.dumps(self.prs),
            "GH_REPO_EXPECTED": "octo/widgets",
        }
        return subprocess.run(
            ["bash", str(SCRIPTS / "unblock-measure.sh"), *arguments],
            cwd=self.base, env=env, text=True, capture_output=True, check=False, timeout=60,
        )

    def rows(self, result: subprocess.CompletedProcess[str]) -> list[list[str]]:
        self.assertEqual(0, result.returncode, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual("pr\tfiles\tadded\tremoved\tmigration\trating\ttitle", lines[0])
        return [line.split("\t") for line in lines[1:]]

    def test_each_candidate_is_measured_and_rated(self) -> None:
        self.assertEqual(
            [
                ["#11", "3", "20", "4", "no", "easy", "Small fix"],
                ["#12", "40", "900", "100", "no", "heavy", "Big feature work"],
                ["#13", "2", "30", "0", "yes", "risky", "Add a column"],
                ["#14", "120", "5000", "4000", "unknown", "heavy", "Huge refactor"],
                ["chain", "165", "5950", "4104", "yes", "risky", "4 PRs"],
            ],
            self.rows(self.measure("octo/widgets", "11", "#12", "13", "14")),
        )

    def test_a_chain_is_only_as_easy_as_its_worst_link(self) -> None:
        self.assertEqual(
            ["chain", "3", "20", "4", "no", "easy", "1 PRs"],
            self.rows(self.measure("octo/widgets", "11"))[-1],
        )
        self.assertEqual(
            ["chain", "43", "920", "104", "no", "heavy", "2 PRs"],
            self.rows(self.measure("octo/widgets", "11", "12"))[-1],
        )

    def test_an_unreadable_pr_makes_the_chain_unmeasured(self) -> None:
        rows = self.rows(self.measure("octo/widgets", "11", "#999"))
        self.assertEqual(["#999", "-", "-", "-", "-", "unmeasured", "gh pr view failed"], rows[1])
        self.assertEqual(["chain", "3", "20", "4", "no", "unmeasured", "2 PRs"], rows[2])
        # The repository is passed through: the stub refuses any other one.
        other = self.rows(self.measure("octo/other", "11"))
        self.assertEqual("unmeasured", other[0][5])

    def test_usage_errors_exit_2(self) -> None:
        for arguments in ((), ("octo/widgets",), ("widgets", "11"), ("octo/widgets", "abc")):
            with self.subTest(arguments=arguments):
                result = self.measure(*arguments)
                self.assertEqual(2, result.returncode)
                self.assertIn("usage:", result.stderr)
                self.assertEqual("", result.stdout)


CURL_STUB = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
state = Path(os.environ["CURL_STATE"])
with (state / "calls.jsonl").open("a") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
queue = sorted(state.glob("response-*.json"))
if not queue:
    sys.exit(7)
response = json.loads(queue[0].read_text())
queue[0].unlink()
sys.stdout.write(response["body"])
sys.exit(response.get("exit", 0))
"""


class ShortcutScriptTests(unittest.TestCase):
    """NW-22: sc.sh against a stub curl."""

    SCRIPT = ROOT / "skills" / "shortcut" / "scripts" / "sc.sh"

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name).resolve()
        bin_dir = self.state / "bin"
        bin_dir.mkdir()
        executable(bin_dir / "curl", CURL_STUB)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CURL_STATE": str(self.state),
            "SHORTCUT_API_TOKEN": "test-token",
            "SHORTCUT_API_BASE": "https://shortcut.invalid",
        }
        self.count = 0

    def respond(self, body: object, exit_code: int = 0) -> None:
        self.count += 1
        text = body if isinstance(body, str) else json.dumps(body)
        (self.state / f"response-{self.count:03d}.json").write_text(json.dumps({"body": text, "exit": exit_code}))

    def sc(self, *arguments: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.SCRIPT), *arguments], env={**self.env, **env}, text=True, capture_output=True, check=False, timeout=60,
        )

    def calls(self) -> list[list[str]]:
        log = self.state / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_get_retries_once_on_organization2_missing_and_parses_loosely(self) -> None:
        self.respond({"errors": ["organization2_missing"]})
        self.respond('{"id": 7, "description": "line one\nline two"}')
        result = self.sc("get", "/stories/7")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"id": 7, "description": "line one\nline two"}, json.loads(result.stdout))
        calls = self.calls()
        self.assertEqual(2, len(calls))
        self.assertIn("--fail-with-body", calls[0])
        self.assertIn("Shortcut-Token: test-token", calls[0])
        self.assertEqual("https://shortcut.invalid/api/v3/stories/7", calls[0][-1])
        self.assertNotIn("test-token", result.stdout + result.stderr)

    def test_an_http_error_is_retried_once_then_reported(self) -> None:
        self.respond({"message": "Bad Gateway"}, exit_code=22)
        self.respond({"id": 1})
        self.assertEqual(0, self.sc("get", "/members").returncode)
        self.respond({"message": "Bad Gateway"}, exit_code=22)
        self.respond({"message": "Bad Gateway"}, exit_code=22)
        self.respond({"id": 2})
        failed = self.sc("get", "/members")
        self.assertEqual(1, failed.returncode)
        self.assertIn("failed after retry", failed.stderr)
        self.assertEqual(4, len(self.calls()))

    def test_search_follows_next_until_the_last_page(self) -> None:
        self.respond({"data": [{"id": 1}], "next": "/api/v3/search/stories?query=owner%3Ame&next=abc"})
        self.respond({"data": [{"id": 2}, {"id": 3}], "next": None})
        result = self.sc("search", "owner:me is:started")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([{"id": 1}, {"id": 2}, {"id": 3}], json.loads(result.stdout))
        first, second = self.calls()
        self.assertEqual(
            "https://shortcut.invalid/api/v3/search/stories?query=owner%3Ame%20is%3Astarted&page_size=25", first[-1]
        )
        self.assertEqual("https://shortcut.invalid/api/v3/search/stories?query=owner%3Ame&next=abc", second[-1])

    def test_post_sends_json_and_usage_errors_exit_2(self) -> None:
        self.respond({"id": 9})
        result = self.sc("post", "/stories/9/comments", '{"text": "done"}')
        self.assertEqual(0, result.returncode, result.stderr)
        call = self.calls()[0]
        self.assertEqual("POST", call[call.index("-X") + 1])
        self.assertEqual('{"text": "done"}', call[call.index("--data-binary") + 1])
        self.assertIn("Content-Type: application/json", call)
        for arguments in ((), ("get",), ("delete", "/x"), ("post", "/x")):
            with self.subTest(arguments=arguments):
                self.assertEqual(2, self.sc(*arguments).returncode)
        missing = self.sc("get", "/x", SHORTCUT_API_TOKEN="")
        self.assertEqual(2, missing.returncode)
        self.assertIn("SHORTCUT_API_TOKEN is not set", missing.stderr)

    def test_upload_numbers_the_parts_and_attaches_to_a_story(self) -> None:
        first, second = self.state / "a.png", self.state / "b.webm"
        first.write_bytes(b"png")
        second.write_bytes(b"webm")
        self.respond([{"id": 1, "url": "https://files.invalid/a.png"}])
        result = self.sc("upload", "--story", "12", str(first), str(second))
        self.assertEqual(0, result.returncode, result.stderr)
        call = self.calls()[0]
        parts = [call[index + 1] for index, value in enumerate(call) if value == "-F"]
        self.assertEqual(["story_id=12", f"file0=@{first}", f"file1=@{second}"], parts)
        self.assertEqual("https://shortcut.invalid/api/v3/files", call[-1])
        for arguments in (("upload",), ("upload", "--story", "x", str(first)), ("upload", str(self.state / "none"))):
            with self.subTest(arguments=arguments):
                self.assertEqual(2, self.sc(*arguments).returncode)


DOCKER_STUB = """#!/usr/bin/env python3
import os, sys
from pathlib import Path
state = Path(os.environ["DOCKER_STATE"])
args = sys.argv[1:]
with (state / "docker.log").open("a") as handle:
    handle.write(" ".join(args) + "\\n")
up = (state / "up").exists()
if args[:1] == ["compose"]:
    (state / "up").write_text("1")
    sys.exit(0)
if args[:2] == ["ps", "-a"]:
    print("superset-superset-init-light-1" if up else "")
    sys.exit(0)
if args[:1] == ["ps"]:
    if up:
        print("superset-superset-light-1\\tUp 2 minutes (healthy)\\t8088/tcp")
        print("superset-superset-node-light-1\\tUp 2 minutes\\t0.0.0.0:9002->9000/tcp")
    sys.exit(0)
if args[:1] == ["logs"]:
    print("Step 4/4 [Complete]" if os.environ.get("INIT_DONE") == "1" else "Step 3/4 loading")
    sys.exit(0)
sys.exit(1)
"""


class SupersetUpTests(unittest.TestCase):
    """NW-20: detection, a stubbed start, and a timeout; never edits source."""

    SCRIPT = ROOT / "scripts" / "superset-local" / "up.sh"

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.work = self.base / "superset"
        self.work.mkdir()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        executable(bin_dir / "docker", DOCKER_STUB)
        executable(bin_dir / "curl", "#!/bin/sh\nprintf 302\n")
        executable(bin_dir / "clo", "#!/bin/sh\nexit 0\n")
        self.env = {
            key: value for key, value in os.environ.items() if key != "PROJECT"
        } | {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "DOCKER_STATE": str(self.base), "INIT_DONE": "1"}

    def up(self, *arguments: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.SCRIPT), *arguments], cwd=self.work, env={**self.env, **env},
            text=True, capture_output=True, check=False, timeout=60,
        )

    def test_detects_the_start_command(self) -> None:
        self.assertEqual(2, self.up("--detect").returncode)
        (self.work / "docker-compose-light.yml").write_text("services: {}\n")
        self.assertEqual("docker compose -f docker-compose-light.yml up -d", self.up("--detect").stdout.strip())
        self.assertEqual(2, self.up("--detect", "--interval", "soon").returncode)
        self.assertEqual("clo docker up", self.up("--detect", PROJECT="superset").stdout.strip())
        (self.work / ".claudette").mkdir()
        self.assertEqual("clo docker up", self.up("--detect").stdout.strip())

    def test_starts_waits_and_prints_the_node_port_without_editing_source(self) -> None:
        (self.work / "docker-compose-light.yml").write_text("services: {}\n")
        config = self.work / "docker/pythonpath_dev/superset_config_docker_light.py"
        config.parent.mkdir(parents=True)
        config.write_text("FEATURE_FLAGS = {}\n")
        result = self.up("--interval", "0")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PLAYWRIGHT_BASE_URL=http://localhost:9002", result.stdout)
        self.assertIn("Frontend: http://localhost:9002 (HTTP 302)", result.stdout)
        self.assertIn("COMPRESS_ALGORITHM", result.stderr)
        self.assertEqual("FEATURE_FLAGS = {}\n", config.read_text())
        self.assertIn("compose -f docker-compose-light.yml up -d", (self.base / "docker.log").read_text())
        again = self.up("--interval", "0")
        self.assertEqual(0, again.returncode, again.stderr)
        starts = [line for line in (self.base / "docker.log").read_text().splitlines() if line.startswith("compose ")]
        self.assertEqual(1, len(starts), "a healthy stack is not restarted")

    def test_gives_up_after_the_timeout(self) -> None:
        (self.work / "docker-compose-light.yml").write_text("services: {}\n")
        result = self.up("--timeout", "0", "--interval", "0", INIT_DONE="0")
        self.assertEqual(1, result.returncode)
        self.assertIn("not ready after 0s (last phase: init)", result.stderr)


RBAC = ROOT / "scripts" / "preset" / "setup-rbac.mjs"

RBAC_FIXTURE = {
    "workspace": {"id": 42, "name": "rbac-ws", "hostname": "ws1.us1a.app-stg.preset.io"},
    "memberships": [
        {"user": {"email": "Test-Primary-Contributor@preset.zone", "id": 1, "username": "primary"},
         "workspaces": [{"workspace_id": 42, "role_identifier": "PresetAlpha"}]},
        {"user": {"email": "test-limited-contributor@preset.zone", "id": 2, "username": "limited"},
         "workspaces": [{"workspace_id": 42, "role_identifier": "PresetAlpha"}]},
        {"email": "test-limited-contributor-no-access@preset.zone", "user_id": 3, "username": "limited-none"},
        {"user": {"email": "test-dashboard-viewer@preset.zone", "id": 4, "username": "dash"}},
        {"user": {"email": "test-viewer@preset.zone", "id": 6, "username": "viewer"}},
        {"user": {"email": "test-no-access@preset.zone", "id": 7, "username": "none"}},
    ],
    "permissions": {
        "primary": [{"name": "AI Toolkit RBAC primary", "acl": {"dar:AI Toolkit RBAC primary": {"config": {}, "grants": "DEFAULT"}}}],
        "limited": [{"name": "AI Toolkit RBAC limited", "acl": {"dar:AI Toolkit RBAC limited": {"config": {}, "grants": []}}},
                    {"name": "Customer analysts"}],
        "limited-none": [{"name": "AI Toolkit RBAC limited-none"}],
        "dash": [{"name": "AI Toolkit RBAC old-dash"}],
    },
}

RBAC_PLAN = [
    {"email": "test-primary-contributor@preset.zone", "role": ["none", "PresetAlpha"], "dar": ["none", "AI Toolkit RBAC primary"], "delete": [], "kept": []},
    {"email": "test-limited-contributor@preset.zone", "role": ["PUT", "PresetGamma"], "dar": ["PUT", "AI Toolkit RBAC limited"], "delete": [], "kept": ["Customer analysts"]},
    {"email": "test-limited-contributor-no-access@preset.zone", "role": ["PUT", "PresetGamma"], "dar": ["none", None], "delete": ["AI Toolkit RBAC limited-none"], "kept": []},
    {"email": "test-dashboard-viewer@preset.zone", "role": ["PUT", "PresetDashboardsOnly"], "dar": ["POST", "AI Toolkit RBAC dash"], "delete": ["AI Toolkit RBAC old-dash"], "kept": []},
    {"email": "test-dashboard-viewer-no-access@preset.zone", "status": "NOT_A_MEMBER"},
    {"email": "test-viewer@preset.zone", "role": ["PUT", "PresetReportsOnly"], "dar": ["POST", "AI Toolkit RBAC viewer"], "delete": [], "kept": []},
    {"email": "test-no-access@preset.zone", "role": ["PUT", "PresetNoAccess"], "dar": ["none", None], "delete": [], "kept": []},
]

RBAC_DRIVER = """
import * as rbac from %(module)s;
const fixture = %(fixture)s;
for (const list of Object.values(fixture.permissions)) {
  for (const permission of list) {
    for (const entry of Object.values(permission.acl ?? {})) if (entry.grants === 'DEFAULT') entry.grants = rbac.DEFAULT_GRANTS;
  }
}
const plan = rbac.planChanges(fixture);
const calls = [];
const states = {};
const api = {
  get: async (path) => {
    calls.push(['GET', path]);
    const name = decodeURIComponent(path.split('/permissions/')[1] ?? '');
    states[name] = (states[name] ?? 0) + 1;
    return { status: name.endsWith('viewer') ? 'FAILED' : states[name] > 1 ? 'APPLIED' : 'SYNCING' };
  },
  put: async (path, body) => { calls.push(['PUT', path, body]); return {}; },
  post: async (path, body) => { calls.push(['POST', path, body]); return {}; },
  delete: async (path) => { calls.push(['DELETE', path]); return {}; },
};
const discovery = { slug: 'qa-team', workspace: fixture.workspace };
const poll = { delay: 0, sleep: async () => {} };
const kept = await rbac.applyPlan(api, discovery, plan, { poll });
const keptCalls = calls.splice(0);
const replaced = await rbac.applyPlan(api, discovery, plan, { replaceExisting: true, poll });
const sent = [];
const client = rbac.managerApi({ managerUrl: 'https://manage.app-stg.preset.io', token: 't0k', referer: 'https://ws1.us1a.app-stg.preset.io/',
  send: async (method, url, request) => { sent.push({ method, url, headers: request.headers, body: request.body }); return { status: 200, json: {} }; } });
await client.get('/api/v1/teams/');
await client.put('/api/v1/teams/qa-team/permissions/x', { a: 1 });
console.log(JSON.stringify({ plan, table: rbac.formatPlan(plan), kept, keptCalls, replaced, deletes: calls.filter((call) => call[0] === 'DELETE'), sent }));
"""


@unittest.skipIf(NODE is None, "node is not installed")
class RbacScriptTests(unittest.TestCase):
    """NW-19: the plan-diff fixture, the apply rules, and the refusals."""

    def drive(self) -> dict[str, object]:
        source = RBAC_DRIVER % {"module": json.dumps(RBAC.as_uri()), "fixture": json.dumps(RBAC_FIXTURE)}
        result = node("--input-type=module", "-e", source)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_script_parses(self) -> None:
        result = node("--check", str(RBAC))
        self.assertEqual(0, result.returncode, result.stderr)

    def test_the_plan_matches_the_fixture(self) -> None:
        plan = self.drive()["plan"]
        summary = []
        for row in plan:
            if row["status"] == "NOT_A_MEMBER":
                summary.append({"email": row["email"], "status": "NOT_A_MEMBER"})
                continue
            summary.append(
                {
                    "email": row["email"],
                    "role": [row["role"]["action"], row["role"]["proposed"]],
                    "dar": [row["dar"]["action"], row["dar"]["name"]],
                    "delete": row["delete"],
                    "kept": row["kept"],
                }
            )
        self.assertEqual(RBAC_PLAN, summary)

    def test_apply_writes_only_the_plan_and_deletes_only_on_request(self) -> None:
        outcome = self.drive()
        kept = {row["email"]: row["status"] for row in outcome["kept"]["results"]}
        self.assertEqual("UNCHANGED", kept["test-primary-contributor@preset.zone"])
        self.assertEqual("NOT_A_MEMBER", kept["test-dashboard-viewer-no-access@preset.zone"])
        self.assertEqual("DAR_FAILED", kept["test-viewer@preset.zone"])
        self.assertEqual("UPDATED", kept["test-dashboard-viewer@preset.zone"])
        self.assertFalse([call for call in outcome["keptCalls"] if call[0] == "DELETE"])
        membership = next(call for call in outcome["keptCalls"] if call[1].endswith("/workspaces/42/membership"))
        self.assertEqual({"role_identifier": "PresetGamma", "user_id": 2}, membership[2])
        post = next(call for call in outcome["keptCalls"] if call[0] == "POST")
        self.assertEqual("/api/v1/teams/qa-team/permissions/", post[1])
        self.assertEqual(
            {"workspace_name": "rbac-ws", "type": "data_access_role", "grantees": [{"type": "USER", "identifier": "dash"}]},
            {key: post[2][key] for key in ("workspace_name", "type", "grantees")},
        )
        self.assertEqual(["dar:AI Toolkit RBAC dash"], list(post[2]["acl"]))
        self.assertEqual(
            sorted(["/api/v1/teams/qa-team/permissions/AI%20Toolkit%20RBAC%20limited-none",
                    "/api/v1/teams/qa-team/permissions/AI%20Toolkit%20RBAC%20old-dash"]),
            sorted(call[1] for call in outcome["deletes"]),
        )
        self.assertGreater(outcome["replaced"]["mutations"], outcome["kept"]["mutations"])

    def test_the_token_rides_in_bearer_and_csrf_with_a_referer_on_writes(self) -> None:
        read, write = self.drive()["sent"]
        self.assertEqual("Bearer t0k", read["headers"]["Authorization"])
        self.assertNotIn("X-CSRF-Token", read["headers"])
        self.assertEqual(("t0k", "https://ws1.us1a.app-stg.preset.io/"), (write["headers"]["X-CSRF-Token"], write["headers"]["Referer"]))
        self.assertEqual('{"a":1}', write["body"])

    def test_refuses_hosts_and_flags_before_any_browser(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            env = {"PATH": os.environ.get("PATH", ""), "HOME": home}
            for arguments, message in (
                (("--host", "https://ws1.us1a.app.preset.io/"), "refusing"),
                (("--host", "manage.app-stg.preset.io"), "not a staging or dev workspace host"),
                (("--host", "example.com"), "refusing"),
                (("--host", "localhost:8088"), "not a staging or dev workspace host"),
                (("--host", "ws1.us1a.app-stg.preset.io", "--replace-existing"), "--replace-existing needs --apply"),
                (("--host", "ws1.us1a.app-stg.preset.io"), "PRESET_STG_BOT_LOGIN"),
                ((), "missing --host"),
            ):
                with self.subTest(arguments=arguments):
                    result = node(str(RBAC), *arguments, cwd=Path(home), env=env)
                    self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                    self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
