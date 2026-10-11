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


if __name__ == "__main__":
    unittest.main()
