"""require-review-gate.sh blocks `gh pr create` until the review gate is PASS.

The hook reads the routing snapshot in the repository's PROJECT.md through the
same `gate_blockers` check `bin/aitk deliver` uses, so each case builds the
snapshot with the real `project-state` CLI rather than hand-writing the block.
A review PASS counts only with its evidence: a reviewer record from a
`model-run` envelope (`--result`), or a review exception backed by a passing
verification run. It also requires `--draft` unless the user set
`AITK_PR_READY=1` (N4), so the review cases open drafts and `DraftPolicyTests`
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
import unittest
import uuid

from aitk.project_state import result_digest, working_tree_sha

ROOT = Path(__file__).resolve().parents[1]
AITK = str(ROOT / "bin" / "aitk")
PR_CREATE = 'gh pr create --draft --title "t" --body "b"'
READY_PR_CREATE = 'gh pr create --title "t" --body "b"'
DRAFT_PR_CREATE = "gh pr create --draft --base main --head o:feat/x --title t --body b"
# The lookup exactly as create-pr.md fences it, env prefix included.
PR_LOOKUP = (
    'BRANCH="$branch" HEAD_REPO="$head_repo" gh api --paginate -X GET "repos/$base_repo/pulls" \\\n'
    '  -f state=open -f per_page=100 -f head="$head_owner:$branch" \\\n'
    "  --jq '.[] | select(.head.ref == env.BRANCH and ((.head.repo.full_name // \"\") | ascii_downcase) == env.HEAD_REPO)"
    " | [.number, .draft, .base.ref, .html_url] | @tsv'"
)
REPO_VIEW = "gh repo view --json nameWithOwner,defaultBranchRef,isFork"
DIGEST = "sha256:" + "a" * 64


def run_hook(command: str, cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != "SKIP_PR_GATE"}
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


def checkpoint(
    repo: Path, action: str, *args: str, workflow: str = "create-feature"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [AITK, "checkpoint", action, "--workflow", workflow, "--file", str(repo / "PROJECT.md"), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class ReviewGateHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        # macOS temp dirs sit under the /var -> /private/var symlink, which
        # `aitk checkpoint` refuses; resolve like tests/test_checkpoint.py.
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

    def test_bypass_prefix_and_environment_allow(self) -> None:
        self.assertEqual(0, run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
        self.assertEqual(0, run_hook(f"env SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
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

    def test_ignores_commands_that_are_not_pr_create(self) -> None:
        for command in (
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

    def test_pending_reservation_from_another_workflow_does_not_count(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase-one")
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
        ):
            with self.subTest(command=command):
                self.assert_blocked(run_hook(command, self.repo), "cannot follow")
        # Without a directory change the starting repo is the target, so a pass holds.
        self.assertEqual(0, run_hook("gh pr create --draft --title $'it\\'s fixed' --body x", self.repo).returncode)

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

    def test_pending_publish_reservation_no_longer_stands_in_after_a_phase_advance(self) -> None:
        # deliver opens the PR in the phase whose review it read, so a
        # reservation no longer stands in for a review `advance` cleared.
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase-one")
        project_state(self.repo, "advance", "--to", "next-phase")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=unrecorded")

    def test_pending_reservation_never_overrides_a_later_retry(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase-one")
        self.record_review("RETRY", unit="slice-two")
        self.assert_blocked(run_hook(PR_CREATE, self.repo), "review=RETRY")

    def test_finds_project_file_in_a_subdirectory_workflow(self) -> None:
        nested = self.repo / "pkg"
        nested.mkdir()
        self.classify(nested)
        pass_review(nested)
        self.assertEqual(0, run_hook(PR_CREATE, nested).returncode)

    def test_ignores_the_draft_pr_identity_and_lookup_commands(self) -> None:
        for command in (PR_LOOKUP, REPO_VIEW, "git push -u origin HEAD"):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_gates_the_unprefixed_draft_pr_creation(self) -> None:
        self.assert_blocked(run_hook(DRAFT_PR_CREATE, self.repo), "no PROJECT.md")
        self.classify()
        self.assert_blocked(run_hook(DRAFT_PR_CREATE, self.repo), "review=unrecorded")
        self.record_review("PASS")
        self.assertEqual(0, run_hook(DRAFT_PR_CREATE, self.repo).returncode)

    def test_test_workflows_open_a_draft_on_review_pass_without_a_checkpoint(self) -> None:
        for workflow in ("create-tests", "update-tests"):
            with self.subTest(workflow=workflow):
                (self.repo / "PROJECT.md").unlink(missing_ok=True)
                self.classify(workflow=workflow)
                self.record_review("PASS")
                result = run_hook(DRAFT_PR_CREATE, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("published_pr", (self.repo / "PROJECT.md").read_text())

    def test_applied_reservation_no_longer_covers_a_phase_advance(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase:single")
        checkpoint(
            self.repo, "apply", "--key", "published_pr", "--operation-id", "phase:single",
            "--result-digest", DIGEST,
        )
        project_state(self.repo, "advance", "--to", "next-phase")
        self.assert_blocked(run_hook(DRAFT_PR_CREATE, self.repo), "review=unrecorded")

    def test_pending_reservation_no_longer_covers_a_draft_after_a_phase_advance(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        checkpoint(self.repo, "reserve", "--key", "published_pr", "--operation-id", "phase:single")
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
        subprocess.run(
            [AITK, "verify", "--run", "true", "--file", str(self.repo / "PROJECT.md")],
            cwd=self.repo, capture_output=True, text=True, check=True,
        )
        subprocess.run(exception, cwd=self.repo, capture_output=True, text=True, check=True)
        result = run_hook(PR_CREATE, self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_opt_out_leaves_no_effect_and_allows_restarting_the_checkpoint(self) -> None:
        self.classify()
        checkpoint(self.repo, "init")
        project_state(self.repo, "gate", "--gate", "verification", "--status", "PASS")
        self.record_review("PASS")
        # `--no-pr`: the owner never reserves, so a fresh run can replace the checkpoint.
        replaced = checkpoint(self.repo, "init", "--replace", "--json")
        self.assertEqual([], json.loads(replaced.stdout)["effects"])

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
            "gh --repo o/r pr create --fill --draft",
        ):
            with self.subTest(command=command):
                result = run_hook(command, self.repo)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_aitk_pr_ready_lifts_the_draft_check_only(self) -> None:
        self.assertEqual(0, run_hook(f"AITK_PR_READY=1 {READY_PR_CREATE}", self.repo).returncode)
        self.assertEqual(0, run_hook(f"env AITK_PR_READY=1 {READY_PR_CREATE}", self.repo).returncode)
        self.assertEqual(0, run_hook(READY_PR_CREATE, self.repo, AITK_PR_READY="1").returncode)
        self.assert_draft_blocked(run_hook(READY_PR_CREATE, self.repo, AITK_PR_READY="0"))
        self.assert_draft_blocked(run_hook(f"AITK_PR_READY= {READY_PR_CREATE}", self.repo))
        # A ready PR still needs the review PASS.
        project_state(self.repo, "gate", "--gate", "review", "--status", "RETRY")
        result = run_hook(f"AITK_PR_READY=1 {READY_PR_CREATE}", self.repo)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("review=RETRY", result.stderr)

    def test_skip_pr_gate_does_not_lift_the_draft_check(self) -> None:
        project_state(self.repo, "gate", "--gate", "review", "--status", "RETRY")
        self.assert_draft_blocked(run_hook(f"SKIP_PR_GATE=1 {READY_PR_CREATE}", self.repo))
        self.assert_draft_blocked(run_hook(READY_PR_CREATE, self.repo, SKIP_PR_GATE="1"))
        # It still lifts the review check for a draft.
        self.assertEqual(0, run_hook(f"SKIP_PR_GATE=1 {PR_CREATE}", self.repo).returncode)
        # Both overrides together open a ready PR without a recorded review.
        self.assertEqual(
            0,
            run_hook(f"SKIP_PR_GATE=1 AITK_PR_READY=1 {READY_PR_CREATE}", self.repo).returncode,
        )

    def test_ready_delivery_needs_the_same_override(self) -> None:
        for command in (
            "bin/aitk deliver --workflow create-feature --ready",
            "./bin/aitk deliver --ready --workflow fix-bug",
            "aitk deliver --workflow create-feature --phase one --ready",
        ):
            with self.subTest(command=command):
                self.assert_draft_blocked(run_hook(command, self.repo))
                self.assertEqual(0, run_hook(f"AITK_PR_READY=1 {command}", self.repo).returncode)
                self.assert_draft_blocked(run_hook(f"SKIP_PR_GATE=1 {command}", self.repo))
        # A draft delivery is deliver's own business: the hook lets it through.
        result = run_hook("bin/aitk deliver --workflow create-feature", self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_unparseable_creation_needs_a_visible_draft_flag(self) -> None:
        self.assert_draft_blocked(run_hook("gh pr create --title $'it\\'s fixed' --body x", self.repo))
        result = run_hook("gh pr create --draft --title $'it\\'s fixed' --body x", self.repo)
        self.assertEqual(0, result.returncode, result.stderr)

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
