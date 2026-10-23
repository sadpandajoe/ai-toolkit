"""require-review-gate.sh blocks `gh pr create` until the review gate is PASS.

The hook reads the routing snapshot in the repository's PROJECT.md through the
same `gate_blockers` check `bin/aitk deliver` uses, so each case builds the
snapshot with the real `project-state` CLI rather than hand-writing the block.
A review PASS counts only with its evidence: a reviewer record from a
`model-run` envelope (`--result`), or a review exception backed by a passing
verification run. It also requires `--draft` unless the user set
`AITK_PR_READY=1` in the session environment (N4; a typed prefix does not
count), so the review cases open drafts and `DraftPolicyTests`
covers the draft check.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

from aitk.project_state import result_digest, working_tree_sha

ROOT = Path(__file__).resolve().parents[1]
AITK = str(ROOT / "bin" / "aitk")
PR_CREATE = 'gh pr create --draft --title "t" --body "b"'
READY_PR_CREATE = 'gh pr create --title "t" --body "b"'
DRAFT_PR_CREATE = "gh pr create --draft --base main --head o:feat/x --title t --body b"
# Creations the wrapper's text prefilter never hands to the detector (a quoted `g'h'`
# hides `gh` and `create` from it): a known limit, so they are allowed.
PREFILTER_LIMITS = ("g'h' pr create --fill",)
REPO_VIEW = "gh repo view --json nameWithOwner,defaultBranchRef,isFork"


def run_hook(command: str, cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if key not in {"SKIP_PR_GATE", "AITK_PR_READY"}
    }
    environment.update(env)
    return subprocess.run(
        ["bash", str(ROOT / "hooks" / "require-review-gate.sh")],
        input=json.dumps(
            {"cwd": str(cwd), "tool_input": {"command": command}, "hook_event_name": "PreToolUse"}
        ),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )


def project_state(repo: Path, *args: str) -> None:
    subprocess.run(
        [AITK, "project-state", *args, "--file", str(repo / "PROJECT.md")],
        check=True,
        capture_output=True,
        text=True,
    )


_ENVELOPES = tempfile.TemporaryDirectory(prefix="aitk-review-envelopes-")


def review_envelope(repo: Path) -> Path:
    """A completed `model-run` envelope for the tree in `repo`, as a reviewer lane returns it."""
    result = {
        "status": "completed",
        "summary": "no findings",
        "findings": [],
        "verification": ["read the diff"],
    }
    envelope = {
        "command": "model-run",
        "dry_run": False,
        "route": "review",
        "boundary": "review.independent",
        "provider": "codex",
        "result": result,
        "result_digest": result_digest(result),
        "reviewed_tree": working_tree_sha(repo),
        "error": None,
    }
    path = Path(_ENVELOPES.name) / f"{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(envelope))
    return path


def pass_review(repo: Path, *args: str) -> None:
    """Record review PASS the way a workflow does: with the reviewer's envelope."""
    project_state(
        repo, "gate", "--gate", "review", "--status", "PASS",
        "--result", str(review_envelope(repo)), *args,
    )


class ReviewGateHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        # macOS temp dirs sit under the /var -> /private/var symlink; resolve
        # so the hook and the state writer agree on the path.
        self.repo = Path(self._temporary.name).resolve()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q", "-b", "main"], check=True)

    def classify(self, repo: Path | None = None, workflow: str = "create-feature") -> None:
        project_state(
            repo or self.repo,
            "init",
            "--workflow", workflow,
            "--complexity", "STANDARD",
            "--size", "M",
            "--phaseability", "none",
            "--phase", "review",
        )

    def record_review(self, status: str, unit: str | None = None) -> None:
        unit_args = ["--unit", unit] if unit else []
        if status == "PASS":
            pass_review(self.repo, *unit_args)
            return
        project_state(self.repo, "gate", "--gate", "review", "--status", status, *unit_args)

    def assert_blocked(self, result: subprocess.CompletedProcess[str], *fragments: str) -> None:
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        self.assertIn("`review-code` on the branch for a change outside any workflow", result.stderr)
        self.assertNotIn("SKIP_PR_GATE", result.stderr)
        self.assertNotIn("--status PASS", result.stderr)
        for fragment in fragments:
            self.assertIn(fragment, result.stderr)

    def test_blocks_when_no_project_file_exists(self) -> None:
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "no PROJECT.md")

    def test_blocks_when_project_file_has_no_snapshot(self) -> None:
        (self.repo / "PROJECT.md").write_text("# Notes\n")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "no routing snapshot")

    def test_blocks_when_snapshot_never_recorded_review(self) -> None:
        self.classify()
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_allows_when_review_passed(self) -> None:
        self.classify()
        self.record_review("PASS")
        result = run_hook(PR_CREATE, self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_blocks_when_another_unit_is_still_open(self) -> None:
        self.classify()
        self.record_review("RETRY", unit="slice-two")
        self.record_review("PASS", unit="slice-one")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=RETRY", "slice-two")

    def test_blocks_review_pass_recorded_in_another_phase(self) -> None:
        self.classify()
        self.record_review("PASS")
        project_state(self.repo, "advance", "--to", "next-phase")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_resolves_project_file_from_a_subdirectory(self) -> None:
        self.classify()
        self.record_review("PASS")
        nested = self.repo / "pkg" / "src"
        nested.mkdir(parents=True)
        self.assertEqual(0, run_hook(PR_CREATE, nested).returncode)

    def test_bypass_counts_only_from_the_session_environment(self) -> None:
        self.assertEqual(2, run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
        self.assertEqual(2, run_hook(f"env SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
        self.assertEqual(0, run_hook(PR_CREATE, self.repo, SKIP_PR_GATE="1").returncode)
        self.assertEqual(2, run_hook(PR_CREATE, self.repo, SKIP_PR_GATE="0").returncode)

    def test_matches_pr_create_inside_compound_and_shell_commands(self) -> None:
        for command in (
            f"git push -u origin HEAD && {PR_CREATE}",
            f"cd . ; {PR_CREATE}",
            "git push -u origin HEAD\ngh pr create --fill",
            "git status\n\ngh pr new --fill",
            "if gh pr view --json url >/dev/null 2>&1; then echo exists; else gh pr create --fill; fi",
            "{ gh pr create --fill; }",
            "! gh pr create --fill",
            "then gh pr create --fill",
            f"bash -c '{PR_CREATE}'",
            f"bash -lc '{PR_CREATE}'",
            f"bash -ec '{PR_CREATE}'",
            "eval 'gh pr create --title t'",
            "env gh pr create --title t",
            "env GH_TOKEN=x gh pr create --title t",
            "timeout 60 gh pr create --fill",
            "echo x | xargs gh pr create",
            "GH_TOKEN=x gh pr create --draft",
            "/opt/homebrew/bin/gh pr create",
            "gh pr create --repo o/r --draft",
            "gh --repo o/r pr create --fill",
            "gh -R o/r pr create --fill",
            "gh pr new",
            "SKIP_PR_GATE=0 gh pr create --fill",
            "SKIP_PR_GATE= gh pr create --fill",
            "env -u UNUSED gh pr create --fill",
            "command -p gh pr create --fill",
            "timeout --signal TERM 60 gh pr create --fill",
            "xargs -I '{}' gh pr create",
            'printf \'%s\' "first \\"\nsecond"\ngh pr create --fill',
            "# open the PR\ngh pr create --fill",
            "git push # push first\ngh pr create --fill",
            "git push -u origin HEAD && \\\n  gh pr create --fill",
            "gh pr create --title \"x\" --body \"$(cat <<'EOF'\n## Summary\n- supports 12\" screens\nEOF\n)\"",
            "cat <<'END-BODY' > /dev/null\nit's here\nEND-BODY\ngh pr create --fill",
            "env -S 'gh pr create --fill'",
            "env --split-string='gh pr create --fill'",
            'echo "$(gh pr create --fill)"',
            "URL=`gh pr create --fill`",
            'gh pr create --title "never closed',
            "echo a\\ #; gh pr create --fill",
            "env -S '-u UNUSED gh pr create --fill'",
            "env -S 'gh\\_pr\\_create'",
        ):
            with self.subTest(command=command):
                self.assertEqual(2, run_hook(command, self.repo).returncode)

    def test_matches_pr_create_behind_wrappers_the_tokenizer_does_not_know(self) -> None:
        # No override anywhere in the session environment (run_hook strips them).
        for command in (
            "setsid gh pr create --fill",
            "setsid -w gh pr create --fill",
            "uv run gh pr create --fill",
            "flock /tmp/x gh pr create --fill",
            "chronic gh pr create --fill",
            "watch -n1 gh pr create --fill",
            "find . -maxdepth 0 -exec gh pr create --fill \\;",
            "builtin command gh pr create --fill",
            "eval -- 'gh pr create --fill'",
            "setsid bash -c 'gh pr create --fill'",
            "flock /tmp/x -c 'gh pr create --fill'",
            "uv run env GH_TOKEN=x gh pr create --fill",
            # a gh or git word that is only an argument of the wrapper comes first
            "flock /tmp/gh gh pr create --fill",
            "find . -name git -exec gh pr create --fill \\;",
            "uv run --with git gh pr create --fill",
            # function bodies, and the places git runs a shell it was given
            "echo() { gh pr create --fill; }; echo",
            "git rebase -x 'gh pr create --fill' HEAD~1",
            "git submodule foreach gh pr create --fill",
            "git -c alias.x='!gh pr create --fill' x",
            # a git-* head that git does not install is an ordinary executable, rescanned
            "./git-run gh pr create --fill",
            "git-x sh -c 'gh pr create --fill'",
            "/opt/x/git-wrap env gh pr create --fill",
        ):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(2, result.returncode, result.stderr)

    def test_a_git_rebase_exec_creation_is_listed_by_the_detector(self) -> None:
        from aitk.hooks import review_gate

        found = review_gate.pr_creations("git rebase -x 'gh pr create --fill' HEAD~1", str(self.repo))
        self.assertEqual([False], [creation.draft for creation in found])
        found = review_gate.pr_creations("flock /tmp/gh gh pr create --draft --fill", str(self.repo))
        self.assertEqual([True], [creation.draft for creation in found])
        for text in (
            "./git-run gh pr create --fill",
            "git-x sh -c 'gh pr create --fill'",
            "/opt/x/git-wrap env gh pr create --fill",
        ):
            with self.subTest(text=text):
                found = review_gate.pr_creations(text, str(self.repo))
                self.assertTrue(found)
                self.assertEqual({False}, {creation.draft for creation in found})

    def test_a_long_run_of_rescan_words_stays_fast_and_is_still_seen(self) -> None:
        from aitk.hooks import review_gate

        # Each later rescan word was rescanned from its own later words, so the work grew
        # with the fourth power of the word count (and the hook timed out, which may not block).
        text = "true " + "sh " * 200 + "; gh pr create --fill"
        started = time.monotonic()
        found = review_gate.pr_creations(text, str(self.repo))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual([False], [creation.draft for creation in found])
        # past the work budget the segment reads as one unresolved creation: still seen
        text = "true " + "sh " * 4000 + "gh pr create --draft --fill"
        started = time.monotonic()
        found = review_gate.pr_creations(text, str(self.repo))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertTrue(found)
        self.assertEqual({False}, {creation.draft for creation in found})

    def test_the_wrapper_prefilter_stays_linear_before_the_deadline(self) -> None:
        # The bash prefilter runs before the Python deadline: a two-star glob such as
        # `*gh*create*` backtracked quadratically (about 15 s here, past the 10 s timeout).
        started = time.monotonic()
        result = run_hook("gh " * 130_000 + "&& gh pr new --fill", self.repo)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(2, result.returncode, result.stderr)

    def test_the_work_budget_counts_characters_and_an_unread_creation_says_so(self) -> None:
        from aitk.hooks import review_gate

        self.classify()
        self.record_review("PASS")
        # a few words, one very long: every rescan tail carries it (~40s before the cap was in characters)
        for name, text in (
            ("gh300", "true " + "gh " * 300 + "x" * 100_000 + "; gh pr create --fill"),
            ("sh400", "true " + "sh " * 400 + "'" + "x" * 100_000 + "'; gh pr create --fill"),
        ):
            with self.subTest(case=name):
                started = time.monotonic()
                found = review_gate.pr_creations(text, str(self.repo))
                self.assertLess(time.monotonic() - started, 1.0)
                self.assertTrue(found)
                self.assertEqual({False}, {creation.draft for creation in found})
                started = time.monotonic()
                result = run_hook(text, self.repo)
                self.assertLess(time.monotonic() - started, 5.0)
                self.assertEqual(2, result.returncode, result.stderr)
        # a segment the budget could not cover reads as an unread creation, whatever its
        # text says, and the reason says it could not be read (not that it changes directory)
        for text in (
            "true " + "sh " * 4000 + "gh pr create --draft --fill",
            "true " + "sh " * 4000 + "; gh pr create --draft --fill",
            "true " + "sh " * 4000 + "; g'h' pr create --draft --fill; gh pr create --draft --fill",
        ):
            with self.subTest(words=len(text.split())):
                result = run_hook(text, self.repo)
                self.assert_blocked(result, "could not be read in full")
                self.assertNotIn("changes directory", result.stderr)
        # the reviewed repository does not vouch for a command that was never read; the
        # user's session overrides lift each check as for any other creation
        text = "true " + "sh " * 4000 + "gh pr create --draft --fill"
        skipped = run_hook(text, self.repo, SKIP_PR_GATE="1")
        self.assertEqual(2, skipped.returncode, skipped.stderr)
        self.assertIn("could not be read in full", skipped.stderr)
        self.assertEqual(0, run_hook(text, self.repo, SKIP_PR_GATE="1", AITK_PR_READY="1").returncode)

    def test_a_payload_git_runs_or_an_inline_alias_with_a_creation_is_never_read(self) -> None:
        # Block on sight: a gated mention in text git runs (or in a segment with an inline
        # alias) makes the whole command unreadable, in the reviewed repository or any other.
        self.classify()
        self.record_review("PASS")
        creation = "gh pr create --draft --head f --title t --body b"
        for command in (
            f"git rebase -x '{creation}' HEAD~1",
            f"git rebase --exec='{creation}' HEAD~1",
            f"git rebase -ix '{creation}' HEAD~1",
            f"git bisect run {creation}",
            f"git submodule foreach {creation}",
            "git submodule foreach \"gh''\" pr create --draft --fill",
            "git -c alias.x='!gh' x pr create --draft --fill",
            f"git -c alias.r='rebase -x \"{creation}\"' r HEAD~1",
            f"git -c alias.rebase=status rebase -x '{creation}' HEAD~1",
            f"git -c alias.rebase='!true' rebase -x '{creation}' HEAD~1",
            f"git -C . rebase -x '{creation}' HEAD~1",
            f"git --attr-source HEAD rebase -x '{creation}' HEAD~1",
            f"git-rebase -x '{creation}' HEAD~1",
            f"git-submodule foreach {creation}",
            "git submodule--helper foreach gh pr create --draft --fill",
            "git config alias.x '!gh pr create --draft --fill'",
            "git -c 'alias.x=!gh p\\\nr create --draft --fill' x",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "could not be read in full")
                self.assertEqual(0, run_hook(command, self.repo, SKIP_PR_GATE="1", AITK_PR_READY="1").returncode)
        # the same payloads that mention no gated operation are ordinary commands
        for command in (
            "git rebase -x 'make test' HEAD~1",
            "git bisect run ./t.sh",
            "git submodule foreach 'echo $name'",
            "git -c alias.st=status st",
            "git-rebase -x 'make test' HEAD~1",
            # a bare `alias.NAME` word is a name, not a configured alias
            "gh pr view alias.cleanup",
            "grep alias.x docs/create.md",
            "git log alias.create",
        ):
            with self.subTest(command=command):
                self.assertEqual(0, run_hook(command, self.repo).returncode)

    def test_a_git_dir_variable_on_gh_itself_is_a_pinned_limit(self) -> None:
        # `gh` is not git: GIT_DIR on a plain `gh pr create` is not tied to the repository it
        # names, so the reviewed working directory vouches for it (review_gate docstring).
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        for command in (
            f"GIT_DIR={other}/.git gh pr create --draft --fill",
            f"env GIT_DIR={other}/.git GIT_WORK_TREE={other} gh pr create --draft --fill",
        ):
            with self.subTest(command=command):
                self.assertEqual(0, run_hook(command, self.repo).returncode)

    def test_substitution_text_is_charged_against_the_work_budget(self) -> None:
        from aitk.hooks import review_gate

        # Each `$(` was rescanned to the end of the text: ~13s for this input before the
        # scan was charged to the budget (and the hook timeout then lets the command through).
        self.classify()
        self.record_review("PASS")
        text = 'gh pr create --fill --body "' + "$(" * 3000 + '"'
        started = time.monotonic()
        found = review_gate.pr_creations(text, str(self.repo))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertTrue(found)
        self.assertEqual({False}, {creation.draft for creation in found})
        self.assertTrue(all(creation.unreadable for creation in found))
        started = time.monotonic()
        result = run_hook(text, self.repo)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assert_blocked(result, "could not be read in full")
        started = time.monotonic()
        with self.assertRaises(review_gate.Blocked):
            review_gate.evaluate(text, str(self.repo), {})
        self.assertLess(time.monotonic() - started, 2.0)

    def test_a_creation_nested_past_the_depth_limit_reads_as_not_draft(self) -> None:
        from aitk.hooks import review_gate

        def nest(command: str, layers: int) -> str:
            for _ in range(layers):
                command = "sh -c " + shlex.quote(command)
            return command

        self.classify()
        self.record_review("PASS")
        for layers in (4, 5):
            for creation in ("gh pr create -d -dd=false --fill", "gh pr create --draft --fill"):
                command = nest(creation, layers)
                with self.subTest(layers=layers, creation=creation):
                    found = review_gate.pr_creations(command, str(self.repo))
                    self.assertEqual([False], [c.draft for c in found])
                    result = run_hook(command, self.repo)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertIn("--draft", result.stderr)
        # within the depth limit the creation is resolved and read as written
        self.assertEqual(0, run_hook(nest("gh pr create --draft --fill", 2), self.repo).returncode)
        self.assertEqual(2, run_hook(nest("gh pr create -d -dd=false --fill", 2), self.repo).returncode)

    def test_nested_pr_creation_inside_deliver_arguments_is_inspected(self) -> None:
        # The prefilter must still hand a deliver-containing command to the
        # detector: `g'h'` hides `gh` and `create` from a text match.
        nested = "bin/aitk deliver --title \"$(g'h' pr create --fill)\" --body-file b.md"
        nested_draft = "bin/aitk deliver --title \"$(g'h' pr create --fill --draft)\" --body-file b.md"
        self.assert_blocked(run_hook(nested, self.repo), "no PROJECT.md")
        # SKIP_PR_GATE lifts the review check only: the ready creation still blocks.
        skipped = run_hook(nested, self.repo, SKIP_PR_GATE="1")
        self.assertEqual(2, skipped.returncode, skipped.stderr)
        self.assertIn("--draft", skipped.stderr)
        # The draft variant needs a passing review.
        self.assert_blocked(run_hook(nested_draft, self.repo), "no PROJECT.md")
        self.classify()
        self.assert_blocked(run_hook(nested_draft, self.repo), "review=unrecorded")
        self.record_review("PASS")
        self.assertEqual(0, run_hook(nested_draft, self.repo).returncode)
        draft_blocked = run_hook(nested, self.repo)
        self.assertEqual(2, draft_blocked.returncode, draft_blocked.stderr)
        self.assertIn("--draft", draft_blocked.stderr)

    def test_the_text_prefilter_limit_is_pinned(self) -> None:
        # The wrapper's prefilter is a text match on `gh`..`create`/`gh`..`new`/`deliver`.
        # A quoted `g'h'` hides both from it, so the detector never runs and the
        # creation is not seen (review_gate docstring, Known limits). Pinned so a
        # fix moves these into the blocked set and out of the docstring.
        for command in PREFILTER_LIMITS:
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_ignores_commands_that_are_not_pr_create(self) -> None:
        for command in (
            "setsid gh pr view 12",
            "uv run pytest tests/",
            "echo setsid gh pr create",
            "find . -name '*.py' -exec grep -l gh {} \\;",
            "bin/aitk deliver --title t --body-file b.md",
            "gh pr view 12",
            "gh pr list --search create",
            "gh pr create --help",
            'git commit -m "docs: mention gh pr create"',
            'echo "gh pr create"',
            'git commit -m "first line\ngh pr create in the body"',
            "gh issue create --title t",
            "gh repo new",
            "cat <<'EOF' > notes.md\ngh pr create\nEOF",
            "cat <<-EOF\n\tgh pr create\n\tEOF\nls",
            "cat <<'END-DOC' > notes.md\ngh pr create\nEND-DOC",
            "# gh pr create later\nls",
            'git commit -m "x" # gh pr create',
            'echo "${#HOME} $#"',
            "ls",
            "flock /tmp/gh git status",
            "find . -name git -exec grep x {} \\;",
            "echo() { echo hi; }; echo",
            "git rebase -i HEAD~3",
            "git submodule update --init",
            "git bisect start",
        ):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_cd_inside_the_command_selects_the_repository_checked(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.repo.parent / (self.repo.name + "-other")
        other.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        subprocess.run(["git", "-C", str(other), "init", "-q", "-b", "main"], check=True)
        self.assert_blocked(run_hook(f"cd {other} && {PR_CREATE}", self.repo), "no PROJECT.md")
        self.assertEqual(0, run_hook(PR_CREATE, self.repo).returncode)
        # And the reverse: a gated target repo is allowed from an ungated session repo.
        self.classify(other)
        pass_review(other)
        with tempfile.TemporaryDirectory() as bare:
            subprocess.run(["git", "-C", bare, "init", "-q", "-b", "main"], check=True)
            self.assertEqual(0, run_hook(f"cd {other} && {PR_CREATE}", Path(bare)).returncode)

    def ungated_repo(self) -> Path:
        other = self.repo.parent / (self.repo.name + "-other")
        other.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        subprocess.run(["git", "-C", str(other), "init", "-q", "-b", "main"], check=True)
        return other

    def test_env_chdir_selects_the_repository_checked(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        for command in (
            f"env -C {other} gh pr create --fill",
            f"env --chdir={other} gh pr create --fill",
            f"env -C{other} gh pr create --fill",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "no PROJECT.md")

    def test_every_pr_creation_in_a_request_is_checked(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        self.assert_blocked(
            run_hook(f"{PR_CREATE}; cd {other} && {PR_CREATE}", self.repo), "no PROJECT.md"
        )
        self.assert_blocked(
            run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}; cd {other} && {PR_CREATE}", self.repo),
            "no PROJECT.md",
        )
        self.assertEqual(0, run_hook(f"{PR_CREATE}; git status", self.repo).returncode)

    def test_a_review_from_another_workflow_does_not_count(self) -> None:
        self.classify()
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        project_state(
            self.repo,
            "init", "--replace",
            "--workflow", "fix-bug",
            "--complexity", "STANDARD",
            "--size", "S",
            "--phaseability", "none",
            "--phase", "fix",
        )
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_directory_context_follows_the_command_order(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        (self.repo / "sub").mkdir()
        (other / "sub").mkdir()
        for command in (
            f'cd {other} && echo "$(gh pr create --fill)"',
            f'{PR_CREATE}; cd {other}; echo "$(gh pr create)"',
            f"env -C {other} env -C sub gh pr create --fill",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "no PROJECT.md")

    def test_unresolvable_target_blocks_instead_of_inheriting_a_pass(self) -> None:
        self.classify()
        self.record_review("PASS")
        other = self.ungated_repo()
        nested = f"cd {other} && gh pr create --fill"
        for _ in range(5):
            nested = f"sh -c {shlex.quote(nested)}"
        for command in (
            f"cd {other}; gh pr create --title $'it\\'s fixed' --body x",
            nested,
            # a target the shell expands names no directory this hook can read: not the
            # starting repo (a folder named `$OTHER` need not exist, and may)
            'cd "$OTHER/.." && gh pr create --draft --fill',
            "cd $OTHER && gh pr create --draft --fill",
            'cd "`pwd`/.." && gh pr create --draft --fill',
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "cannot follow")
        # Without a directory change the starting repo is the target, so its review pass
        # holds; the command cannot show a draft, so only the draft check blocks it.
        command = "gh pr create --draft --title $'it\\'s fixed' --body x"
        result = run_hook(command, self.repo)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("--draft", result.stderr)
        self.assertNotIn("cannot follow", result.stderr)
        self.assertNotIn("review gate", result.stderr)
        self.assertEqual(0, run_hook(command, self.repo, AITK_PR_READY="1").returncode)

    def test_a_fused_operator_run_does_not_hide_a_creation(self) -> None:
        # `&&(`, `;(`, `)|` came out of the lexer as one token, so the creation after the
        # run read as arguments of the command before it. No PROJECT.md here: every
        # creation the detector sees blocks.
        for command in (
            "git status&&(gh pr create --fill)",
            "git status;(gh pr create --draft --fill)",
            "(git status)&&gh pr create --draft --fill",
            "(git status)|gh pr create --draft --fill",
            "echo $(git status); gh pr create --draft --fill",
            "f()(gh pr create --draft --fill); f",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "no PROJECT.md")

    def test_the_head_is_matched_without_case(self) -> None:
        for command in (
            "Gh pr create --fill",
            "GH pr create --draft --fill",
            "/usr/local/bin/GH pr create --draft --fill",
            "setsid GH pr create --draft --fill",
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "no PROJECT.md")

    def test_cd_to_the_git_toplevel_follows_the_repository(self) -> None:
        self.classify()
        self.record_review("PASS")
        sub = self.repo / "sub"
        sub.mkdir()
        other = self.ungated_repo()
        (other / "sub").mkdir()
        for spelling in (
            'cd "$(git rev-parse --show-toplevel)"',
            "cd $(git rev-parse --show-toplevel)",
            "cd `git rev-parse --show-toplevel`",
        ):
            command = f"{spelling} && gh pr create --draft --fill"
            with self.subTest(command=command):
                self.assertEqual(0, run_hook(command, sub).returncode)
                # it follows the repository of the current directory, not the session's
                self.assert_blocked(run_hook(command, other / "sub"), "no PROJECT.md")
        # any other substitution, or a glob, still names no directory this hook can read
        for command in (
            'cd "$(git rev-parse --show-cdup)" && gh pr create --draft --fill',
            'cd "$(git rev-parse --show-toplevel)/sub" && gh pr create --draft --fill',
            f"cd {self.repo}/[s]ub && gh pr create --draft --fill",
            f"cd {self.repo}/su? && gh pr create --draft --fill",
            f'cd "{self.repo}/sub\t" && gh pr create --draft --fill',
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "cannot follow")
        # outside any repository the top level is unknown
        with tempfile.TemporaryDirectory() as bare:
            self.assert_blocked(
                run_hook('cd "$(git rev-parse --show-toplevel)" && gh pr create --draft --fill', Path(bare)),
                "cannot follow",
            )

    def test_blocks_when_project_file_is_unreadable(self) -> None:
        project = self.repo / "PROJECT.md"
        project.write_text("# Notes\n")
        project.chmod(0)
        self.addCleanup(lambda: project.chmod(0o644))
        if os.access(project, os.R_OK):
            self.skipTest("file permissions are not enforced for this user")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "could not be read")

    def test_blocks_when_snapshot_is_malformed(self) -> None:
        (self.repo / "PROJECT.md").write_text(
            "<!-- aitk-project-state:v2 -->\n{\"schema_version\": 2}\n<!-- /aitk-project-state -->\n"
        )
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "unreadable")

    def test_a_phase_advance_clears_the_review_for_a_pr(self) -> None:
        # deliver opens the PR in the phase whose review it read, so nothing
        # stands in for a review `advance` cleared.
        self.classify()
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        project_state(self.repo, "advance", "--to", "next-phase")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_a_later_retry_blocks_the_pr(self) -> None:
        self.classify()
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        self.record_review("RETRY", unit="slice-two")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=RETRY")

    def test_finds_project_file_in_a_subdirectory_workflow(self) -> None:
        nested = self.repo / "pkg"
        nested.mkdir()
        self.classify(nested)
        pass_review(nested)
        self.assertEqual(0, run_hook(PR_CREATE, nested).returncode)

    def test_ignores_the_draft_pr_identity_and_lookup_commands(self) -> None:
        for command in (REPO_VIEW, "git push -u origin HEAD"):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_gates_the_unprefixed_draft_pr_creation(self) -> None:
        self.assert_blocked(run_hook(DRAFT_PR_CREATE, self.repo), "no PROJECT.md")
        self.classify()
        self.assert_blocked(run_hook(DRAFT_PR_CREATE, self.repo), "review=unrecorded")
        self.record_review("PASS")
        self.assertEqual(0, run_hook(DRAFT_PR_CREATE, self.repo).returncode)

    def test_test_workflows_open_a_draft_on_review_pass(self) -> None:
        for workflow in ("tests",):
            with self.subTest(workflow=workflow):
                (self.repo / "PROJECT.md").unlink(missing_ok=True)
                self.classify(workflow=workflow)
                self.record_review("PASS")
                result = run_hook(DRAFT_PR_CREATE, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("published_pr", (self.repo / "PROJECT.md").read_text())

    def test_a_phase_advance_clears_the_review_for_a_draft(self) -> None:
        self.classify()
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        project_state(self.repo, "advance", "--to", "next-phase")
        self.assert_blocked(run_hook(DRAFT_PR_CREATE, self.repo), "review=unrecorded")

    def test_review_pass_without_a_reviewer_record_is_refused(self) -> None:
        self.classify()
        project_state(self.repo, "gate", "--gate", "review", "--status", "PASS")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "no reviewer record")
        # The same PASS with the reviewer's envelope counts.
        self.record_review("PASS")
        result = run_hook(PR_CREATE, self.repo)
        self.assertEqual(0, result.returncode, result.stderr)
        # A later PASS typed without evidence clears the record again.
        project_state(self.repo, "gate", "--gate", "review", "--status", "PASS")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "no reviewer record")

    def test_review_exception_counts_only_on_a_passing_verification_run(self) -> None:
        self.classify()
        exception = [
            AITK, "project-state", "gate", "--gate", "review", "--status", "PASS",
            "--exception", "micro-fix", "--file", str(self.repo / "PROJECT.md"),
        ]
        refused = subprocess.run(exception, cwd=self.repo, capture_output=True, text=True, check=False)
        self.assertEqual(1, refused.returncode)
        self.assertIn("passing verification run", refused.stderr)
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")
        verify = [AITK, "verify", "--run", "true", "--file", str(self.repo / "PROJECT.md")]
        subprocess.run(verify, cwd=self.repo, capture_output=True, text=True, check=True)
        # The setUp repository has no commit, so there is no base to measure the diff against.
        unmeasured = subprocess.run(exception, cwd=self.repo, capture_output=True, text=True, check=False)
        self.assertEqual(1, unmeasured.returncode)
        self.assertIn("no base", unmeasured.stderr)
        (self.repo / "base.py").write_text("x = 0\n")
        identity = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
        subprocess.run(["git", "-C", str(self.repo), "add", "base.py"], check=True)
        subprocess.run(["git", "-C", str(self.repo), *identity, "commit", "-q", "-m", "base"], check=True)
        (self.repo / "fix.py").write_text("y = 1\n")
        subprocess.run(verify, cwd=self.repo, capture_output=True, text=True, check=True)
        subprocess.run(exception, cwd=self.repo, capture_output=True, text=True, check=True)
        result = run_hook(PR_CREATE, self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_allows_outside_a_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(0, run_hook(PR_CREATE, Path(outside)).returncode)



class DraftPolicyTests(unittest.TestCase):
    """N4: a PR opens as a draft unless the user set AITK_PR_READY=1."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.repo = Path(self._temporary.name).resolve()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q", "-b", "main"], check=True)
        project_state(
            self.repo,
            "init",
            "--workflow", "create-feature",
            "--complexity", "STANDARD",
            "--size", "M",
            "--phaseability", "none",
            "--phase", "review",
        )
        pass_review(self.repo)

    def assert_draft_blocked(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn("--draft", result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        # The override is the user's to set; the message never spells it out.
        self.assertNotIn("AITK_PR_READY", result.stderr)

    def test_pr_create_without_draft_is_blocked_after_review_pass(self) -> None:
        for command in (
            READY_PR_CREATE,
            "gh pr create --fill",
            "gh pr create --draft=false --fill",
            "gh pr create -d=false --fill",
            "gh pr create -fd=false",
            "gh pr create -d=0 --fill",
            "gh pr create -dd=false --fill",
            "gh pr create -d -d=false --fill",
            "gh pr create -fdd=0",
            "gh pr create -dd=no --fill",
            "setsid gh pr create --fill",
            "uv run gh pr create --fill",
            "gh pr create -t d --fill",
            f"git push -u origin HEAD && {READY_PR_CREATE}",
            "git push -u origin HEAD\ngh pr create --fill",
            "timeout 60 gh pr create --fill",
            f"bash -lc '{READY_PR_CREATE}'",
        ):
            with self.subTest(command=command):
                self.assert_draft_blocked(run_hook(command, self.repo))

    def test_draft_spellings_are_allowed_after_review_pass(self) -> None:
        for command in (
            PR_CREATE,
            "gh pr create -d --fill",
            "gh pr create -fd",
            "gh pr create --draft=true --fill",
            "gh pr create -d=true --fill",
            "gh pr create -dd --fill",
            "gh pr create -dd=true --fill",
            "gh pr create -d=false -d --fill",
            "setsid gh pr create --draft --fill",
            "gh --repo o/r pr create --fill --draft",
        ):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_aitk_pr_ready_lifts_the_draft_check_only(self) -> None:
        self.assert_draft_blocked(run_hook(f"AITK_PR_READY=1 {READY_PR_CREATE}", self.repo))
        self.assert_draft_blocked(run_hook(f"env AITK_PR_READY=1 {READY_PR_CREATE}", self.repo))
        self.assertEqual(0, run_hook(READY_PR_CREATE, self.repo, AITK_PR_READY="1").returncode)
        for falsy in ("0", "false", "no", "off", "OFF"):
            self.assert_draft_blocked(run_hook(READY_PR_CREATE, self.repo, AITK_PR_READY=falsy))
        self.assert_draft_blocked(run_hook(f"AITK_PR_READY= {READY_PR_CREATE}", self.repo))
        # A ready PR still needs the review PASS.
        project_state(self.repo, "gate", "--gate", "review", "--status", "RETRY")
        result = run_hook(READY_PR_CREATE, self.repo, AITK_PR_READY="1")
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("review=RETRY", result.stderr)

    def test_skip_pr_gate_does_not_lift_the_draft_check(self) -> None:
        project_state(self.repo, "gate", "--gate", "review", "--status", "RETRY")
        self.assert_draft_blocked(run_hook(READY_PR_CREATE, self.repo, SKIP_PR_GATE="1"))
        # It still lifts the review check for a draft.
        self.assertEqual(0, run_hook(PR_CREATE, self.repo, SKIP_PR_GATE="1").returncode)
        # As a typed prefix it lifts nothing: the review check still blocks.
        result = run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}", self.repo)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("review=RETRY", result.stderr)
        # Both overrides together open a ready PR without a recorded review.
        self.assertEqual(
            0,
            run_hook(READY_PR_CREATE, self.repo, SKIP_PR_GATE="1", AITK_PR_READY="1").returncode,
        )

    def test_deliver_is_not_a_pr_creation_the_hook_polices(self) -> None:
        # `bin/aitk deliver` always opens a draft and has no ready flag, so the hook
        # has nothing to add; its block message points only at `gh pr create --draft`.
        for command in ("bin/aitk deliver --workflow create-feature", "./bin/aitk deliver --no-pr"):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)
        blocked = run_hook(READY_PR_CREATE, self.repo)
        self.assertNotIn("deliver", blocked.stderr)
        self.assertNotIn("--ready", blocked.stderr)

    def test_an_unresolved_creation_never_reads_as_a_draft(self) -> None:
        # A command the hook cannot read (an unbalanced quote) or that nests past the
        # tokenizer's depth reads as not draft whatever its text says: a regex over the
        # text accepts a first `-d` and ignores a later `-d=false`.
        for command in (
            "gh pr create --title $'it\\'s fixed' --body x",
            "gh pr create --draft --title $'it\\'s fixed' --body x",
            "gh pr create -d -dd=false --title $'it\\'s fixed' --body x",
        ):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assert_draft_blocked(result)
                self.assertIn("could not be read", result.stderr)
        self.assertEqual(
            0, run_hook("gh pr create --draft --title $'it\\'s fixed' --body x", self.repo, AITK_PR_READY="1").returncode
        )

    def test_python_missing_fails_closed_on_a_pr_command(self) -> None:
        with tempfile.TemporaryDirectory() as bindir:
            for tool in ("bash", "cat", "dirname", "printf"):
                found = shutil.which(tool)
                if found:
                    os.symlink(found, os.path.join(bindir, tool))
            payload = json.dumps({"cwd": str(self.repo), "tool_input": {"command": PR_CREATE}})
            blocked = subprocess.run(
                [os.path.join(bindir, "bash"), str(ROOT / "hooks" / "require-review-gate.sh")],
                input=payload, capture_output=True, text=True, timeout=30, check=False,
                env={"PATH": bindir},
            )
            self.assertEqual(2, blocked.returncode, blocked.stderr)
            self.assertIn("python3", blocked.stderr)
            unrelated = json.dumps({"cwd": str(self.repo), "tool_input": {"command": "ls"}})
            allowed = subprocess.run(
                [os.path.join(bindir, "bash"), str(ROOT / "hooks" / "require-review-gate.sh")],
                input=unrelated, capture_output=True, text=True, timeout=30, check=False,
                env={"PATH": bindir},
            )
            self.assertEqual(0, allowed.returncode, allowed.stderr)

if __name__ == "__main__":
    unittest.main()
