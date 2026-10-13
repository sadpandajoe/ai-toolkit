"""The D11 experiment: the reviewer runs one allowlisted test in a scratch copy.

Nothing here reaches a provider. The transport tests use stub process runners
behind the real `model-run` code, and the CLI tests put a stub `claude` first on
a PATH that holds no real one. What they pin: the allowlist is narrow and comes
only from the command line, only the reviewer's lanes take it, each provider's
controls hold it, the worker runs in a copy that is removed afterwards, the
source worktree is never written, and the envelope records the experiment.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

from aitk.routing_experiment import (
    CLAUDE_SANDBOX_SETTINGS,
    COMMAND_RUNNERS,
    REVIEWER_CONTRACT,
    experiment,
    reviewer_route,
)
from aitk.routing_policy import ROUTE_CONTROLS, ModelRouteError
from aitk.routing_resolver import resolve_route
from aitk.routing_transport import run_model, worker_instructions

from routing_fixtures import ROOT, RESULT


GIT_RULES = ["Bash(git log *)", "Bash(git show *)", "Bash(git diff *)", "Bash(git blame *)"]


TEST_COMMAND = "python3 -m unittest *"


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", *arguments],
        text=True, capture_output=True, check=True,
    ).stdout


def make_repo(parent: Path) -> Path:
    """A repo with one commit, an uncommitted edit, an untracked file and a symlink."""
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "code.py").write_text("VALUE = 1\n")
    (repo / "README.md").write_text("readme\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    (repo / "pkg" / "code.py").write_text("VALUE = 2\n")
    (repo / "pkg" / "test_new.py").write_text("# untracked test\n")
    os.symlink("code.py", repo / "pkg" / "link.py")
    return repo


def reviewer_runs_test(*commands: str):
    return experiment("reviewer-runs-test", list(commands) or [TEST_COMMAND])


class AllowlistTests(unittest.TestCase):
    def test_exact_and_prefix_entries_are_accepted_as_written(self) -> None:
        chosen = experiment(
            "reviewer-runs-test",
            ["npm test", "python3 -m pytest *", "go test ./... *", "bin/aitk check",
             "python3 -m unittest tests.test_x.Case.test_y", "npm test"],
        )
        self.assertEqual("reviewer-runs-test", chosen.name)
        # Duplicates collapse; order is kept.
        self.assertEqual(
            ("npm test", "python3 -m pytest *", "go test ./... *", "bin/aitk check",
             "python3 -m unittest tests.test_x.Case.test_y"),
            chosen.test_commands,
        )

    def test_shell_syntax_and_general_prefixes_are_refused(self) -> None:
        refused = [
            "npm test; curl example.com",
            "npm test && rm -rf build",
            "npm test || true",
            "npm test | tee log",
            "npm test > out.txt",
            "npm test < in.txt",
            "npm test $(id)",
            "npm test `id`",
            "npm test ${HOME}",
            'pytest "tests/a b.py"',
            "pytest 'x'",
            "pytest ~/tests",
            "pytest tests/*.py *",
            "npm test*",
            "npm  test",
            " npm test",
            "npm test ",
            "npm test\nrm -rf build",
            "npm test) Bash(rm *",
            "",
            "*",
            # Prefixes that would allow any command or any code.
            "pytest *",
            "python3 *",
            "python3 -m *",
            "python3 -c *",
            "node -e *",
            "npm test -- *",
            "timeout 60 *",
            "env CI=1 *",
            "/usr/bin/env CI=1 *",
            "bash run-tests.sh *",
            "sudo -u nobody *",
            "docker run image *",
            "xargs pytest *",
            "x" * 201,
        ]
        for command in refused:
            with self.subTest(command=command):
                with self.assertRaises(ModelRouteError):
                    experiment("reviewer-runs-test", [command])
        for runner in sorted(COMMAND_RUNNERS):
            with self.subTest(runner=runner):
                with self.assertRaisesRegex(ModelRouteError, "runs its arguments"):
                    experiment("reviewer-runs-test", [f"{runner} tests *"])

    def test_the_flags_come_together_or_not_at_all(self) -> None:
        self.assertIsNone(experiment(None, []))
        with self.assertRaisesRegex(ModelRouteError, "only accepted with --experiment"):
            experiment(None, ["npm test"])
        with self.assertRaisesRegex(ModelRouteError, "at least one --test-command"):
            experiment("reviewer-runs-test", [])
        with self.assertRaisesRegex(ModelRouteError, "unknown experiment"):
            experiment("reviewer-runs-anything", ["npm test"])
        with self.assertRaisesRegex(ModelRouteError, "at most 8"):
            experiment("reviewer-runs-test", [f"npm run test{index}" for index in range(9)])


class ReviewerRouteTests(unittest.TestCase):
    def test_only_the_reviewer_lanes_take_the_experiment(self) -> None:
        payload = json.loads((ROOT / "interfaces/model-routing.json").read_text())
        reviewer_lanes = {
            boundary["id"]
            for boundary in payload["dispatch_boundaries"]
            if REVIEWER_CONTRACT in boundary.get("contracts", [])
        }
        self.assertIn("review.independent", reviewer_lanes)
        chosen = reviewer_runs_test()
        for boundary in sorted(reviewer_lanes):
            for provider in ("claude", "codex"):
                with self.subTest(boundary=boundary, provider=provider):
                    reviewer_route(resolve_route(ROOT, "review", provider, boundary), chosen)
        for route, boundary, lens in (
            ("review", "review.verify-major", None),
            ("deep-review", "review.deep-lenses", "skills/review/references/adversarial.md"),
            ("review", "planning.validate", None),
            ("rca", "debug.rca-specialist", None),
        ):
            with self.subTest(boundary=boundary):
                resolved = resolve_route(ROOT, route, "claude", boundary, lens)
                with self.assertRaisesRegex(ModelRouteError, "only to the independent reviewer"):
                    reviewer_route(resolved, chosen)

    def test_the_variant_changes_only_what_the_experiment_needs(self) -> None:
        chosen = reviewer_runs_test("npm test", TEST_COMMAND)
        claude = resolve_route(ROOT, "review", "claude", "review.independent")
        variant = reviewer_route(claude, chosen)
        self.assertEqual("dontAsk", variant.controls["permission_mode"])
        self.assertEqual(["Write", "Edit", "NotebookEdit"], variant.controls["disallowed_tools"])
        self.assertEqual(claude.tools + ("Bash(npm test)", f"Bash({TEST_COMMAND})"), variant.tools)
        self.assertEqual("plan", claude.controls["permission_mode"], "the resolved route is not mutated")
        codex = resolve_route(ROOT, "review", "codex", "review.independent")
        self.assertEqual("workspace-write", reviewer_route(codex, chosen).controls["sandbox"])
        self.assertEqual("read-only", codex.controls["sandbox"])
        # The pinned table stays as it was: only this code path widens a lane.
        self.assertEqual(("read-only", "plan", ("Write", "Edit", "NotebookEdit")), ROUTE_CONTROLS["review"])

    def test_the_header_names_the_allowlist_after_the_contracts(self) -> None:
        route = resolve_route(ROOT, "review", "claude", "review.independent")
        contracts = ((REVIEWER_CONTRACT, "digest", "# Reviewer\nYou never run tests.\n"),)
        plain = worker_instructions(route, contracts)
        self.assertNotIn("experiment", plain)
        text = worker_instructions(route, contracts, Path("/scratch/worktree"), reviewer_runs_test())
        self.assertEqual(plain.split("workspace=")[0], text.split("workspace=")[0])
        self.assertIn('allowed_test_commands=["python3 -m unittest *"]\n', text)
        self.assertIn("experiment=reviewer-runs-test\n", text)
        self.assertLess(text.index("You never run tests."), text.index("experiment_rule="))
        self.assertLess(text.index("experiment_rule="), text.index("The task is the user message"))
        self.assertIn("one targeted test", text)


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name).resolve()
        self.prompt = self.directory / "prompt.md"
        self.prompt.write_text("Review this change.\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_lane(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]],
        provider: str,
        cwd: Path,
        chosen=None,
        boundary: str = "review.independent",
        dry_run: bool = False,
    ) -> tuple[int, dict[str, object]]:
        with mock.patch(
            "aitk.routing_transport.shutil.which", side_effect=lambda name: f"/stub/{name}"
        ):
            return run_model(
                ROOT, "review", provider, boundary, self.prompt, cwd=cwd,
                dry_run=dry_run, runner=runner, experiment=chosen,
            )

    @staticmethod
    def version_only(provider: str) -> Callable[..., subprocess.CompletedProcess[str]]:
        def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if "--version" in argv:
                version = "2.1.284\n" if provider == "claude" else "codex-cli 0.159.3\n"
                return subprocess.CompletedProcess(argv, 0, version, "")
            raise AssertionError("no worker may start")

        return runner

    def observing(self, provider: str, seen: dict[str, object]):
        """A stub worker that records what it was handed and writes like a test run."""

        def runner(argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            if "--version" in argv:
                return self.version_only(provider)(argv)
            cwd = Path(str(options["cwd"]))
            seen["argv"] = list(argv)
            seen["cwd"] = cwd
            seen["env"] = dict(options.get("env") or {})
            seen["status"] = git(cwd, "status", "--porcelain")
            seen["head"] = git(cwd, "rev-parse", "HEAD").strip()
            seen["remotes"] = git(cwd, "remote").strip()
            seen["log"] = git(cwd, "log", "--format=%s").strip()
            seen["git_is_directory"] = (cwd / ".git").is_dir()
            seen["code"] = (cwd / "pkg" / "code.py").read_text()
            link = cwd / "pkg" / "link.py"
            seen["link"] = os.readlink(link) if link.is_symlink() else None
            if provider == "claude":
                seen["instructions"] = Path(
                    argv[argv.index("--append-system-prompt-file") + 1]
                ).read_text()
            else:
                overrides = [argv[i + 1] for i, item in enumerate(argv) if item == "--config"]
                (developer,) = [item for item in overrides if item.startswith("developer_instructions=")]
                seen["instructions"] = tomllib.loads(developer)["developer_instructions"]
            # What a test run leaves behind, read-only directory included.
            (cwd / "written-by-the-test.txt").write_text("output\n")
            (cwd / "readonly").mkdir()
            (cwd / "readonly" / "file").write_text("x")
            (cwd / "readonly").chmod(0o500)
            if provider == "codex":
                Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(RESULT))
                return subprocess.CompletedProcess(argv, 0, json.dumps({"type": "turn.completed"}), "")
            envelope = {"type": "result", "subtype": "success", "is_error": False,
                        "structured_output": RESULT}
            return subprocess.CompletedProcess(argv, 0, json.dumps(envelope), "")

        return runner

    def test_claude_dry_run_names_the_allowlist_and_the_sandbox(self) -> None:
        code, payload = self.run_lane(
            self.version_only("claude"), "claude", ROOT, reviewer_runs_test("npm test", TEST_COMMAND),
            dry_run=True,
        )
        self.assertEqual(0, code, payload)
        argv = payload["argv"]
        self.assertEqual("dontAsk", argv[argv.index("--permission-mode") + 1])
        self.assertEqual("none", argv[argv.index("--permission-prompts") + 1])
        self.assertIn("--restricted", argv)
        self.assertEqual(CLAUDE_SANDBOX_SETTINGS, json.loads(argv[argv.index("--settings") + 1]))
        sandbox = json.loads(argv[argv.index("--settings") + 1])["sandbox"]
        self.assertIs(True, sandbox["enabled"])
        self.assertIs(True, sandbox["failIfUnavailable"])
        self.assertIs(False, sandbox["allowUnsandboxedCommands"])
        self.assertIs(False, sandbox["autoAllowBashIfSandboxed"])
        self.assertEqual({"allowedDomains": [], "strictAllowlist": True}, sandbox["network"])
        tools = argv[argv.index("--tools") + 1 : argv.index("--allowedTools")]
        self.assertEqual(["Read", "Grep", "Glob", "Bash"], tools)
        rules = argv[argv.index("--allowedTools") + 1 : argv.index("--json-schema")]
        self.assertEqual(GIT_RULES + ["Bash(npm test)", f"Bash({TEST_COMMAND})"], rules)
        disallowed = argv[argv.index("--disallowedTools") + 1 : argv.index("--tools")]
        self.assertEqual(["Write", "Edit", "NotebookEdit"], disallowed)
        self.assertEqual(
            {"name": "reviewer-runs-test", "allowed_commands": ["npm test", TEST_COMMAND],
             "enforcement": "permission-rules+sandbox"},
            payload["experiment"],
        )

    def test_without_the_flag_the_reviewer_stays_read_only(self) -> None:
        code, payload = self.run_lane(self.version_only("claude"), "claude", ROOT, dry_run=True)
        self.assertEqual(0, code, payload)
        argv = payload["argv"]
        self.assertEqual("plan", argv[argv.index("--permission-mode") + 1])
        self.assertNotIn("--settings", argv)
        self.assertEqual(GIT_RULES, argv[argv.index("--allowedTools") + 1 : argv.index("--json-schema")])
        self.assertIsNone(payload["experiment"])
        code, payload = self.run_lane(self.version_only("codex"), "codex", ROOT, dry_run=True)
        self.assertEqual(0, code, payload)
        self.assertEqual("read-only", payload["argv"][payload["argv"].index("--sandbox") + 1])
        self.assertIn("--add-dir", payload["argv"])
        self.assertIsNone(payload["experiment"])

    def test_codex_dry_run_roots_a_networkless_sandbox_at_the_copy(self) -> None:
        code, payload = self.run_lane(
            self.version_only("codex"), "codex", ROOT, reviewer_runs_test(), dry_run=True
        )
        self.assertEqual(0, code, payload)
        argv = payload["argv"]
        self.assertEqual("workspace-write", argv[argv.index("--sandbox") + 1])
        self.assertEqual("<scratch-worktree>", argv[argv.index("--cd") + 1])
        self.assertNotIn("--add-dir", argv, "the source worktree is never a writable root")
        overrides = [argv[i + 1] for i, item in enumerate(argv) if item == "--config"]
        for expected in (
            'approval_policy="never"',
            "sandbox_workspace_write.network_access=false",
            "sandbox_workspace_write.exclude_slash_tmp=true",
            "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            'sandbox_workspace_write.writable_roots=["<scratch-tmp>"]',
        ):
            self.assertIn(expected, overrides)
        self.assertEqual("instruction+sandbox", payload["experiment"]["enforcement"])

    def test_claude_runs_in_a_copy_that_is_removed_and_never_writes_the_source(self) -> None:
        repo = make_repo(self.directory)
        status = git(repo, "status", "--porcelain")
        head = git(repo, "rev-parse", "HEAD").strip()
        seen: dict[str, object] = {}
        with mock.patch.dict(os.environ, {"GIT_DIR": str(repo / ".git"), "GIT_WORK_TREE": str(repo)}):
            code, payload = self.run_lane(self.observing("claude", seen), "claude", repo, reviewer_runs_test())
        self.assertEqual(0, code, payload)
        cwd = seen["cwd"]
        assert isinstance(cwd, Path)
        self.assertNotEqual(repo, cwd)
        self.assertEqual(cwd.resolve(), cwd)
        self.assertEqual("worktree", cwd.name)
        # The copy is the worktree as it stands, as a standalone repository.
        self.assertEqual(status, seen["status"])
        self.assertEqual(head, seen["head"])
        self.assertEqual("base", seen["log"])
        self.assertEqual("", seen["remotes"])
        self.assertIs(True, seen["git_is_directory"])
        self.assertEqual("VALUE = 2\n", seen["code"])
        self.assertEqual("code.py", seen["link"])
        environment = seen["env"]
        assert isinstance(environment, dict)
        self.assertEqual(str(cwd.parent / "tmp"), environment["CLAUDE_CODE_TMPDIR"])
        self.assertEqual("1", environment["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"])
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_WORK_TREE", environment)
        instructions = str(seen["instructions"])
        self.assertIn(f"workspace={cwd}\n", instructions)
        self.assertIn(f'allowed_test_commands=["{TEST_COMMAND}"]', instructions)
        self.assertFalse(cwd.parent.exists(), "the scratch root outlived the run")
        self.assertFalse((repo / "written-by-the-test.txt").exists())
        self.assertEqual(status, git(repo, "status", "--porcelain"))
        self.assertEqual(head, git(repo, "rev-parse", "HEAD").strip())
        self.assertEqual("reviewer-runs-test", payload["experiment"]["name"])
        self.assertEqual([TEST_COMMAND], payload["experiment"]["allowed_commands"])

    def test_codex_runs_in_the_copy_with_its_temp_as_the_only_other_root(self) -> None:
        repo = make_repo(self.directory)
        status = git(repo, "status", "--porcelain")
        seen: dict[str, object] = {}
        code, payload = self.run_lane(self.observing("codex", seen), "codex", repo, reviewer_runs_test())
        self.assertEqual(0, code, payload)
        cwd = seen["cwd"]
        assert isinstance(cwd, Path)
        argv = seen["argv"]
        assert isinstance(argv, list)
        self.assertEqual(str(cwd), argv[argv.index("--cd") + 1])
        self.assertNotIn(str(repo), argv)
        self.assertIn(
            f"sandbox_workspace_write.writable_roots=[{json.dumps(str(cwd.parent / 'tmp'))}]", argv
        )
        environment = seen["env"]
        assert isinstance(environment, dict)
        self.assertEqual(str(cwd.parent / "tmp"), environment["TMPDIR"])
        self.assertNotEqual(str(cwd.parent / "tmp"), environment["CODEX_HOME"])
        self.assertEqual(status, seen["status"])
        self.assertIn('allowed_test_commands=["python3 -m unittest *"]', str(seen["instructions"]))
        self.assertFalse(cwd.parent.exists(), "the scratch root outlived the run")
        self.assertFalse((repo / "written-by-the-test.txt").exists())
        self.assertEqual(status, git(repo, "status", "--porcelain"))
        self.assertEqual("instruction+sandbox", payload["experiment"]["enforcement"])

    def test_a_linked_worktree_is_copied_as_a_standalone_repository(self) -> None:
        main = make_repo(self.directory)
        git(main, "stash", "-u", "-q")
        linked = self.directory / "linked"
        git(main, "worktree", "add", "-q", "-b", "feature", str(linked))
        (linked / "pkg" / "code.py").write_text("VALUE = 3\n")
        worktrees = git(main, "worktree", "list", "--porcelain")
        seen: dict[str, object] = {}
        code, payload = self.run_lane(self.observing("claude", seen), "claude", linked, reviewer_runs_test())
        self.assertEqual(0, code, payload)
        # Not a linked worktree: Claude's sandbox would let one write the main
        # repository's `.git`.
        self.assertIs(True, seen["git_is_directory"])
        self.assertEqual(git(linked, "rev-parse", "HEAD").strip(), seen["head"])
        self.assertEqual(" M pkg/code.py\n", seen["status"])
        self.assertEqual(worktrees, git(main, "worktree", "list", "--porcelain"))

    def test_a_directory_inside_a_worktree_is_refused_before_any_worker(self) -> None:
        repo = make_repo(self.directory)
        with self.assertRaisesRegex(ModelRouteError, "the top of the worktree"):
            self.run_lane(self.version_only("claude"), "claude", repo / "pkg", reviewer_runs_test())

    def test_a_directory_outside_git_is_copied_as_is(self) -> None:
        plain = self.directory / "plain"
        (plain / "pkg").mkdir(parents=True)
        (plain / "pkg" / "code.py").write_text("VALUE = 1\n")
        seen: list[Path] = []

        def runner(argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, "2.1.284\n", "")
            cwd = Path(str(options["cwd"]))
            seen.append(cwd)
            self.assertEqual("VALUE = 1\n", (cwd / "pkg" / "code.py").read_text())
            envelope = {"type": "result", "subtype": "success", "is_error": False,
                        "structured_output": RESULT}
            return subprocess.CompletedProcess(argv, 0, json.dumps(envelope), "")

        code, payload = self.run_lane(runner, "claude", plain, reviewer_runs_test())
        self.assertEqual(0, code, payload)
        self.assertNotEqual(plain, seen[0])
        self.assertFalse(seen[0].exists())

    def test_a_copy_that_fails_starts_no_worker_and_leaves_nothing(self) -> None:
        repo = make_repo(self.directory)
        created: list[Path] = []
        real_mkdtemp = tempfile.mkdtemp

        def mkdtemp(*arguments: object, **options: object) -> str:
            path = real_mkdtemp(*arguments, **options)
            created.append(Path(path))
            return path

        with mock.patch("aitk.routing_experiment.tempfile.mkdtemp", side_effect=mkdtemp), mock.patch(
            "aitk.routing_experiment.shutil.copytree", side_effect=shutil.Error("disk full")
        ):
            code, payload = self.run_lane(self.version_only("claude"), "claude", repo, reviewer_runs_test())
        self.assertEqual(3, code)
        self.assertFalse(payload["transport"]["started"])
        self.assertIn("the scratch copy could not be made", payload["error"]["message"])
        self.assertEqual("reviewer-runs-test", payload["experiment"]["name"])
        self.assertEqual(1, len(created))
        self.assertFalse(created[0].exists())

    def test_the_experiment_is_refused_on_other_lanes_before_preflight(self) -> None:
        with self.assertRaisesRegex(ModelRouteError, "only to the independent reviewer"):
            self.run_lane(
                self.version_only("claude"), "claude", ROOT, reviewer_runs_test(),
                boundary="review.verify-major",
            )


STUB = """#!{python}
import pathlib, sys
if "--version" in sys.argv:
    print("2.1.284")
    sys.exit(0)
