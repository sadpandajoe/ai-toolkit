from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from aitk.doctor import _personal_paths, _secret_output, run_doctor


ROOT = Path(__file__).resolve().parents[1]


class DoctorTests(unittest.TestCase):
    def make_clean_repo(self, root: Path) -> None:
        (root / "skills/example/references").mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("See [the example](skills/example/SKILL.md).\n")
        (root / "skills/example/SKILL.md").write_text(
            "---\n"
            "name: example\n"
            "description: Use when an example is needed. Do NOT use for real work.\n"
            "---\n\n"
            "Read [details](references/details.md).\n"
        )
        (root / "skills/example/references/details.md").write_text("# Details\n")

    def test_clean_fixture_has_no_failures_or_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            findings = run_doctor(root)
            problems = [finding for finding in findings if finding.status != "PASS"]
            self.assertEqual([], problems)

    def test_broken_link_fails_and_bad_description_is_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "skills/example/SKILL.md").write_text(
                "---\nname: example\ndescription: Example helper.\n---\n"
                "[missing](references/missing.md)\n"
            )
            findings = run_doctor(root)
            messages = "\n".join(
                f"{finding.status} {finding.message} {' '.join(finding.details)}"
                for finding in findings
            )
            # The routing halves of a description are advice: reported, not failed.
            self.assertIn(
                "PASS Skill descriptions advisory: skills/example/SKILL.md: "
                "description lacks positive and negative routing",
                messages,
            )
            self.assertIn("FAIL Markdown links", messages)

    def test_skill_frontmatter_shape_still_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            (root / "skills/example/SKILL.md").write_text(
                "---\nname: example\ndescription: Use when needed. Do NOT use otherwise.\n"
                "model: opus\n---\n"
            )
            finding = next(
                item for item in run_doctor(root) if item.check == "skill-descriptions"
            )
            self.assertEqual("DRIFT", finding.status)
            self.assertEqual(
                ("skills/example/SKILL.md: provider-specific fields model",), finding.details
            )

    def test_routing_manifest_problems_fail_the_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(
                ROOT, root, ignore=shutil.ignore_patterns(".git", "build", "__pycache__")
            )
            findings = {item.check: item for item in run_doctor(root)}
            self.assertEqual("PASS", findings["model-routing"].status)
            manifest = root / "interfaces/model-routing.json"
            payload = json.loads(manifest.read_text())
            payload["dispatch_boundaries"][0]["routes"] = ["no-such-route"]
            manifest.write_text(json.dumps(payload))
            findings = {item.check: item for item in run_doctor(root)}
            self.assertEqual("FAIL", findings["model-routing"].status)

    def test_personal_absolute_paths_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_clean_repo(root)
            self.assertEqual("PASS", _personal_paths(root).status)
            (root / "skills/example/references/details.md").write_text(
                "Run /Users/someone/tools/run.sh\n"
            )
            finding = _personal_paths(root)
            self.assertEqual("FAIL", finding.status)
            self.assertEqual(("skills/example/references/details.md",), finding.details)

    def test_secret_output_scanner_covers_shell_and_python_sinks(self) -> None:
        cases = {
            "echo.sh": 'echo "$GH_TOKEN"\n',
            "printf.sh": "printf '%s\\n' \"${API_KEY}\"\n",
            "trace.sh": "set -x\nrun_command\n",
            "print.py": 'import os\nprint(os.environ["GH_TOKEN"])\n',
            "logging.py": "import logging\napi_key = 'value'\nlogging.info('%s', api_key)\n",
            "raise.py": "secret = 'value'\nraise RuntimeError(secret)\n",
        }
        for filename, content in cases.items():
            with self.subTest(
                filename=filename
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / filename).write_text(content)

                finding = _secret_output(root)

                self.assertEqual("FAIL", finding.status)
                self.assertIn(filename, finding.details)

    def test_secret_output_scanner_ignores_environment_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dependency = root / ".venv/lib/python/site-packages/dependency.py"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("print(API_TOKEN)\n")

            finding = _secret_output(root)

            self.assertEqual("PASS", finding.status)
            self.assertEqual((), finding.details)

if __name__ == "__main__":
    unittest.main()
