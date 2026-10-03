"""The head-identity block in create-pr.md resolves only an unambiguous pushed head.

The block is extracted from the doc and run with bash against real temporary
repositories (a bare remote plus a work clone), so every STOP case is a real
git configuration rather than a mocked answer.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from create_pr_doc import fenced_block

BRANCH = "feat/x"


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=ENVIRONMENT,
    )
    return result.stdout.strip()


ENVIRONMENT = {
    **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def run_block(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=ENVIRONMENT,
    )


@unittest.skipUnless(shutil.which("git"), "git is required")
class HeadIdentityBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        base = Path(self._temporary.name).resolve()
        self.remote = base / "origin.git"
        self.work = base / "work"
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(self.remote)],
            check=True,
            env=ENVIRONMENT,
        )
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(self.work)], check=True, env=ENVIRONMENT
        )
        git(self.work, "remote", "add", "origin", str(self.remote))
        self.commit("base")
        git(self.work, "checkout", "-q", "-b", BRANCH)
        self.block = fenced_block("%(upstream:remoteref)")

    def commit(self, name: str) -> None:
        (self.work / f"{name}.txt").write_text(name)
        git(self.work, "add", ".")
        git(self.work, "commit", "-q", "-m", name)

    def push(self) -> None:
        git(self.work, "push", "-q", "-u", "origin", "HEAD")

    def identity(self) -> subprocess.CompletedProcess[str]:
        return run_block(self.block, self.work)

    def assert_stops(self, *fragments: str) -> None:
        result = self.identity()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertTrue(result.stdout.startswith("STOP:"), result.stdout + result.stderr)
        self.assertNotIn("remote=", result.stdout)
        for fragment in fragments:
            self.assertIn(fragment, result.stdout)

    def assert_resolves(self) -> None:
        result = self.identity()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(
            [
                "remote=origin",
                f"ref=refs/heads/{BRANCH}",
                f"sha={git(self.work, 'rev-parse', 'HEAD')}",
            ],
            result.stdout.splitlines(),
        )

    def test_pushed_branch_with_upstream_resolves_remote_ref_and_sha(self) -> None:
        self.push()
        self.assert_resolves()

    def test_push_default_current_and_upstream_still_resolve(self) -> None:
        self.push()
        for setting in ("current", "upstream", "simple"):
            with self.subTest(push_default=setting):
                git(self.work, "config", "push.default", setting)
                self.assert_resolves()

    def test_branch_that_was_never_pushed_stops(self) -> None:
        self.assert_stops()

    def test_renamed_push_ref_stops(self) -> None:
        self.push()
        git(self.work, "config", "remote.origin.push", f"refs/heads/{BRANCH}:refs/heads/other")
        self.assert_stops("renamed push ref")

    def test_push_default_remote_that_is_not_the_upstream_stops(self) -> None:
        self.push()
        other = self.remote.parent / "fork.git"
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(other)], check=True, env=ENVIRONMENT
        )
        git(self.work, "remote", "add", "fork", str(other))
        git(self.work, "config", "remote.pushDefault", "fork")
        self.assert_stops("fork")

    def test_local_commit_the_remote_lacks_stops(self) -> None:
        self.push()
        self.commit("unpushed")
        self.assert_stops()

    def test_branch_tracking_a_differently_named_upstream_stops_before_any_push(self) -> None:
        # `mine` was created from `origin/feature`: the identity block stops with a
        # renamed upstream ref, and the upstream stays origin/feature (nothing moved it).
        git(self.work, "push", "-q", "origin", "HEAD:refs/heads/feature")
        git(self.work, "fetch", "-q", "origin")
        git(self.work, "checkout", "-q", "-b", "mine", "--track", "origin/feature")
        self.assert_stops("renamed upstream ref")
        self.assertEqual(
            "origin/feature", git(self.work, "rev-parse", "--abbrev-ref", "mine@{upstream}")
        )

    def upstream_matches(self, remote: str = "origin") -> bool:
        """The owners' pre-push condition: upstream equals `<remote>/<branch>`."""
        branch = git(self.work, "symbolic-ref", "--short", "HEAD")
        upstream = git(self.work, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}")
        return upstream == f"{remote}/{branch}"

    def remote_refs(self) -> dict[str, str]:
        listing = git(self.remote, "for-each-ref", "--format=%(refname) %(objectname)")
        return dict(line.split(" ") for line in listing.splitlines())

    def test_branch_created_from_another_remote_branch_fails_the_prepush_condition(self) -> None:
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "fetch", "-q", "origin")
        git(self.work, "checkout", "-q", "-b", "topic", "--track", "origin/main")
        before = self.remote_refs()
        self.assertFalse(self.upstream_matches())
        self.assertEqual(before, self.remote_refs())

    def test_explicit_push_updates_only_the_branch_ref(self) -> None:
        git(self.work, "push", "-q", "origin", "main")
        self.push()
        git(self.work, "push", "-q", "origin", "main:refs/heads/other")
        git(self.work, "checkout", "-q", "main")
        self.commit("main-local")
        git(self.work, "checkout", "-q", "-b", "other", "--track", "origin/other")
        self.commit("other-local")
        git(self.work, "checkout", "-q", BRANCH)
        self.commit("feature-work")
        for setting in ("upstream", "matching"):
            with self.subTest(push_default=setting):
                git(self.work, "config", "push.default", setting)
                before = self.remote_refs()
                self.assertTrue(self.upstream_matches())
                git(self.work, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
                after = self.remote_refs()
                self.assertEqual(git(self.work, "rev-parse", "HEAD"), after[f"refs/heads/{BRANCH}"])
                for ref in ("refs/heads/main", "refs/heads/other"):
                    self.assertEqual(before[ref], after[ref])
                self.commit(f"more-{setting}")

    @unittest.skipUnless(shutil.which("zsh"), "zsh is required")
    def test_block_also_resolves_under_zsh(self) -> None:
        self.push()
        result = subprocess.run(
            ["zsh", "-c", self.block],
            cwd=self.work,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=ENVIRONMENT,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(
            [
                "remote=origin",
                f"ref=refs/heads/{BRANCH}",
                f"sha={git(self.work, 'rev-parse', 'HEAD')}",
            ],
            result.stdout.splitlines(),
        )

    def test_detached_head_stops(self) -> None:
        self.push()
        git(self.work, "checkout", "-q", "--detach")
        self.assert_stops("detached")


@unittest.skipUnless(shutil.which("git"), "git is required")
class HeadRepoNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name).resolve()
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(self.work)], check=True, env=ENVIRONMENT
        )
        git(self.work, "remote", "add", "origin", "https://example.invalid/placeholder")
        self.block = fenced_block("get-url --push")

    def head_repo(self) -> str:
        result = run_block(
            f'remote=origin\n{self.block}\nprintf "head_repo=[%s]\\n" "$head_repo"', self.work
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(1, result.stdout.count("head_repo=["), result.stdout)
        return result.stdout.split("head_repo=[", 1)[1].rstrip().removesuffix("]")

    def test_supported_url_forms_normalize_to_lowercase_owner_repo(self) -> None:
        for url in (
            "git@github.com:Apache/Superset.git",
            "https://github.com/Apache/Superset",
            "https://github.com/Apache/Superset.git",
            "ssh://git@github.com/Apache/Superset.git",
        ):
            with self.subTest(url=url):
                git(self.work, "remote", "set-url", "origin", url)
                self.assertEqual("apache/superset", self.head_repo())

    def test_unsupported_host_normalizes_to_empty(self) -> None:
        git(self.work, "remote", "set-url", "origin", "https://gitlab.com/o/r")
        self.assertEqual("", self.head_repo())

    def test_push_url_wins_over_fetch_url(self) -> None:
        git(self.work, "remote", "set-url", "origin", "https://github.com/Upstream/Repo")
        git(self.work, "remote", "set-url", "--push", "origin", "git@github.com:Fork/Repo.git")
        self.assertEqual("fork/repo", self.head_repo())


if __name__ == "__main__":
    unittest.main()
