"""Command-line interface for AI Toolkit maintenance."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable

from .build import compare_build, write_build
from .checkpoint import (
    CheckpointError,
    accept_artifact as accept_artifact_checkpoint,
    advance as advance_checkpoint,
    apply as apply_checkpoint,
    checkpoint_file,
    initialize as initialize_checkpoint,
    read_snapshot,
    record_evidence as record_evidence_checkpoint,
    record_reclassification as record_reclassification_checkpoint,
    reserve as reserve_checkpoint,
    validate as validate_checkpoint,
)
from .conformance import contracts_by_name, route_workflow, workflow_dependencies
from .doctor import run_doctor
from .evals import EvalError, load_fixtures, run_fixture
from .evals_complexity import make_checker as _make_complexity_checker
from .evals_decomposition import make_checker as _make_decomposition_checker
from .evals_escalation import make_checker as _make_escalation_checker
from .evals_execution_shape import make_checker as _make_execution_shape_checker
from .evals_phaseability import make_checker as _make_phaseability_checker
from .evals_review_remediation import make_checker as _make_review_remediation_checker
from .evals_size import make_checker as _make_size_checker
from .evals_skill_routing import make_checker as _make_skill_routing_checker
from .installer import install, resolve_paths, rollback, uninstall
from .model_routing import (
    ModelRouteError,
    resolve_route,
    run_model,
)
from .gate_state import (
    GateStateError,
    read as read_gate_state,
    set_state as set_gate_state,
)
from .gates import FAILURE_KINDS, GATE_STATES
from .frontmatter import FrontmatterError, read_frontmatter
from .size_axis import SIZE_AXIS_FIELDS, SizeAxisError, validate_size_axis
from .pgm import preflight as pgm_preflight
from .routing import (
    COMPLEXITY_VALUES,
    RoutingStateError,
    read as read_routing_state,
    set_classification,
)
from .workflows import load_workflows


# One entry per evals/ fixture family, added alongside that family's own
# commit — see rules/rule-maintenance.md's Evals signal. Each value is a
# factory taking the resolved repo root and returning the actual per-fixture
# checker — most checkers need to read real repo content (SKILL.md
# descriptions, rule files) to catch drift, not just the fixture dict.
EVAL_CHECKERS: dict[str, Callable[[Path], Callable[[dict], tuple[bool, str]]]] = {
    "skill_routing": _make_skill_routing_checker,
    "escalation": _make_escalation_checker,
    "complexity": _make_complexity_checker,
    "size": _make_size_checker,
    "execution_shape": _make_execution_shape_checker,
    "phaseability": _make_phaseability_checker,
    "decomposition": _make_decomposition_checker,
    "review_remediation": _make_review_remediation_checker,
}

# `aitk evals-run --live` mode (PLAN.md's C4): a model-in-the-loop runner using
# the routed Sonnet transport, for families whose correctness can't be
# verified by pure structural checks alone (see each EVAL_CHECKERS docstring).
# Not implemented: `aitk.model_routing.run_model()`/`resolve_route()` require a
# declared `dispatch_boundaries` entry, and `validate_dispatch_boundaries()`
# (aitk/routing_manifest.py) only recognizes a boundary's marker inside a
# `skills/**/*.md` or `extensions/*/skills/**/*.md` file, immediately
# preceding dispatch prose. This CLI harness has no skill file and no
# dispatch prose to put a marker in — registering a boundary here would mean
# writing a fake skill file solely to satisfy the validator. There is
# deliberately no per-family checker table for this mode: until the transport
# grows a non-skill dispatch path (or this harness gets its own provider
# invocation independent of interfaces/model-routing.json), no family can be
# live-checked, so `--live` always refuses rather than offering a lookup that
# could never be populated without first resolving the blocker.


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
        if arguments.command == "install" and result.exit_code == 0:
            print("")
            print("Recommended provider settings (not set automatically):")
            print(
                "  CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000  "
                "(keeps parent context from compacting mid-phase; "
                "worker isolation stays primary)"
            )
            print(
                "  CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2  "
                "(enforces the shallow spawn depth in "
                "rules/resource-management.md)"
            )
            print(
                "  See rules/context-management.md's "
                "'Recommended Provider Settings' section."
            )
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
        elif arguments.checkpoint_action == "apply":
            result = apply_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.key,
                arguments.operation_id,
                arguments.result_digest,
                arguments.with_pgm,
            )
        elif arguments.checkpoint_action in {
            "accept-rca",
            "accept-decomposition",
            "accept-phase-plan",
        }:
            field = arguments.checkpoint_action.replace("accept-", "accepted_").replace(
                "-", "_"
            )
            result = accept_artifact_checkpoint(
                root,
                arguments.workflow,
                path,
                field,
                arguments.pointer,
                arguments.with_pgm,
            )
        elif arguments.checkpoint_action == "record-evidence":
            result = record_evidence_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.pointer,
                arguments.with_pgm,
            )
        else:
            result = record_reclassification_checkpoint(
                root,
                arguments.workflow,
                path,
                arguments.reason,
                arguments.from_complexity,
                arguments.to_complexity,
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


def _project_state_file(arguments: argparse.Namespace) -> Path:
    if arguments.file:
        expanded = Path(arguments.file).expanduser()
        return expanded if expanded.is_absolute() else Path.cwd() / expanded
    return Path.cwd() / "PROJECT.md"


def _project_state(arguments: argparse.Namespace) -> int:
    path = _project_state_file(arguments)
    try:
        checkpoint_snapshot = read_snapshot(path)
        routing_snapshot = read_routing_state(path)
        gate_snapshot = read_gate_state(path)
        frontmatter = read_frontmatter(path) if path.is_file() else {}
        validate_size_axis(frontmatter)
    except (CheckpointError, RoutingStateError, GateStateError, FrontmatterError, SizeAxisError) as error:
        print(f"aitk project-state: {error}", file=sys.stderr)
        return 1
    size_axis_snapshot = {
        field: frontmatter[field] for field in SIZE_AXIS_FIELDS if field in frontmatter
    }
    payload = {
        "file": str(path),
        "checkpoint": checkpoint_snapshot,
        "routing": routing_snapshot,
        "gates": gate_snapshot,
        "size_axis": size_axis_snapshot,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _routing_state(arguments: argparse.Namespace) -> int:
    path = _project_state_file(arguments)
    try:
        payload = set_classification(
            path, arguments.complexity, arguments.confidence, arguments.reason
        )
    except (CheckpointError, RoutingStateError) as error:
        print(f"aitk routing-state: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"routing-state: complexity={payload['complexity']} "
            f"confidence={payload['confidence']}"
        )
        print(f"  file: {path}")
    return 0


def _gate_state(arguments: argparse.Namespace) -> int:
    path = _project_state_file(arguments)
    try:
        record = set_gate_state(
            path,
            arguments.gate,
            arguments.state,
            arguments.reason,
            arguments.count,
            arguments.kind,
        )
    except (CheckpointError, GateStateError) as error:
        print(f"aitk gate-state: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(
            f"gate-state: gate={arguments.gate} state={record['state']} "
            f"count={record['count']} kind={record['kind']}"
        )
        print(f"  file: {path}")
    return 0


def _evals_run(arguments: argparse.Namespace) -> int:
    if arguments.live:
        print(
            "aitk evals-run --live: not implemented. The routed transport requires "
            "a declared dispatch boundary whose marker lives in a scanned "
            "skills/**/*.md file immediately preceding dispatch prose "
            "(aitk/routing_manifest.py's validate_dispatch_boundaries); a CLI "
            "harness has no skill file to put one in. Run without --live for "
            "structural mode.",
            file=sys.stderr,
        )
        return 1
    checker_factory = EVAL_CHECKERS.get(arguments.family)
    if checker_factory is None:
        print(
            f"aitk evals-run: no checker registered for family '{arguments.family}'"
            f" (known: {sorted(EVAL_CHECKERS) or 'none'})",
            file=sys.stderr,
        )
        return 1
    root = _root(arguments.root)
    checker = checker_factory(root)
    family_dir = root / "evals" / arguments.family
    try:
        fixtures = load_fixtures(family_dir)
    except EvalError as error:
        print(f"aitk evals-run: {error}", file=sys.stderr)
        return 1
    if not fixtures:
        print(f"evals-run: no fixtures found under {family_dir}")
        return 0
    results = [run_fixture(fixture, checker) for fixture in fixtures]
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.name}: {result.reason}")
    print(f"evals-run: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


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
    model_run.set_defaults(handler=_model_run)

    checkpoint = subparsers.add_parser(
        "checkpoint", help="manage durable workflow checkpoints"
    )
    checkpoint_actions = checkpoint.add_subparsers(
        dest="checkpoint_action", required=True
    )
    for action in (
        "init",
        "validate",
        "advance",
        "reserve",
        "apply",
        "accept-rca",
        "accept-decomposition",
        "accept-phase-plan",
        "record-evidence",
        "record-reclassification",
    ):
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
        if action.startswith("accept-") or action == "record-evidence":
            checkpoint_action.add_argument("--pointer", required=True)
        if action == "record-reclassification":
            checkpoint_action.add_argument("--reason", required=True)
            checkpoint_action.add_argument("--from", dest="from_complexity", required=True)
            checkpoint_action.add_argument("--to", dest="to_complexity", required=True)
        checkpoint_action.set_defaults(handler=_checkpoint)

    project_state = subparsers.add_parser(
        "project-state",
        help="read the routing snapshot from PROJECT.md without loading history",
    )
    project_state.add_argument("--file")
    project_state.set_defaults(handler=_project_state)

    routing_state = subparsers.add_parser(
        "routing-state", help="record the complexity-gate classification snapshot"
    )
    routing_actions = routing_state.add_subparsers(
        dest="routing_action", required=True
    )
    routing_set = routing_actions.add_parser(
        "set", help="set the routing-state classification"
    )
    routing_set.add_argument("--file")
    routing_set.add_argument(
        "--complexity", required=True, choices=sorted(COMPLEXITY_VALUES)
    )
    routing_set.add_argument("--confidence", required=True, type=int)
    routing_set.add_argument("--reason", required=True)
    routing_set.add_argument("--json", action="store_true")
    routing_set.set_defaults(handler=_routing_state)

    gate_state = subparsers.add_parser(
        "gate-state", help="record a gate's PASS/RETRY/ESCALATE/... history"
    )
    gate_actions = gate_state.add_subparsers(dest="gate_action", required=True)
    gate_set = gate_actions.add_parser("set", help="set a gate's recorded state")
    gate_set.add_argument("--file")
    gate_set.add_argument("--gate", required=True)
    gate_set.add_argument("--state", required=True, choices=sorted(GATE_STATES))
    gate_set.add_argument("--reason", required=True)
    gate_set.add_argument("--count", required=True, type=int)
    gate_set.add_argument(
        "--kind", choices=sorted(FAILURE_KINDS), default="reasoning"
    )
    gate_set.add_argument("--json", action="store_true")
    gate_set.set_defaults(handler=_gate_state)

    evals_run = subparsers.add_parser(
        "evals-run", help="run one evals/ fixture family through its checker"
    )
    evals_run.add_argument("--family", required=True)
    evals_run.add_argument("--root", help="Toolkit repository root")
    evals_run.add_argument(
        "--live",
        action="store_true",
        help="model-in-the-loop mode using the routed Sonnet transport (structural mode is the CI default)",
    )
    evals_run.set_defaults(handler=_evals_run)

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
