from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


# The standing PII and secret scan over tracked files. Placeholders pass: a
# repeated-digit or 12345 story id, `<org>`/`<ws>` slots, made-up workspaces.
PLACEHOLDER_ID = re.compile(r"^(?:12345|(\d)\1+)$")
LEAK_PATTERNS = (
    ("Shortcut story URL", re.compile(r"app\.shortcut\.com/[\w-]+/story/(\d+)")),
    ("Shortcut story id", re.compile(r"\bsc-(\d{5,})\b", re.IGNORECASE)),
    (
        "internal workspace host",
        re.compile(
            r"\b(?=[0-9a-f]{0,7}\d)[0-9a-f]{8}\.(?:[a-z0-9-]+\.)*app(?:-stg|-dev)?\.preset\.io\b",
            re.IGNORECASE,
        ),
    ),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{22,})")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("API key", re.compile(r"\bsk-(?:ant-[\w-]{20,}|(?:proj-)?[A-Za-z0-9]{32,})")),
    ("Google API key", re.compile(r"\bAIza[\w-]{35}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
FIXTURE_DIRECTORIES = ("tests/fixtures/",)


def tracked_files() -> list[Path] | None:
    try:
        listing = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        return None
    return [
        ROOT / name
        for name in listing.split("\0")
        if name and not name.startswith(FIXTURE_DIRECTORIES) and (ROOT / name).is_file()
    ]


def leak_findings(paths: list[Path], root: Path = ROOT) -> list[str]:
    findings = []
    for path in paths:
        data = path.read_bytes()
        if b"\0" in data:
            continue
        for line_number, line in enumerate(data.decode(errors="replace").splitlines(), 1):
            for label, pattern in LEAK_PATTERNS:
                for match in pattern.finditer(line):
                    if match.groups() and PLACEHOLDER_ID.match(match.group(1) or ""):
                        continue
                    findings.append(f"{path.relative_to(root)}:{line_number}: {label}: {match.group(0)}")
    return findings


# A fenced example that evals its arguments runs whatever string a caller hands
# it; command substitution such as `eval "$(brew shellenv)"` is not an argument.
EVALUATED_ARGUMENT = re.compile(r"\beval\s+\"?\$(?:[0-9@*]|\{[0-9@*])")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def fenced_eval_findings(paths: list[Path], root: Path = ROOT) -> list[str]:
    findings = []
    for path in paths:
        opened: str | None = None
        for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            marker = FENCE.match(line)
            if marker is not None:
                token = marker.group(1)
                if opened is None:
                    opened = token
                elif token[0] == opened[0] and len(token) >= len(opened):
                    opened = None
                continue
            if opened is not None and EVALUATED_ARGUMENT.search(line):
                findings.append(f"{path.relative_to(root)}:{line_number}: {line.strip()}")
    return findings


class SafetyInvariantTests(unittest.TestCase):
    def test_tracked_files_carry_no_pii_or_secrets(self) -> None:
        files = tracked_files()
        if files is None:
            self.skipTest("not a git checkout")
        self.assertEqual([], leak_findings(files))

    def test_the_leak_scan_catches_seeded_values(self) -> None:
        # Seeds are assembled at run time so this file holds no literal leak.
        story = "https://app.shortcut.com/" + "acme/story/" + "48213"
        seeded = {
            "Shortcut story URL": f"See {story}#activity-77",
            "Shortcut story id": "Fixes " + "sc-" + "48213.",
            "internal workspace host": "https://" + "9f3c2a1b" + ".us1a.app-stg.preset.io/",
            "GitHub token": "token=" + "ghp_" + "A1b2C3d4" * 5,
            "AWS access key": "AKIA" + "ABCDEFGH" + "12345678",
            "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
        }
        placeholders = (
            "Story: https://app.shortcut.com/<org>/story/<story-id>",
            "create-feature sc-12345 or sc-NNNNN",
            "https://<ws>.us1a.app-stg.preset.io and ws1.us1a.app-dev.preset.io",
            "`app.preset.io`, manage.app-stg.preset.io",
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for index, (label, text) in enumerate(seeded.items()):
                with self.subTest(seed=label):
                    path = base / f"seed-{index}.md"
                    path.write_text(f"intro\n{text}\n")
                    findings = leak_findings([path], base)
                    self.assertTrue(any(f"seed-{index}.md:2: {label}:" in item for item in findings), findings)
            clean = base / "placeholders.md"
            clean.write_text("\n".join(placeholders) + "\n")
            self.assertEqual([], leak_findings([clean], base))

    def test_rbac_seed_is_dry_run_and_never_targets_production(self) -> None:
        text = read("skills/preset-rbac-setup/SKILL.md")
        lowered = text.lower()
        self.assertIn("dry-run by default", lowered)
        self.assertIn("--apply", text)
        self.assertNotIn("default to pre-cleaning", lowered)
        self.assertNotIn("without explicit confirmation", lowered)
        self.assertIn("refuse", lowered)

    def test_all_local_workflow_state_is_hook_protected(self) -> None:
        # The wrapper hands every command to hooks/lib/git_guard.py, which
        # blocks commits of the files in its STATE_FILES.
        hook_lib = str(ROOT / "hooks" / "lib")
        sys.path.insert(0, hook_lib)
        self.addCleanup(sys.path.remove, hook_lib)
        from git_guard import STATE_FILES

        for stem in (
            "PROJECT",
            "PROJECT_ARCHIVE",
            "PLAN",
            "WATCH",
            "CHERRY_PICK",
            "CI_FIX",
        ):
            self.assertIn(f"{stem}.md", STATE_FILES)
        # -E -s keep PYTHONPATH and the user site from replacing the guard's imports.
        self.assertIn('python3 -E -s "$ROOT/hooks/lib/git_guard.py"', read("hooks/prevent-project-commit.sh"))

    def test_no_fenced_example_evals_its_arguments(self) -> None:
        files = tracked_files()
        if files is None:
            self.skipTest("not a git checkout")
        self.assertEqual([], fenced_eval_findings([path for path in files if path.suffix == ".md"]))

    def test_the_eval_scan_reads_every_fenced_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            seeded = base / "seeded.md"
            seeded.write_text(
                "Prose may say eval \"$1\" is unsafe.\n\n"
                "```bash\nretry() { eval \"$1\"; }\n```\n\n"
                "~~~sh\nrun() { eval \"$@\"; }\n~~~\n\n"
                "```sh\neval \"$(brew shellenv)\"\n```\n"
            )
            self.assertEqual(
                ["seeded.md:4", "seeded.md:8"],
                [item.split(": ", 1)[0] for item in fenced_eval_findings([seeded], base)],
            )


if __name__ == "__main__":
    unittest.main()
