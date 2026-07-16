"""Fail-closed configuration preflight for optional PGM workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, TypeVar


WORKFLOWS = {"create-status-report", "create-velocity-report"}
VELOCITY_FILES = (
    "run.md",
    "collect_github.py",
    "collect_shortcut.py",
    "analyze.py",
    "report.py",
)
T = TypeVar("T")


class PGMPreflightError(RuntimeError):
    """PGM collection must not start because configuration is not ready."""


@dataclass(frozen=True)
class PGMPreflightResult:
    workflow: str
    status: str
    config: str
    findings: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "ready" else 1

    def as_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "status": self.status,
            "config": self.config,
            "findings": list(self.findings),
        }


def _objects(
    value: object, name: str, *, nonempty: bool
) -> tuple[list[object], list[str]]:
    problems: list[str] = []
    if isinstance(value, list):
        entries = value
    elif isinstance(value, dict):
        entries = list(value.values())
    else:
        return [], [f"config field {name} must be a list or object"]
    if nonempty and not entries:
        problems.append(f"config field {name} cannot be empty")
    if any(not isinstance(item, dict) for item in entries):
        problems.append(f"config field {name} entries must be objects")
    return entries, problems


def _nonempty_string(entry: dict[str, object], *names: str) -> bool:
    return any(
        isinstance(entry.get(name), str) and bool(str(entry[name]).strip())
        for name in names
    )


def _team_assignments(entry: dict[str, object]) -> list[str]:
    assignments: list[str] = []
    for name in ("team", "team_id", "team_uuid"):
        value = entry.get(name)
        if isinstance(value, str) and value.strip():
            assignments.append(value.strip())
    teams = entry.get("teams")
    if isinstance(teams, str) and teams.strip():
        assignments.append(teams.strip())
    elif isinstance(teams, list):
        assignments.extend(
            value.strip() for value in teams if isinstance(value, str) and value.strip()
        )
    return assignments


def _valid_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_config(workflow: str, payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["config.json must contain a JSON object"]
    problems: list[str] = []
    team_entries: list[object] = []
    for field in ("teams", "members", "repos"):
        if field not in payload:
            problems.append(f"config field {field} is required")
        else:
            entries, entry_problems = _objects(payload[field], field, nonempty=True)
            problems.extend(entry_problems)
            if field == "teams":
                team_entries = entries
    team_identities = {
        str(entry[name]).strip()
        for entry in team_entries
        if isinstance(entry, dict)
        for name in ("id", "uuid", "name")
        if isinstance(entry.get(name), str) and str(entry[name]).strip()
    }
    for field in ("teams", "members", "repos"):
        if field not in payload:
            continue
        entries, _ = _objects(payload[field], field, nonempty=True)
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if field == "teams":
                if not _nonempty_string(entry, "name") or not _nonempty_string(
                    entry, "id", "uuid"
                ):
                    problems.append(
                        f"config field teams entry {index} needs name and id or uuid"
                    )
            if field == "members":
                missing: list[str] = []
                if not _nonempty_string(entry, "name"):
                    missing.append("name")
                if not _nonempty_string(entry, "github", "github_handle"):
                    missing.append("GitHub handle")
                if not _nonempty_string(entry, "shortcut_id", "shortcut_uuid"):
                    missing.append("Shortcut ID")
                assignments = _team_assignments(entry)
                if not assignments:
                    missing.append("team assignment")
                if missing:
                    problems.append(
                        f"config field members entry {index} needs "
                        + ", ".join(missing)
                    )
                elif any(value not in team_identities for value in assignments):
                    problems.append(
                        f"config field members entry {index} has an unknown team assignment"
                    )
            if field == "repos":
                if not _nonempty_string(entry, "name") or not _nonempty_string(
                    entry, "path"
                ):
                    problems.append(
                        f"config field repos entry {index} needs name and path"
                    )
                else:
                    repository = Path(str(entry["path"])).expanduser()
                    if not repository.is_dir():
                        problems.append(
                            f"config field repos entry {index} path must be an existing directory"
                        )
                assignments = _team_assignments(entry)
                if not assignments:
                    problems.append(
                        f"config field repos entry {index} needs a team relationship"
                    )
                elif any(value not in team_identities for value in assignments):
                    problems.append(
                        f"config field repos entry {index} has an unknown team relationship"
                    )
                strategy = entry.get("strategy", entry.get("collection_strategy"))
                if strategy not in {"per_member", "all_prs"}:
                    problems.append(
                        f"config field repos entry {index} needs strategy per_member or all_prs"
                    )
    bots = payload.get("bots")
    if not isinstance(bots, list) or any(not isinstance(item, str) for item in bots):
        problems.append("config field bots must be a list of account names")
    if workflow == "create-velocity-report":
        month = payload.get("month")
        if (
            not isinstance(month, str)
            or re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", month) is None
        ):
            problems.append("velocity config field month must use YYYY-MM")
        date_range = payload.get("date_range")
        if not isinstance(date_range, dict) or set(date_range) != {"start", "end"}:
            problems.append(
                "velocity config field date_range must contain start and end"
            )
        elif not _valid_date(date_range["start"]) or not _valid_date(date_range["end"]):
            problems.append("velocity date_range values must use YYYY-MM-DD")
        elif str(date_range["start"]) > str(date_range["end"]):
            problems.append("velocity date_range start must not follow end")
    return problems


def preflight(
    workflow: str,
    pgm_dir: Path | None,
    *,
    environment: dict[str, str] | None = None,
    shortcut_connector: bool = False,
    github_connector: bool = False,
    github_cli_available: bool | None = None,
    github_cli_authenticated: bool | None = None,
) -> PGMPreflightResult:
    if workflow not in WORKFLOWS:
        raise ValueError(f"unknown PGM workflow: {workflow}")
    env = os.environ if environment is None else environment
    selected = pgm_dir or (Path(env["PGM_DIR"]) if env.get("PGM_DIR") else None)
    if selected is None:
        return PGMPreflightResult(
            workflow, "blocked", "", ("PGM_DIR or --pgm-dir is required",)
        )
    selected = selected.expanduser()
    config = selected / "config.json"
    findings: list[str] = []
    payload: object = None
    if selected.is_symlink() or not selected.is_dir():
        findings.append("PGM directory is missing or is a symlink")
    elif config.is_symlink() or not config.is_file():
        findings.append("PGM config.json is missing or is a symlink")
    else:
        try:
            payload = json.loads(config.read_text())
        except (OSError, json.JSONDecodeError):
            findings.append("PGM config.json is not valid readable JSON")
        else:
            findings.extend(_validate_config(workflow, payload))

    if not env.get("SHORTCUT_API_TOKEN") and not shortcut_connector:
        findings.append("Shortcut authorization or connector capability is required")
    gh_available = (
        shutil.which("gh") is not None
        if github_cli_available is None
        else github_cli_available
    )
    if github_cli_authenticated is None:
        if not gh_available:
            gh_authenticated = False
        elif env.get("GH_TOKEN") or env.get("GITHUB_TOKEN"):
            gh_authenticated = True
        else:
            try:
                gh_authenticated = (
                    subprocess.run(
                        ["gh", "auth", "status"],
                        env=dict(env),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    ).returncode
                    == 0
                )
            except OSError:
                gh_authenticated = False
    else:
        gh_authenticated = github_cli_authenticated
    if not (gh_available and gh_authenticated) and not github_connector:
        findings.append("GitHub CLI authorization or connector capability is required")
    if (
        workflow == "create-velocity-report"
        and selected.is_dir()
        and not selected.is_symlink()
    ):
        for name in VELOCITY_FILES:
            target = selected / name
            if target.is_symlink() or not target.is_file():
                findings.append(f"velocity pipeline file is missing or unsafe: {name}")
    return PGMPreflightResult(
        workflow,
        "ready" if not findings else "blocked",
        str(config.resolve(strict=False)),
        tuple(findings),
    )


def run_after_preflight(
    workflow: str,
    pgm_dir: Path | None,
    effect: Callable[[dict[str, object]], T],
    **options: object,
) -> T:
    result = preflight(workflow, pgm_dir, **options)  # type: ignore[arg-type]
    if result.status != "ready":
        raise PGMPreflightError("; ".join(result.findings))
    second = preflight(workflow, pgm_dir, **options)  # type: ignore[arg-type]
    if second.status != "ready":
        raise PGMPreflightError(
            "PGM prerequisites changed: " + "; ".join(second.findings)
        )
    environment = options.get("environment")
    selected_environment = environment if isinstance(environment, dict) else os.environ
    selected = pgm_dir or Path(str(selected_environment.get("PGM_DIR", "")))
    config = selected.expanduser() / "config.json"
    if config.is_symlink() or not config.is_file():
        raise PGMPreflightError("PGM config changed after preflight")
    try:
        payload = json.loads(config.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PGMPreflightError("PGM config changed after preflight") from error
    problems = _validate_config(workflow, payload)
    if problems:
        raise PGMPreflightError(
            "PGM config changed after preflight: " + "; ".join(problems)
        )
    return effect(payload)
