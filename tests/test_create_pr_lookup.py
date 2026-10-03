"""The open-PR lookup block in create-pr.md selects only this head, across pages.

The block is extracted from the doc and run through bash with a stub `gh` first
on PATH. The stub applies the real `--jq` filter with `jq` to each fixture page,
inheriting its environment unchanged, so a filter that reads `env.BRANCH` only
works when the block passes those variables to `gh` the way the doc says.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest

from create_pr_doc import fenced_block

BLOCK_START = 'BRANCH="$branch" HEAD_REPO="$head_repo" gh api --paginate -X GET'
ENV_PREFIX = 'BRANCH="$branch" HEAD_REPO="$head_repo" '

GH_STUB = r"""#!/usr/bin/env bash
paginate=0; method=0; filter=""
args=("$@")
printf '%s\n' "${args[@]}" > "$FIXTURE_DIR/argv.txt"
[ -z "$GH_STUB_EXIT" ] || exit "$GH_STUB_EXIT"
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    --paginate) paginate=1 ;;
    -X) [ "${args[i+1]}" = "GET" ] && method=1 ;;
    --jq) filter="${args[i+1]}" ;;
  esac
done
[ "$paginate" = 1 ] && [ "$method" = 1 ] && [ -n "$filter" ] || exit 2
for page in "$FIXTURE_DIR"/page-*.json; do
  jq -r "$filter" "$page" || exit 3
done
"""


def pull(number: int, ref: str, repo: str | None, base: str = "main", draft: bool = False) -> dict:
    return {
        "number": number,
        "draft": draft,
        "html_url": f"https://github.com/o/r/pull/{number}",
        "base": {"ref": base},
        "head": {"ref": ref, "repo": None if repo is None else {"full_name": repo}},
    }


def row(number: int, base: str, draft: bool = False) -> str:
    return f"{number}\t{str(draft).lower()}\t{base}\thttps://github.com/o/r/pull/{number}"


@unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "jq and bash are required")
class OpenPullLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.bin = self.root / "bin"
        self.pages = self.root / "pages"
        self.bin.mkdir()
        self.pages.mkdir()
        stub = self.bin / "gh"
        stub.write_text(GH_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.block = fenced_block("gh api --paginate -X GET")

    def write_pages(self, *pages: list[dict]) -> None:
        for index, page in enumerate(pages, 1):
            (self.pages / f"page-{index}.json").write_text(json.dumps(page))

    def lookup(
        self,
        block: str | None = None,
        branch: str = "feat/x",
        head_repo: str = "owner/repo",
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        # Lowercase variables are assigned but never exported, as in the doc's flow.
        script = (
            f"branch={shlex.quote(branch)}\nhead_repo={shlex.quote(head_repo)}\n"
            "base_repo=owner/repo\nhead_owner=owner\n"
            f"{self.block if block is None else block}"
        )
        environment = {
            key: value for key, value in os.environ.items() if key not in {"BRANCH", "HEAD_REPO"}
        }
        environment["PATH"] = f"{self.bin}{os.pathsep}{environment['PATH']}"
        environment["FIXTURE_DIR"] = str(self.pages)
        environment.update(extra_environment or {})
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=environment,
        )

    def paged_fixture(self) -> None:
        forks = [pull(number, "feat/x", f"fork-{number}/r") for number in range(1, 11)]
        self.write_pages(
            forks,
            [
                pull(11, "feat/x", "Owner/Repo"),
                pull(12, "feat/x", "owner/repo", base="6.1-release", draft=True),
                pull(13, "feat/x", None),
                pull(14, "feat/other", "owner/repo"),
            ],
        )

    def test_lookup_uses_the_documented_environment_prefix(self) -> None:
        self.assertTrue(self.block.startswith(BLOCK_START), self.block)

    def test_lookup_reads_every_page_and_keeps_only_this_head(self) -> None:
        self.paged_fixture()
        result = self.lookup()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [row(11, "main"), row(12, "6.1-release", draft=True)], result.stdout.splitlines()
        )

    def test_without_the_environment_prefix_nothing_matches(self) -> None:
        self.paged_fixture()
        self.assertIn(ENV_PREFIX, self.block)
        result = self.lookup(block=self.block.replace(ENV_PREFIX, "", 1))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_branch_names_with_quotes_round_trip_through_the_environment(self) -> None:
        self.write_pages(
            [pull(21, 'a"b', "owner/repo"), pull(22, "ab", "owner/repo")],
        )
        result = self.lookup(branch='a"b')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([row(21, "main")], result.stdout.splitlines())

    def test_lookup_passes_the_documented_query_parameters(self) -> None:
        self.write_pages([pull(41, "feat/x", "owner/repo")])
        result = self.lookup(branch="feat/x")
        self.assertEqual(0, result.returncode, result.stderr)
        argv = (self.pages / "argv.txt").read_text().splitlines()
        self.assertIn("repos/owner/repo/pulls", argv)
        for flag, value in (
            ("-f", "state=open"),
            ("-f", "per_page=100"),
            ("-f", "head=owner:feat/x"),
        ):
            with self.subTest(parameter=value):
                self.assertIn(value, argv)
                self.assertEqual(flag, argv[argv.index(value) - 1])

    def test_a_gh_failure_is_visible_to_the_caller(self) -> None:
        self.write_pages([pull(31, "feat/x", "owner/repo")])
        result = self.lookup(extra_environment={"GH_STUB_EXIT": "4"})
        self.assertEqual(4, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_a_bad_page_is_visible_to_the_caller(self) -> None:
        self.write_pages([pull(32, "feat/x", "owner/repo")])
        (self.pages / "page-2.json").write_text("not json")
        result = self.lookup()
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
