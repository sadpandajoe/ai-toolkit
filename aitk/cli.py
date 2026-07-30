"""Command-line interface for AI Toolkit maintenance."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

from .build import compare_build, write_build
from .checkpoint import (
    CheckpointError,
    advance as advance_checkpoint,
    apply as apply_checkpoint,
    checkpoint_file,
    initialize as initialize_checkpoint,
    reserve as reserve_checkpoint,
    validate as validate_checkpoint,
)
from .conformance import contracts_by_name, route_workflow, workflow_dependencies
from .doctor import run_doctor
from .installer import install, resolve_paths, rollback, uninstall
from .model_routing import ModelRouteError, resolve_route, run_model
from .pgm import preflight as pgm_preflight
from .workflows import load_workflows


def _root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    working_directory = Path.cwd().resolve()
    for candidate in (working_directory, *working_directory.parents):
        if (candidate / "interfaces/workflows.json").is_file():
            return candidate
    source_root = Path(__file__).resolve().parents[1]
    if (source_root / "interfaces/workflows.json").is_file():
        return source_root
    raise FileNotFoundError(
        "AI Toolkit repository not found; run inside a checkout or pass --root <path>"
    )


def _print(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload["command"] == "build":
        differences = payload.get("differences", [])
        if differences:
            print("Build drift:")
            for difference in differences:
                print(f"  {difference}")
        else:
            print("Build is current.")
        return
    summary = payload["summary"]
    print(
        f"Doctor: {summary['PASS']} pass, {summary['DRIFT']} drift, {summary['FAIL']} fail"
    )
    for finding in payload["findings"]:
        print(f"[{finding['status']}] {finding['message']}")
        for detail in finding["details"]:
            print(f"  {detail}")


def _build(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    if arguments.check:
        differences = compare_build(root, arguments.with_pgm)
        payload: dict[str, object] = {"command": "build", "differences": differences}
    else:
        result = write_build(root, arguments.with_pgm)
        differences = compare_build(root, arguments.with_pgm)
        payload = {
            "command": "build",
            "differences": differences,
            "written": result.written,
            "unchanged": result.unchanged,
            "removed": [path.as_posix() for path in result.removed],
        }
    _print(payload, arguments.json)
    return 1 if differences else 0


def _doctor(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    installed_paths = (
        resolve_paths(
            root,
            Path(arguments.home) if arguments.home else None,
            Path(arguments.codex_home) if arguments.codex_home else None,
            Path(arguments.agents_dir) if arguments.agents_dir else None,
        )
        if arguments.installed
        else None
    )
    findings = run_doctor(
        root, installed_paths=installed_paths, with_pgm=arguments.with_pgm
    )
    summary = {
        status: sum(finding.status == status for finding in findings)
        for status in ("PASS", "DRIFT", "FAIL")
    }
    payload: dict[str, object] = {
        "command": "doctor",
        "summary": summary,
        "findings": [asdict(finding) for finding in findings],
    }
    _print(payload, arguments.json)
    return 1 if summary["FAIL"] or (arguments.strict and summary["DRIFT"]) else 0


def _list(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    workflows = load_workflows(root, include_pgm=arguments.with_pgm)
    contracts = contracts_by_name(root) if arguments.details else {}
    items: list[dict[str, object]] = []
    for workflow in workflows:
        item: dict[str, object] = {
            "name": workflow.name,
            "summary": workflow.summary,
            "arguments": workflow.arguments,
        }
        if arguments.details:
            contract = contracts[workflow.name]
            item.update(
                {
                    "owner_skill": workflow.owner_skill,
                    "reference": workflow.reference.as_posix(),
                    "rules": list(workflow.rules),
                    "dependencies": list(workflow_dependencies(root, workflow)),
                    "effect": contract["effect"],
                    "authorization": contract["authorization"],
                    "state": contract["state"],
                    "resumable": contract["resumable"],
                    "phases": contract["phases"],
                    "gates": contract["authorization"]["gates"],
                }
            )
        items.append(item)
    payload: dict[str, object] = {
        "command": "list",
        "workflows": items,
    }
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for workflow in workflows:
            arguments_hint = f" {workflow.arguments}" if workflow.arguments else ""
            print(f"{workflow.name}{arguments_hint}\n  {workflow.summary}")
    return 0


def _route(arguments: argparse.Namespace) -> int:
    request = " ".join(arguments.request)
    match = route_workflow(
        _root(arguments.root), request, include_pgm=arguments.with_pgm
    )
    payload: dict[str, object] = {"command": "route", "request": request, "match": None}
    if match is not None:
        payload["match"] = {
            "workflow": match.workflow.name,
            "summary": match.workflow.summary,
            "trigger": match.trigger,
            "invoke": f"Use ${match.workflow.owner_skill} in {match.workflow.name} mode for: {request}",
        }
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif match is None:
        print("No toolkit workflow matched; handle the request directly.")
    else:
        print(f"{match.workflow.name}: {match.workflow.summary}")
        print(
            f"Invoke: Use ${match.workflow.owner_skill} in {match.workflow.name} mode for: {request}"
        )
    return 0 if match is not None else 1


def _model_route(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    try:
        route = resolve_route(
            root,
            arguments.model_route,
            arguments.provider,
            arguments.boundary,
            arguments.lens,
        )
    except ModelRouteError as error:
        if arguments.json:
            print(
                json.dumps(
                    {
                        "command": "model-route",
                        "error": {"code": error.code, "message": str(error)},
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    payload = {"command": "model-route", **route.as_dict()}
    if arguments.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key in (
            "route",
            "provider",
            "family",
            "selector",
            "effort",
            "responsibility",
            # An unscored lane must return an empty findings array or the run
            # fails, so an operator reading this output needs to see it. The lens
            # domain is here for the same reason: it decides which severity
            # vocabulary the result is checked against, so a lane resolved
            # without it is a lane whose findings will not be graded.
            "unscored",
            "lens",
            "lens_domain",
            "controls",
        ):
            value = payload[key]
            rendered = (
                json.dumps(value, separators=(",", ":"), sort_keys=True)
                if isinstance(value, dict)
                else value
            )
            print(f"{key}: {rendered}")
    return 0


def _model_run(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    try:
        exit_code, payload = run_model(
            root,
            arguments.model_route,
            arguments.provider,
            arguments.boundary,
            Path(arguments.prompt_file),
            Path(arguments.cwd) if arguments.cwd else None,
            arguments.timeout_seconds,
            arguments.dry_run,
            lens=arguments.lens,
        )
    except ModelRouteError as error:
        print(
            json.dumps(
                {
                    "command": "model-run",
                    "error": {"code": error.code, "message": str(error)},
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(payload, sort_keys=True))
    return exit_code


def _lifecycle(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    paths = resolve_paths(
        root,
        Path(arguments.home) if arguments.home else None,
        Path(arguments.codex_home) if arguments.codex_home else None,
        Path(arguments.agents_dir) if arguments.agents_dir else None,
    )
    if arguments.command == "install":
        result = install(paths, with_pgm=arguments.with_pgm)
    elif arguments.command == "uninstall":
        result = uninstall(paths)
    else:
        result = rollback(paths)
    payload = result.as_dict()
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{result.operation}: {result.status}")
        for value in result.changed:
            print(f"  changed: {value}")
        for value in result.conflicts:
            print(f"  {value}", file=sys.stderr)
        print(f"  ledger: {result.ledger}")
    return result.exit_code


def _checkpoint(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    try:
        path = checkpoint_file(
            root,
            arguments.workflow,
            Path(arguments.file) if arguments.file else None,
            arguments.with_pgm,
        )
        if arguments.checkpoint_action == "init":
            result = initialize_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.with_pgm,
                arguments.replace,
            )
        elif arguments.checkpoint_action == "validate":
            result = validate_checkpoint(
                root, arguments.workflow, path, arguments.with_pgm
            )
        elif arguments.checkpoint_action == "advance":
            result = advance_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.to,
                arguments.with_pgm,
            )
        elif arguments.checkpoint_action == "reserve":
            result = reserve_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.key,
                arguments.operation_id,
                arguments.with_pgm,
            )
        else:
            result = apply_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.key,
                arguments.operation_id,
                arguments.result_digest,
                arguments.with_pgm,
            )
    except (CheckpointError, OSError, json.JSONDecodeError) as error:
        print(f"aitk checkpoint: {error}", file=sys.stderr)
        return 1
    payload = result.as_dict()
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        disposition = "updated" if result.changed else "unchanged"
        print(
            f"{result.workflow}: phase={result.phase} generation={result.generation} "
            f"({disposition})"
        )
        print(f"  checkpoint: {result.file}")
    return 0


def _pgm_preflight(arguments: argparse.Namespace) -> int:
    result = pgm_preflight(
        arguments.workflow,
        Path(arguments.pgm_dir) if arguments.pgm_dir else None,
        shortcut_connector=arguments.shortcut_connector,
        github_connector=arguments.github_connector,
    )
    payload = result.as_dict()
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{result.workflow}: {result.status}")
        for finding in result.findings:
            print(f"  {finding}", file=sys.stderr)
        if result.config:
            print(f"  config: {result.config}")
    return result.exit_code


def _check(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    differences = compare_build(root)
    findings = run_doctor(root)
    doctor_problems = [finding for finding in findings if finding.status != "PASS"]
    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    hook_path = root / "hooks/test-prevent-project-commit.sh"
    hook = (
        subprocess.run(
            ["bash", str(hook_path)],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if hook_path.is_file()
        else None
    )
    payload: dict[str, object] = {
        "command": "check",
        "build": "PASS" if not differences else "FAIL",
        "doctor": "PASS" if not doctor_problems else "FAIL",
        "tests": "PASS" if tests.returncode == 0 else "FAIL",
        "hook-tests": "PASS" if hook is not None and hook.returncode == 0 else "FAIL",
        "differences": differences,
        "doctor_problems": [asdict(finding) for finding in doctor_problems],
    }
    if arguments.json:
        payload["test_output"] = tests.stderr
        payload["hook_output"] = "" if hook is None else hook.stdout + hook.stderr
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Build: {payload['build']}")
        print(f"Doctor: {payload['doctor']}")
        print(f"Tests: {payload['tests']}")
        print(f"Hook tests: {payload['hook-tests']}")
        if tests.returncode:
            print(tests.stderr)
        if hook is not None and hook.returncode:
            print(hook.stdout + hook.stderr)
    return (
        0
        if all(
            payload[key] == "PASS" for key in ("build", "doctor", "tests", "hook-tests")
        )
        else 1
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="aitk", description="Build and validate AI Toolkit"
    )
    result.add_argument("--root", help="Toolkit repository root")
    subparsers = result.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="generate provider-facing files")
    build.add_argument(
        "--check", action="store_true", help="report drift without writing"
    )
    build.add_argument(
        "--json", action="store_true", help="emit machine-readable output"
    )
    build.add_argument(
        "--with-pgm", action="store_true", help="validate the optional PGM extension"
    )
    build.set_defaults(handler=_build)

    doctor = subparsers.add_parser("doctor", help="run repository health checks")
    doctor.add_argument(
        "--json", action="store_true", help="emit machine-readable output"
    )
    doctor.add_argument("--strict", action="store_true", help="treat drift as failure")
    doctor.add_argument(
        "--installed",
        action="store_true",
        help="also inspect installed ownership state",
    )
    doctor.add_argument(
        "--with-pgm", action="store_true", help="expect the optional PGM extension"
    )
    doctor.add_argument(
        "--home", help="selected home directory for installed-state checks"
    )
    doctor.add_argument("--codex-home", help="selected Codex home directory")
    doctor.add_argument("--agents-dir", help="selected Agent Skills directory")
    doctor.set_defaults(handler=_doctor)

    listing = subparsers.add_parser("list", help="list stable public workflows")
    listing.add_argument(
        "--json", action="store_true", help="emit machine-readable output"
    )
    listing.add_argument(
        "--with-pgm", action="store_true", help="include optional PGM workflows"
    )
    listing.add_argument(
        "--details", action="store_true", help="include contract and ownership details"
    )
    listing.set_defaults(handler=_list)

    route = subparsers.add_parser("route", help="match a request to a public workflow")
    route.add_argument("request", nargs="+", help="natural-language request")
    route.add_argument(
        "--json", action="store_true", help="emit machine-readable output"
    )
    route.add_argument(
        "--with-pgm", action="store_true", help="include optional PGM workflows"
    )
    route.set_defaults(handler=_route)

    model_route = subparsers.add_parser(
        "model-route", help="resolve a stable worker route to model and effort"
    )
    model_route.add_argument("model_route")
    model_route.add_argument("--provider", required=True, choices=("codex", "claude"))
    model_route.add_argument("--boundary")
    model_route.add_argument(
        "--lens",
        help="repo-relative reviewer lens to narrow a fan-out boundary to",
    )
    model_route.add_argument("--json", action="store_true")
    model_route.set_defaults(handler=_model_route)

    model_run = subparsers.add_parser(
        "model-run", help="run one fail-closed worker with pinned model and effort"
    )
    model_run.add_argument("model_route")
    model_run.add_argument("--provider", required=True, choices=("codex", "claude"))
    model_run.add_argument("--boundary", required=True)
    model_run.add_argument("--prompt-file", required=True)
    model_run.add_argument("--cwd")
    model_run.add_argument("--timeout-seconds", type=int, default=1800)
    model_run.add_argument("--dry-run", action="store_true")
    model_run.add_argument(
        "--lens",
        help="repo-relative reviewer lens to narrow a fan-out boundary to",
    )
    model_run.set_defaults(handler=_model_run)

    checkpoint = subparsers.add_parser(
        "checkpoint", help="manage durable workflow checkpoints"
    )
    checkpoint_actions = checkpoint.add_subparsers(
        dest="checkpoint_action", required=True
    )
    for action in ("init", "validate", "advance", "reserve", "apply"):
        checkpoint_action = checkpoint_actions.add_parser(
            action, help=f"{action} a durable workflow checkpoint"
        )
        checkpoint_action.add_argument("--workflow", required=True)
        checkpoint_action.add_argument("--file")
        checkpoint_action.add_argument("--with-pgm", action="store_true")
        checkpoint_action.add_argument("--json", action="store_true")
        if action == "init":
            checkpoint_action.add_argument(
                "--replace",
                action="store_true",
                help="replace completed or stale checkpoint state; pending effects refuse",
            )
        if action == "advance":
            checkpoint_action.add_argument("--to", required=True)
        if action in {"reserve", "apply"}:
            checkpoint_action.add_argument("--key", required=True)
            checkpoint_action.add_argument("--operation-id", required=True)
        if action == "apply":
            checkpoint_action.add_argument("--result-digest", required=True)
        checkpoint_action.set_defaults(handler=_checkpoint)

    pgm = subparsers.add_parser(
        "pgm-preflight", help="validate optional PGM configuration before collection"
    )
    pgm.add_argument(
        "--workflow",
        required=True,
        choices=sorted(("create-status-report", "create-velocity-report")),
    )
    pgm.add_argument("--pgm-dir")
    pgm.add_argument("--shortcut-connector", action="store_true")
    pgm.add_argument("--github-connector", action="store_true")
    pgm.add_argument("--json", action="store_true")
    pgm.set_defaults(handler=_pgm_preflight)

    for name in ("install", "uninstall", "rollback"):
        lifecycle = subparsers.add_parser(
            name, help=f"{name} source-linked toolkit artifacts"
        )
        lifecycle.add_argument(
            "--json", action="store_true", help="emit machine-readable output"
        )
        lifecycle.add_argument("--home", help="selected home directory")
        lifecycle.add_argument("--codex-home", help="selected Codex home directory")
        lifecycle.add_argument("--agents-dir", help="selected Agent Skills directory")
        if name == "install":
            lifecycle.add_argument(
                "--with-pgm", action="store_true", help="include optional PGM workflows"
            )
        else:
            lifecycle.set_defaults(with_pgm=False)
        lifecycle.set_defaults(handler=_lifecycle)

    check = subparsers.add_parser(
        "check", help="run the complete local conformance gate"
    )
    check.add_argument(
        "--json", action="store_true", help="emit machine-readable output"
    )
    check.set_defaults(handler=_check)
    return result


def main(arguments: list[str] | None = None) -> int:
    parsed = parser().parse_args(arguments)
    try:
        return parsed.handler(parsed)
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"aitk: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
