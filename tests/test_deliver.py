"""`bin/aitk deliver` commits, pushes and opens a draft PR only on recorded evidence.

Every case runs real git against a bare remote. `gh` is a stub first on PATH
that serves `repo view`, the paginated pulls lookup and `pr create` from a
state directory and logs each call, and a thin `git` wrapper answers
`remote get-url` with a github.com URL (the push itself goes to the local bare
remote). The head-identity and lookup cases carried over from the create-pr
block tests run the same scenarios against `aitk/deliver.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

from aitk.deliver import (
    DeliverOptions,
    DeliverStop,
    choose_pr,
    deliver,
    head_identity,
    head_repo,
    lookup_open_prs,
    normalize_head_repo,
)
from aitk.project_state import (
    initialize,
    record_gate,
    result_digest,
    review_from_envelopes,
    verify_run,
    working_tree_sha,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_GIT = shutil.which("git") or "git"
BRANCH = "feat/x"

GH_STUB = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

state = Path(os.environ["GH_STUB_DIR"])
args = sys.argv[1:]
with (state / "calls.jsonl").open("a") as handle:
    handle.write(json.dumps(args) + "\n")
if os.environ.get("GH_STUB_EXIT"):
    sys.exit(int(os.environ["GH_STUB_EXIT"]))
pulls_file = state / "pulls.json"
pulls = json.loads(pulls_file.read_text()) if pulls_file.exists() else []
repo = json.loads((state / "repo.json").read_text())
if args[:2] == ["repo", "view"]:
    print(json.dumps(repo))
    sys.exit(0)
if args[:1] == ["api"]:
    pages = sorted(state.glob("page-*.json"))
    if pages:
        for page in pages:
            sys.stdout.write(page.read_text())
    else:
        size = int(os.environ.get("GH_STUB_PAGE_SIZE", "100"))
        for start in range(0, max(len(pulls), 1), size):
            sys.stdout.write(json.dumps(pulls[start:start + size]))
    sys.exit(0)
if args[:2] == ["pr", "create"]:
    mode = os.environ.get("GH_STUB_CREATE", "")
    if mode == "fail-before":
        print("HTTP 502", file=sys.stderr)
        sys.exit(1)
    value = lambda flag: args[args.index(flag) + 1]
    owner, ref = value("--head").split(":", 1)
    name = repo["nameWithOwner"].split("/", 1)[1]
    number = 100 + len(pulls)
    url = f"https://github.com/{repo['nameWithOwner']}/pull/{number}"
    pulls.append({
        "number": number,
        "draft": "--draft" in args,
        "html_url": url,
        "base": {"ref": value("--base")},
        "head": {"ref": ref, "repo": {"full_name": f"{owner}/{name}"}},
    })
    pulls_file.write_text(json.dumps(pulls))
    if mode == "fail-after":
        print("connection reset", file=sys.stderr)
        sys.exit(1)
    print(url)
    sys.exit(0)
sys.exit(2)
"""

GIT_WRAPPER = """#!/bin/bash
if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ -n "$GIT_STUB_PUSH_URL" ]; then
  printf '%s\\n' "$GIT_STUB_PUSH_URL"
  exit 0
fi
exec "$REAL_GIT" "$@"
"""


def base_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.pop("AITK_PR_READY", None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
    )
    return environment