pathlib.Path({marker!r}).write_text("called")
sys.exit(1)
"""


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name).resolve()
        self.stubs = self.directory / "bin"
        self.stubs.mkdir()
        self.marker = self.directory / "provider-called"
        for name in ("claude", "codex"):
            path = self.stubs / name
            path.write_text(STUB.format(python=sys.executable, marker=str(self.marker)))
            path.chmod(0o755)
        self.environment = {
            "PATH": f"{self.stubs}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(self.directory),
            "PYTHONPATH": str(ROOT),
        }
        for name in ("claude", "codex"):
            found = shutil.which(name, path=self.environment["PATH"])
            self.assertEqual(str(self.stubs / name), found, "a real provider CLI would be reachable")
        self.prompt = self.directory / "prompt.md"
        self.prompt.write_text("Review this change.\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def model_run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aitk.cli", "--root", str(ROOT), "model-run", "review",
             "--provider", "claude", "--boundary", "review.independent",
             "--prompt-file", str(self.prompt), "--cwd", str(ROOT), *arguments],
            cwd=self.directory, text=True, capture_output=True, check=False, env=self.environment,
        )

    def test_a_dry_run_records_the_experiment_and_calls_no_worker(self) -> None:
        result = self.model_run(
            "--dry-run", "--experiment", "reviewer-runs-test", "--test-command", TEST_COMMAND
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual([TEST_COMMAND], payload["experiment"]["allowed_commands"])
        self.assertIn(f"Bash({TEST_COMMAND})", payload["argv"])
        self.assertFalse(self.marker.exists())

    def test_a_bad_allowlist_exits_two_without_a_worker(self) -> None:
        for arguments in (
            ("--test-command", "npm test"),
            ("--experiment", "reviewer-runs-test"),
            ("--experiment", "reviewer-runs-test", "--test-command", "npm test && curl example.com"),
        ):
            with self.subTest(arguments=arguments):
                result = self.model_run("--dry-run", *arguments)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual("MODEL_ROUTE_INVALID", json.loads(result.stdout)["error"]["code"])
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