ENVIRONMENT = base_environment()


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [REAL_GIT, "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=ENVIRONMENT
    )
    return result.stdout.strip()


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class Fixture:
    """A bare `origin`, a work clone on `feat/x`, a stub gh, and a snapshot."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.remote = base / "origin.git"
        self.work = base / "work"
        self.bin = base / "bin"
        self.gh_state = base / "gh"
        self.project = self.work / "PROJECT.md"
        self.body = base / "body.md"
        for directory in (self.bin, self.gh_state):
            directory.mkdir()
        write_executable(self.bin / "gh", GH_STUB)
        write_executable(self.bin / "git", GIT_WRAPPER)
        (self.gh_state / "repo.json").write_text(
            json.dumps({"nameWithOwner": "Owner/Repo", "defaultBranchRef": {"name": "main"}, "isFork": False})
        )
        self.body.write_text("## Summary\nAdds x.\n")
        subprocess.run([REAL_GIT, "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True, env=ENVIRONMENT)
        subprocess.run([REAL_GIT, "init", "-q", "-b", "main", str(self.work)], check=True, env=ENVIRONMENT)
        git(self.work, "remote", "add", "origin", str(self.remote))
        self.commit("base")
        git(self.work, "push", "-q", "-u", "origin", "main")
        git(self.work, "remote", "set-head", "origin", "main")
        git(self.work, "checkout", "-q", "-b", BRANCH)
        self.env = {
            **ENVIRONMENT,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "REAL_GIT": REAL_GIT,
            "GH_STUB_DIR": str(self.gh_state),
            "GIT_STUB_PUSH_URL": "https://github.com/Owner/Repo.git",
        }
        initialize(self.project, "create-feature", "STANDARD", "S")

    def commit(self, name: str) -> None:
        (self.work / f"{name}.txt").write_text(name)
        git(self.work, "add", f"{name}.txt")
        git(self.work, "commit", "-q", "-m", name)

    def change(self, name: str = "feature") -> None:
        (self.work / f"{name}.txt").write_text(f"{name}\n")

    def verify(self, command: str = "test -f feature.txt", strength: str | None = "STRONG"):
        return verify_run(self.project, command, cwd=self.work, strength=strength)

    def review(self) -> None:
        result = {"status": "completed", "summary": "clean", "findings": [], "verification": ["feature.txt"]}
        envelope = {
            "command": "model-run",
            "dry_run": False,
            "route": "review",
            "boundary": "review.independent",
            "provider": "codex",
            "result": result,
            "result_digest": result_digest(result),
            "reviewed_tree": working_tree_sha(self.work),
            "error": None,
        }
        record_gate(self.project, "review", "PASS", review=review_from_envelopes([envelope]))

    def ready(self) -> None:
        self.change()
        self.verify()
        self.review()

    def options(self, **changes: object) -> DeliverOptions:
        values: dict[str, object] = {
            "cwd": self.work,
            "project_file": self.project,
            "workflow": "create-feature",
            "title": "Add the x feature",
            "body_file": self.body,
            "env": self.env,
        }
        values.update(changes)
        return DeliverOptions(**values)  # type: ignore[arg-type]

    def calls(self) -> list[list[str]]:
        log = self.gh_state / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def pulls(self) -> list[dict[str, object]]:
        path = self.gh_state / "pulls.json"
        return json.loads(path.read_text()) if path.exists() else []

    def remote_refs(self) -> dict[str, str]:
        listing = git(self.remote, "for-each-ref", "--format=%(refname) %(objectname)")
        return dict(line.split(" ") for line in listing.splitlines())

    def cli(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "bin/aitk"), "deliver", *args],
            cwd=self.work,
            capture_output=True,
            text=True,
            check=False,
            env={**self.env, **env},
        )


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "git and bash are required")
class DeliverTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.fixture = Fixture(Path(self._temporary.name).resolve())

    def assert_untouched(self, head: str, remote: dict[str, str]) -> None:
        self.assertEqual(head, git(self.fixture.work, "rev-parse", "HEAD"))
        self.assertEqual(remote, self.fixture.remote_refs())
        self.assertEqual([], self.fixture.calls())


class RefusalTests(DeliverTestCase):
    """With the hooks out of the picture, deliver itself refuses (exit 1, nothing changed)."""

    def refuse(self, *fragments: str) -> None:
        head, remote = git(self.fixture.work, "rev-parse", "HEAD"), self.fixture.remote_refs()
        result = self.fixture.cli(
            "--workflow", "create-feature", "--title", "Add x", "--body-file", str(self.fixture.body), "--json"
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("refused", payload["status"])
        for fragment in fragments:
            self.assertIn(fragment, payload["reason"])
        self.assert_untouched(head, remote)

    def test_refuses_without_a_review_record(self) -> None:
        self.fixture.change()
        self.fixture.verify()
        self.refuse("review=unrecorded")
        record_gate(self.fixture.project, "review", "PASS")
        self.refuse("no reviewer record")

    def test_refuses_without_a_verification_run(self) -> None:
        self.fixture.change()
        self.fixture.review()
        self.refuse("verification=unrecorded")
        record_gate(self.fixture.project, "verification", "PASS")
        self.refuse("no recorded run")

    def test_refuses_a_non_zero_exit(self) -> None:
        self.fixture.change()
        self.fixture.review()
        self.fixture.verify("test -f missing.txt")
        self.refuse("exited 1")

    def test_refuses_a_tree_that_changed_after_the_run(self) -> None:
        self.fixture.ready()
        (self.fixture.work / "feature.txt").write_text("edited after the run\n")
        self.refuse("changed after the verification run")

    def test_refuses_a_tree_that_changed_after_the_review(self) -> None:
        self.fixture.change()
        self.fixture.review()
        (self.fixture.work / "feature.txt").write_text("fixed after the review\n")
        self.fixture.verify()
        self.refuse("changed after the review")

    def test_refuses_partial_strength_and_protected_branches(self) -> None:
        self.fixture.change()
        self.fixture.verify(strength="PARTIAL")
        self.fixture.review()
        self.refuse("deliver needs STRONG")
        self.fixture.verify()
        git(self.fixture.work, "checkout", "-q", "main")
        self.refuse("never deliver from main")
        git(self.fixture.work, "checkout", "-q", "--detach")
        self.refuse("detached HEAD")

    def test_ready_needs_the_users_override_and_still_needs_review(self) -> None:
        self.fixture.change()
        self.fixture.verify()
        head, remote = git(self.fixture.work, "rev-parse", "HEAD"), self.fixture.remote_refs()
        refused = deliver(self.fixture.options(ready=True))
        self.assertEqual("refused", refused.status)
        self.assertIn("explicit request in words", refused.reason)
        unreviewed = deliver(self.fixture.options(ready=True, env={**self.fixture.env, "AITK_PR_READY": "1"}))
        self.assertEqual("refused", unreviewed.status)
        self.assertIn("review=unrecorded", unreviewed.reason)
        self.assert_untouched(head, remote)


class DeliveryTests(DeliverTestCase):
    def test_commits_pushes_and_opens_a_draft_pr(self) -> None:
        self.fixture.ready()
        result = deliver(self.fixture.options())
        self.assertEqual("delivered", result.status, result.reason)
        self.assertTrue(result.committed and result.pushed)
        head = git(self.fixture.work, "rev-parse", "HEAD")
        self.assertEqual(head, self.fixture.remote_refs()[f"refs/heads/{BRANCH}"])
        self.assertEqual("origin/" + BRANCH, git(self.fixture.work, "rev-parse", "--abbrev-ref", f"{BRANCH}@{{upstream}}"))
        self.assertEqual(["feature.txt"], git(self.fixture.work, "show", "--name-only", "--format=", "HEAD").split())
        self.assertNotIn("PROJECT.md", git(self.fixture.work, "ls-tree", "-r", "--name-only", "HEAD"))
        create = next(call for call in self.fixture.calls() if call[:2] == ["pr", "create"])
        self.assertIn("--draft", create)
        self.assertEqual(f"owner:{BRANCH}", create[create.index("--head") + 1])
        self.assertEqual("main", create[create.index("--base") + 1])
        self.assertEqual({"number": 100, "draft": True, "existing": False}, {
            key: result.pr[key] for key in ("number", "draft", "existing")
        })
        record = self.fixture.project.read_text()
        self.assertIn("## PR Created", record)
        self.assertIn("Draft: yes", record)
        self.assertIn("Delivered as: draft PR #100", record)
        self.assertIn("verified by `test -f feature.txt` (exit 0, STRONG)", record)

    def test_a_rerun_after_a_crash_reuses_the_pr(self) -> None:
        self.fixture.ready()
        first = deliver(self.fixture.options())
        self.assertEqual("PR Created", first.reason)
        # The session died before PROJECT.md recorded the PR.
        text = self.fixture.project.read_text()
        self.fixture.project.write_text(text[: text.index("## PR Created")])
        result = self.fixture.cli(
            "--workflow", "create-feature", "--title", "Add the x feature", "--body-file", str(self.fixture.body)
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("## PR Exists"), result.stdout)
        self.assertEqual(1, sum(call[:2] == ["pr", "create"] for call in self.fixture.calls()))
        self.assertEqual(1, len(self.fixture.pulls()))
        self.assertIn("Existing: yes", self.fixture.project.read_text())
        # A third run writes nothing new.
        before = self.fixture.project.read_text()
        self.assertEqual("delivered", deliver(self.fixture.options()).status)
        self.assertEqual(before, self.fixture.project.read_text())

    def test_a_create_whose_answer_was_lost_is_reconciled_by_lookup(self) -> None:
        self.fixture.ready()
        result = deliver(self.fixture.options(env={**self.fixture.env, "GH_STUB_CREATE": "fail-after"}))
        self.assertEqual("delivered", result.status, result.reason)
        self.assertIn("reconciled", result.reason)
        self.assertEqual(1, len(self.fixture.pulls()))

    def test_a_crash_between_push_and_pr_resumes_without_a_second_commit(self) -> None:
        self.fixture.ready()
        failed = deliver(self.fixture.options(env={**self.fixture.env, "GH_STUB_CREATE": "fail-before"}))
        self.assertEqual("failed", failed.status)
        self.assertIn("re-run the same", failed.reason)
        self.assertTrue(failed.pushed)
        commits = git(self.fixture.work, "rev-list", "--count", "HEAD")
        again = deliver(self.fixture.options())
        self.assertEqual("delivered", again.status, again.reason)
        self.assertFalse(again.committed or again.pushed)
        self.assertEqual(commits, git(self.fixture.work, "rev-list", "--count", "HEAD"))
        self.assertEqual(1, len(self.fixture.pulls()))

    def test_ready_opens_a_non_draft_pr_with_the_override(self) -> None:
        self.fixture.ready()
        result = deliver(self.fixture.options(ready=True, env={**self.fixture.env, "AITK_PR_READY": "1"}))
        self.assertEqual("delivered", result.status, result.reason)
        create = next(call for call in self.fixture.calls() if call[:2] == ["pr", "create"])
        self.assertNotIn("--draft", create)
        self.assertFalse(result.pr["draft"])
        self.assertIn("Draft: no", self.fixture.project.read_text())

    def test_no_pr_stops_after_the_push(self) -> None:
        self.fixture.ready()
        result = deliver(self.fixture.options(no_pr=True, title=None, body_file=None, message="Add x"))
        self.assertEqual("delivered", result.status, result.reason)
        self.assertIsNone(result.pr)
        self.assertEqual([], self.fixture.calls())
        self.assertEqual(git(self.fixture.work, "rev-parse", "HEAD"), self.fixture.remote_refs()[f"refs/heads/{BRANCH}"])
        record = self.fixture.project.read_text()
        self.assertIn("## Delivered", record)
        self.assertIn("pushed — awaiting PR request (--no-pr)", record)

    def test_an_existing_pr_on_another_base_is_a_conflict(self) -> None:
        self.fixture.ready()
        (self.fixture.gh_state / "pulls.json").write_text(json.dumps([{
            "number": 7, "draft": True, "html_url": "https://github.com/owner/repo/pull/7",
            "base": {"ref": "6.1-release"}, "head": {"ref": BRANCH, "repo": {"full_name": "owner/repo"}},
        }]))
        result = deliver(self.fixture.options())
        self.assertEqual("held", result.status)
        self.assertIn("PR conflict: open PR #7", result.reason)
        self.assertTrue(result.pushed, "the phase is still committed and pushed")
        self.assertFalse(any(call[:2] == ["pr", "create"] for call in self.fixture.calls()))

    def test_a_chained_run_never_opens_a_pr_from_a_fork(self) -> None:
        self.fixture.ready()
        fork = {**self.fixture.env, "GIT_STUB_PUSH_URL": "git@github.com:someone/Repo.git"}
        held = deliver(self.fixture.options(env=fork))
        self.assertEqual("held", held.status)
        self.assertIn("is not the base repository", held.reason)
        self.assertFalse(held.committed or held.pushed)
        standalone = deliver(self.fixture.options(env=fork, workflow=None))
        self.assertEqual("delivered", standalone.status, standalone.reason)
        create = next(call for call in self.fixture.calls() if call[:2] == ["pr", "create"])
        self.assertEqual(f"someone:{BRANCH}", create[create.index("--head") + 1])

    def test_the_default_branch_is_refused_before_anything_changes(self) -> None:
        (self.fixture.gh_state / "repo.json").write_text(
            json.dumps({"nameWithOwner": "Owner/Repo", "defaultBranchRef": {"name": BRANCH}, "isFork": False})
        )
        self.fixture.ready()
        head, remote = git(self.fixture.work, "rev-parse", "HEAD"), self.fixture.remote_refs()
        result = deliver(self.fixture.options())
        self.assertEqual("refused", result.status)
        self.assertIn("default branch", result.reason)
        self.assertEqual(head, git(self.fixture.work, "rev-parse", "HEAD"))
        self.assertEqual(remote, self.fixture.remote_refs())


class PushTargetTests(DeliverTestCase):
    """Upstream, then pushRemote, then pushDefault, then origin; anything else holds."""

    def second_remote(self, name: str = "fork") -> Path:
        path = self.fixture.base / f"{name}.git"
        subprocess.run([REAL_GIT, "init", "-q", "--bare", "-b", "main", str(path)], check=True, env=ENVIRONMENT)
        git(self.fixture.work, "remote", "add", name, str(path))
        return path

    def no_pr(self):
        return deliver(self.fixture.options(no_pr=True, title=None, body_file=None, message="Add x"))

    def pushed_to(self, remote: Path) -> str:
        return git(remote, "rev-parse", f"refs/heads/{BRANCH}")

    def test_no_upstream_pushes_to_origin_and_sets_it(self) -> None:
        self.fixture.ready()
        result = self.no_pr()
        self.assertEqual(("delivered", "origin"), (result.status, result.remote), result.reason)
        self.assertEqual(git(self.fixture.work, "rev-parse", "HEAD"), self.pushed_to(self.fixture.remote))

    def test_push_remote_then_push_default_win_over_origin(self) -> None:
        fork = self.second_remote()
        git(self.fixture.work, "config", "remote.pushDefault", "fork")
        mirror = self.second_remote("mirror")
        git(self.fixture.work, "config", f"branch.{BRANCH}.pushRemote", "mirror")
        self.fixture.ready()
        result = self.no_pr()
        self.assertEqual("mirror", result.remote, result.reason)
        self.assertEqual(git(self.fixture.work, "rev-parse", "HEAD"), self.pushed_to(mirror))
        self.assertNotIn(f"refs/heads/{BRANCH}", git(fork, "for-each-ref", "--format=%(refname)"))

    def test_push_default_is_used_without_a_push_remote(self) -> None:
        fork = self.second_remote()
        git(self.fixture.work, "config", "remote.pushDefault", "fork")
        self.fixture.ready()
        self.assertEqual("fork", self.no_pr().remote)
        self.assertEqual(git(self.fixture.work, "rev-parse", "HEAD"), self.pushed_to(fork))

    def test_no_candidate_is_an_ambiguous_target_and_nothing_is_committed(self) -> None:
        git(self.fixture.work, "remote", "rename", "origin", "upstream")
        self.fixture.ready()
        head = git(self.fixture.work, "rev-parse", "HEAD")
        result = self.no_pr()
        self.assertEqual("held", result.status)
        self.assertIn("ambiguous push target", result.reason)
        self.assertEqual(head, git(self.fixture.work, "rev-parse", "HEAD"))

    def test_a_branch_tracking_another_remote_branch_holds_before_any_push(self) -> None:
        git(self.fixture.work, "push", "-q", "origin", "HEAD:refs/heads/feature")
        git(self.fixture.work, "fetch", "-q", "origin")
        git(self.fixture.work, "checkout", "-q", "-b", "mine", "--track", "origin/feature")
        self.fixture.ready()
        before = self.fixture.remote_refs()
        result = self.no_pr()
        self.assertEqual("held", result.status)
        self.assertIn("renamed upstream ref", result.reason)
        self.assertEqual(before, self.fixture.remote_refs())
        self.assertEqual("origin/feature", git(self.fixture.work, "rev-parse", "--abbrev-ref", "mine@{upstream}"))

    def test_a_branch_created_from_the_remote_default_holds(self) -> None:
        git(self.fixture.work, "checkout", "-q", "-b", "topic", "--track", "origin/main")
        self.fixture.ready()
        before = self.fixture.remote_refs()
        result = self.no_pr()
        self.assertEqual("held", result.status)
        self.assertEqual(before, self.fixture.remote_refs())

    def test_push_remote_differing_from_the_upstream_holds(self) -> None:
        git(self.fixture.work, "push", "-q", "-u", "origin", "HEAD")
        self.second_remote()
        git(self.fixture.work, "config", "remote.pushDefault", "fork")
        self.fixture.ready()
        result = self.no_pr()
        self.assertEqual("held", result.status)
        self.assertIn("push remote fork differs from upstream remote origin", result.reason)

    def test_a_renamed_push_ref_holds(self) -> None:
        git(self.fixture.work, "push", "-q", "-u", "origin", "HEAD")
        git(self.fixture.work, "config", "remote.origin.push", f"refs/heads/{BRANCH}:refs/heads/other")
        self.fixture.ready()
        result = self.no_pr()
        self.assertEqual("held", result.status)
        self.assertIn("renamed push ref", result.reason)

    def test_the_push_moves_only_the_branch_ref(self) -> None:
        git(self.fixture.work, "push", "-q", "-u", "origin", "HEAD")
        git(self.fixture.work, "push", "-q", "origin", "main:refs/heads/other")
        git(self.fixture.work, "checkout", "-q", "main")
        self.fixture.commit("main-local")
        git(self.fixture.work, "checkout", "-q", "-b", "other", "--track", "origin/other")
        self.fixture.commit("other-local")
        git(self.fixture.work, "checkout", "-q", BRANCH)
        for setting in ("upstream", "matching"):
            with self.subTest(push_default=setting):
                git(self.fixture.work, "config", "push.default", setting)
                self.fixture.change(f"work-{setting}")
                self.fixture.verify(f"test -f work-{setting}.txt")
                self.fixture.review()
                before = self.fixture.remote_refs()
                result = self.no_pr()
                self.assertEqual("delivered", result.status, result.reason)
                after = self.fixture.remote_refs()
                self.assertEqual(git(self.fixture.work, "rev-parse", "HEAD"), after[f"refs/heads/{BRANCH}"])
                for ref in ("refs/heads/main", "refs/heads/other"):
                    self.assertEqual(before[ref], after[ref])


class HeadIdentityTests(DeliverTestCase):
    """The six STOP cases of the create-pr identity block, against deliver.head_identity."""

    def push(self) -> None:
        git(self.fixture.work, "push", "-q", "-u", "origin", "HEAD")

    def assert_stops(self, *fragments: str) -> None:
        with self.assertRaises(DeliverStop) as raised:
            head_identity(self.fixture.work, ENVIRONMENT)
        self.assertTrue(raised.exception.reason.startswith("STOP:"), raised.exception.reason)
        for fragment in fragments:
            self.assertIn(fragment, raised.exception.reason)

    def assert_resolves(self) -> None:
        self.assertEqual(
            {"remote": "origin", "ref": f"refs/heads/{BRANCH}", "sha": git(self.fixture.work, "rev-parse", "HEAD")},
            head_identity(self.fixture.work, ENVIRONMENT),
        )

    def test_pushed_branch_with_upstream_resolves(self) -> None:
        self.push()
        self.assert_resolves()

    def test_push_default_current_upstream_and_simple_still_resolve(self) -> None:
        self.push()
        for setting in ("current", "upstream", "simple"):
            with self.subTest(push_default=setting):
                git(self.fixture.work, "config", "push.default", setting)
                self.assert_resolves()

    def test_a_branch_that_was_never_pushed_stops(self) -> None:
        self.assert_stops("no upstream")

    def test_a_renamed_push_ref_stops(self) -> None:
        self.push()
        git(self.fixture.work, "config", "remote.origin.push", f"refs/heads/{BRANCH}:refs/heads/other")
        self.assert_stops("renamed push ref")

    def test_a_push_default_remote_that_is_not_the_upstream_stops(self) -> None:
        self.push()
        other = self.fixture.base / "fork.git"
        subprocess.run([REAL_GIT, "init", "-q", "--bare", "-b", "main", str(other)], check=True, env=ENVIRONMENT)
        git(self.fixture.work, "remote", "add", "fork", str(other))
        git(self.fixture.work, "config", "remote.pushDefault", "fork")
        self.assert_stops("fork")

    def test_a_local_commit_the_remote_lacks_stops(self) -> None:
        self.push()
        self.fixture.commit("unpushed")
        self.assert_stops("HEAD differs")

    def test_a_branch_tracking_a_differently_named_upstream_stops(self) -> None:
        git(self.fixture.work, "push", "-q", "origin", "HEAD:refs/heads/feature")
        git(self.fixture.work, "fetch", "-q", "origin")
        git(self.fixture.work, "checkout", "-q", "-b", "mine", "--track", "origin/feature")
        self.assert_stops("renamed upstream ref")

    def test_a_detached_head_stops(self) -> None:
        self.push()
        git(self.fixture.work, "checkout", "-q", "--detach")
        with self.assertRaises(DeliverStop) as raised:
            head_identity(self.fixture.work, ENVIRONMENT)
        self.assertIn("detached HEAD", raised.exception.reason)


class HeadRepoTests(unittest.TestCase):
    def test_supported_url_forms_normalize_to_lowercase_owner_repo(self) -> None:
        for url in (
            "git@github.com:Apache/Superset.git",
            "https://github.com/Apache/Superset",
            "https://github.com/Apache/Superset.git",
            "ssh://git@github.com/Apache/Superset.git",
        ):
            with self.subTest(url=url):
                self.assertEqual("apache/superset", normalize_head_repo(url))

    def test_unsupported_hosts_normalize_to_empty(self) -> None:
        for url in ("https://gitlab.com/o/r", "/srv/git/repo.git", "https://github.com/only-owner"):
            with self.subTest(url=url):
                self.assertEqual("", normalize_head_repo(url))

    def test_push_url_wins_over_fetch_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            subprocess.run([REAL_GIT, "init", "-q", "-b", "main", str(work)], check=True, env=ENVIRONMENT)
            git(work, "remote", "add", "origin", "https://github.com/Upstream/Repo")
            git(work, "remote", "set-url", "--push", "origin", "git@github.com:Fork/Repo.git")
            self.assertEqual("fork/repo", head_repo(work, "origin", ENVIRONMENT))


class OpenPullLookupTests(DeliverTestCase):
    """The paginated lookup keeps only this head, across every page."""

    @staticmethod
    def pull(number: int, ref: str, repo: str | None, base: str = "main", draft: bool = False) -> dict:
        return {
            "number": number,
            "draft": draft,
            "html_url": f"https://github.com/o/r/pull/{number}",
            "base": {"ref": base},
            "head": {"ref": ref, "repo": None if repo is None else {"full_name": repo}},
        }

    def write_pages(self, *pages: object) -> None:
        for index, page in enumerate(pages, 1):
            text = page if isinstance(page, str) else json.dumps(page)
            (self.fixture.gh_state / f"page-{index}.json").write_text(text)

    def lookup(self, branch: str = BRANCH, **env: str) -> list[dict[str, object]]:
        return lookup_open_prs(
            self.fixture.work, "owner/repo", "owner", branch, "owner/repo", {**self.fixture.env, **env}
        )

    def test_reads_every_page_and_keeps_only_this_head(self) -> None:
        forks = [self.pull(number, BRANCH, f"fork-{number}/r") for number in range(1, 11)]
        self.write_pages(
            forks,
            [
                self.pull(11, BRANCH, "Owner/Repo"),
                self.pull(12, BRANCH, "owner/repo", base="6.1-release", draft=True),
                self.pull(13, BRANCH, None),
                self.pull(14, "feat/other", "owner/repo"),
            ],
        )
        self.assertEqual([11, 12], [row["number"] for row in self.lookup()])
        self.assertEqual("6.1-release", self.lookup()[1]["base"])

    def test_the_filter_reads_its_arguments_not_the_ambient_environment(self) -> None:
        # The shell block's bug class: a filter that read env.BRANCH matched nothing
        # (or the wrong head) unless the caller exported the right values.
        self.write_pages([self.pull(51, BRANCH, "owner/repo"), self.pull(52, "other", "fork/repo")])
        stale = {"BRANCH": "other", "HEAD_REPO": "fork/repo"}
        self.assertEqual([51], [row["number"] for row in self.lookup(**stale)])

    def test_branch_names_with_quotes_match_exactly(self) -> None:
        self.write_pages([self.pull(21, 'a"b', "owner/repo"), self.pull(22, "ab", "owner/repo")])
        self.assertEqual([21], [row["number"] for row in self.lookup('a"b')])

    def test_passes_the_documented_query_parameters(self) -> None:
        self.write_pages([self.pull(41, BRANCH, "owner/repo")])
        self.lookup()
        argv = self.fixture.calls()[-1]
        self.assertEqual(["api", "--paginate", "-X", "GET", "repos/owner/repo/pulls"], argv[:5])
        for value in ("state=open", "per_page=100", f"head=owner:{BRANCH}"):
            with self.subTest(parameter=value):
                self.assertEqual("-f", argv[argv.index(value) - 1])

    def test_a_gh_failure_a_bad_page_or_a_short_row_is_indeterminate(self) -> None:
        self.write_pages([self.pull(31, BRANCH, "owner/repo")])
        with self.assertRaisesRegex(DeliverStop, "indeterminate lookup: gh exited 4"):
            self.lookup(GH_STUB_EXIT="4")
        self.write_pages([self.pull(32, BRANCH, "owner/repo")], "not json")
        with self.assertRaisesRegex(DeliverStop, "indeterminate lookup"):
            self.lookup()
        short = self.pull(33, BRANCH, "owner/repo")
        del short["html_url"]
        self.write_pages([short])
        (self.fixture.gh_state / "page-2.json").unlink()
        with self.assertRaisesRegex(DeliverStop, "missing a field"):
            self.lookup()

    def test_row_rules_reuse_one_refuse_ambiguity_and_respect_an_explicit_base(self) -> None:
        one = {"number": 1, "draft": True, "base": "main", "url": "u1"}
        other = {"number": 2, "draft": False, "base": "6.1-release", "url": "u2"}
        self.assertEqual(one, choose_pr([one, other], "main", explicit_base=False, chained=True, head="o:b"))
        with self.assertRaisesRegex(DeliverStop, "PR conflict: open PRs #1, #3"):
            choose_pr([one, dict(one, number=3)], "main", explicit_base=False, chained=False, head="o:b")
        for chained, explicit in ((True, True), (False, False)):
            with self.subTest(chained=chained, explicit=explicit):
                with self.assertRaisesRegex(DeliverStop, "targets 6.1-release; this run resolved main"):
                    choose_pr([other], "main", explicit_base=explicit, chained=chained, head="o:b")
        self.assertIsNone(choose_pr([other], "main", explicit_base=True, chained=False, head="o:b"))
        self.assertIsNone(choose_pr([], "main", explicit_base=False, chained=True, head="o:b"))


if __name__ == "__main__":
    unittest.main()
