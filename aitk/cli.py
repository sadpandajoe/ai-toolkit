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
from .deliver import DeliverOptions, deliver as run_delivery, render as render_delivery
from .doctor import run_doctor
from .installer import resolve_paths, run_lifecycle
from .model_routing import (
    ModelRouteError,
    resolve_route,
    run_model,
)
from .pgm import preflight as pgm_preflight
from .review_plan import (
    PROVIDERS,
    PlanInputs,
    ReviewPlanError,
    default_metrics_file,
    evaluate as evaluate_lane_yield,
    excluded_reason,
    families as routing_families,
    is_toolkit_repository,
    load_events,
    local_changes,
    merge as merge_review,
    parent_from_environment,
    phase_base,
    plan as plan_review,
    pr_changes,
    provider_reachable,
    read_envelopes,
    record_demotions,
    render_merge,
    render_plan,
    branch_base as review_branch_base,
)
from .project_state import (
    OBSERVATION_KINDS,
    REVIEW_EXCEPTIONS,
    STRENGTHS,
    ProjectStateError,
    advance_phase,
    append_observation,
    complexity_block,
    ensure_excluded,
    gate_block,
    git_toplevel,
    initialize as initialize_project_state,
    operation_recorded,
    parse_project_state,
    record_gate,
    record_operation,
    review_exception,
    review_from_envelopes,
    set_fields,
    set_phases,
    show as show_project_state,
    state_file,
    update_phase,
    verify_run,
    working_tree_sha,
)
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
    worker_cwd = Path(arguments.cwd) if arguments.cwd else None
    # The tree the worker is handed, taken before it runs; `gate --gate review
    # --result` records it, and `deliver` compares it with what it pushes.
    reviewed_tree = (
        None
        if arguments.dry_run
        else working_tree_sha(worker_cwd if worker_cwd is not None else Path.cwd())
    )
    try:
        exit_code, payload = run_model(
            root,
            arguments.model_route,
            arguments.provider,
            arguments.boundary,
            Path(arguments.prompt_file),
            worker_cwd,
            arguments.timeout_seconds,
            arguments.dry_run,
            lens=arguments.lens,
            reviewed_tree=reviewed_tree,
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
    result = run_lifecycle(
        paths,
        arguments.command,
        with_pgm=arguments.with_pgm,
        hooks=not arguments.no_hooks,
    )
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


def _read_envelopes(paths: list[str]) -> list[object]:
    envelopes: list[object] = []
    for value in paths:
        try:
            envelopes.append(json.loads(Path(value).read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProjectStateError(f"--result {value} is not a readable JSON envelope: {error}") from error
    return envelopes


def _snapshot_or_none(path: Path) -> dict[str, object] | None:
    try:
        return show_project_state(path).snapshot
    except (ProjectStateError, OSError):
        return None


def _project_state(arguments: argparse.Namespace) -> int:
    path = state_file(arguments.file)
    try:
        action = arguments.state_action
        if action == "op" and arguments.check:
            when = operation_recorded(path, arguments.check)
            payload = {"operation": arguments.check, "ran": when is not None, "recorded": when}
            if arguments.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            elif when is None:
                print(f"not run: {arguments.check}")
            else:
                print(f"ran: {arguments.check} (recorded {when}); skip it")
            # 0 = already ran (skip it), 3 = not yet (run it, then `op --id`).
            return 0 if when is not None else 3
        if action != "show":
            # Every write into the target repo keeps the state out of commits.
            ensure_excluded(path.parent)
        before = _snapshot_or_none(path) if action == "gate" else None
        if action == "init":
            result = initialize_project_state(
                path,
                arguments.workflow,
                arguments.complexity,
                arguments.size,
                arguments.phaseability,
                confidence=arguments.confidence,
                modifiers=arguments.modifier or [],
                phaseability_reason=arguments.reason or "",
                phase=arguments.phase,
                replace=arguments.replace,
            )
        elif action == "show":
            result = show_project_state(path)
        elif action == "set":
            result = set_fields(
                path,
                complexity=arguments.complexity,
                size=arguments.size,
                phaseability=arguments.phaseability,
                phaseability_reason=arguments.reason,
                classification_confidence=arguments.confidence,
                modifiers=arguments.modifier if arguments.modifier else None,
            )
        elif action == "gate":
            review = None
            if arguments.result or arguments.exception:
                if arguments.gate != "review":
                    raise ProjectStateError("--result and --exception record review evidence; use --gate review")
                if arguments.result and arguments.exception:
                    raise ProjectStateError("pass --result or --exception, not both")
                if arguments.exception:
                    if arguments.status != "PASS":
                        raise ProjectStateError("a review exception is a PASS")
                    review = review_exception(path, arguments.exception, Path.cwd())
                else:
                    review = review_from_envelopes(_read_envelopes(arguments.result))
            result = record_gate(
                path,
                arguments.gate,
                arguments.status,
                arguments.unit,
                same_failure=arguments.same_failure,
                editorial=arguments.editorial,
                review=review,
                reason=arguments.reason,
            )
        elif action == "advance":
            result = advance_phase(path, arguments.to)
        elif action == "phases":
            result = set_phases(path, json.loads(arguments.phases_json))
        elif action == "op":
            result = record_operation(path, arguments.id)
        else:
            result = update_phase(path, arguments.name, arguments.status, arguments.sha)
    except (ProjectStateError, OSError, json.JSONDecodeError) as error:
        print(f"aitk project-state: {error}", file=sys.stderr)
        return 1
    block_format = getattr(arguments, "format", "line") == "block"
    if arguments.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    elif block_format and action in {"init", "set"}:
        print(complexity_block(result.snapshot, arguments.evidence))
    elif block_format and action == "gate":
        print(
            gate_block(
                before,
                result.snapshot,
                arguments.gate,
                arguments.unit,
                strength=arguments.strength,
                evidence=arguments.evidence,
                next_step=arguments.next,
                reason=arguments.reason,
                editorial=arguments.editorial,
            )
        )
    elif action == "op":
        disposition = "recorded" if result.changed else "already recorded"
        print(f"{arguments.id}: {disposition}")
    else:
        snapshot = result.snapshot
        print(
            f"{snapshot['workflow']}: complexity={snapshot['complexity']} "
            f"size={snapshot['size']} shape={snapshot['execution_shape']} "
            f"phase={snapshot['current_phase']} gate={snapshot['current_gate']}="
            f"{snapshot['gate_status']} attempts={json.dumps(snapshot['attempts'], sort_keys=True)} "
            f"escalations={json.dumps(snapshot['escalations'], sort_keys=True)}"
        )
        print(f"  state: {result.file}")
    return 0


def _deliver(arguments: argparse.Namespace) -> int:
    cwd = Path.cwd()
    result = run_delivery(
        DeliverOptions(
            cwd=cwd,
            project_file=state_file(arguments.file, cwd),
            workflow=arguments.workflow,
            phase=arguments.phase,
            title=arguments.title,
            body_file=Path(arguments.body_file).resolve() if arguments.body_file else None,
            message=arguments.message,
            base=arguments.base,
            no_pr=arguments.no_pr,
            ready=arguments.ready,
        )
    )
    if arguments.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(render_delivery(result))
    return result.exit_code


def _verify(arguments: argparse.Namespace) -> int:
    path = state_file(arguments.file)
    try:
        ensure_excluded(path.parent)
        before = _snapshot_or_none(path)
        outcome = verify_run(
            path,
            arguments.run,
            cwd=Path.cwd(),
            strength=arguments.strength,
            unit=arguments.unit,
            same_failure=arguments.same_failure,
            timeout_seconds=arguments.timeout_seconds,
            reason=arguments.reason,
        )
    except (ProjectStateError, OSError) as error:
        print(f"aitk verify: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(
            json.dumps(
                {
                    "command": "verify",
                    "status": outcome.status,
                    "run": outcome.run,
                    "tree_changed": outcome.tree_changed,
                    "file": outcome.result.file,
                    "snapshot": outcome.result.snapshot,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            gate_block(
                before,
                outcome.result.snapshot,
                "verification",
                arguments.unit,
                strength=str(outcome.run["strength"]),
                evidence=arguments.evidence,
                next_step=arguments.next,
                reason=arguments.reason,
            )
        )
        if outcome.run["output_tail"]:
            print("\nOutput (tail):\n" + str(outcome.run["output_tail"]))
    if outcome.tree_changed:
        print(
            "aitk verify: the command changed the working tree; the run covers the tree "
            "before it, so deliver will refuse until the check runs again on the new tree",
            file=sys.stderr,
        )
    return 0 if outcome.status == "PASS" else 1


def _observe(arguments: argparse.Namespace) -> int:
    path = state_file(arguments.file)
    snapshot = None
    if path.is_file():
        try:
            snapshot = parse_project_state(path.read_text(encoding="utf-8"))
        except (ProjectStateError, OSError):
            snapshot = None
    entry: dict[str, object] = {
        "kind": arguments.kind,
        "workflow": arguments.workflow or (snapshot or {}).get("workflow"),
        "phase": arguments.phase or (snapshot or {}).get("current_phase"),
        "complexity": (snapshot or {}).get("complexity"),
        "size": (snapshot or {}).get("size"),
        "shape": (snapshot or {}).get("execution_shape"),
        "detail": arguments.detail,
        "evidence": arguments.evidence,
        "eval_candidate": True if arguments.eval_candidate else None,
    }
    try:
        written = append_observation(path.parent, entry)
    except (ProjectStateError, OSError) as error:
        print(f"aitk observe: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps({"command": "observe", "file": str(written), "kind": arguments.kind}, sort_keys=True))
    else:
        print(f"observation recorded: {arguments.kind} -> {written}")
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


def _lane_yield(arguments: argparse.Namespace) -> int:
    metrics = Path(arguments.metrics).resolve() if arguments.metrics else default_metrics_file()
    events = load_events(metrics)
    demotions = evaluate_lane_yield(events)
    try:
        queued = record_demotions(Path.cwd(), demotions)
    except (ProjectStateError, OSError) as error:
        print(f"lane-yield: could not append observations: {error}", file=sys.stderr)
        queued = []
    if arguments.json:
        print(
            json.dumps(
                {
                    "metrics": str(metrics),
                    "events": len(events),
                    "demotions": [item.as_dict() for item in demotions],
                    "observations": queued,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"metrics: {metrics} ({len(events)} events)")
    if not demotions:
        print("no lane below its yield threshold")
        return 0
    for item in demotions:
        observed = ", ".join(f"{key}={value}" for key, value in item.observed.items())
        print(f"{item.lane}: demoted over last {item.runs} runs ({observed})")
        print(f"  -> {item.consequence}")
    if queued:
        print(f"low-yield-lane observation queued for: {', '.join(queued)}")
    return 0


def _reachable(root: Path, arguments: argparse.Namespace) -> frozenset[str]:
    unreachable = set(arguments.unreachable or ())
    return frozenset(
        provider for provider in PROVIDERS if provider not in unreachable and provider_reachable(root, provider)
    )


def _demoted(arguments: argparse.Namespace) -> frozenset[str]:
    metrics = Path(arguments.metrics).resolve() if arguments.metrics else default_metrics_file()
    return frozenset(item.lane for item in evaluate_lane_yield(load_events(metrics)))


def _review_plan(arguments: argparse.Namespace, root: Path) -> int:
    cwd = Path.cwd()
    parent = arguments.parent or parent_from_environment()
    if parent is None:
        raise ReviewPlanError("pass --parent claude|codex (the provider running this session)")
    repo = git_toplevel(cwd)
    extra: dict[str, object] = {}
    if arguments.kind == "pr":
        if not arguments.pr:
            raise ReviewPlanError("--kind pr needs --pr <number|url|branch>")
        files, title, base_branch = pr_changes(cwd, arguments.pr)
        titles = (arguments.title or title,)
        base = branch = base_branch
        extra["pr"] = arguments.pr
        complexity = arguments.complexity
        if complexity is None:
            raise ReviewPlanError("--kind pr needs --complexity (from the PR signals table)")
    else:
        if repo is None:
            raise ReviewPlanError("review plan runs inside a git repository")
        snapshot = _snapshot_or_none(state_file(arguments.file, cwd))
        branch = review_branch_base(repo)
        base = arguments.base or phase_base(snapshot) or branch
        if base is None:
            raise ReviewPlanError("no base: pass --base <rev> (no remote default branch or main/master found)")
        files = local_changes(repo, base)
        complexity = arguments.complexity or (snapshot or {}).get("complexity")
        if complexity is None:
            raise ReviewPlanError("no complexity: pass --complexity or record the Complexity Gate first")
        subjects = []
        if arguments.title is None:
            log = subprocess.run(
                ["git", "-C", str(repo), "log", "--format=%s", f"{base}..HEAD"],
                text=True, capture_output=True, check=False,
            )
            subjects = log.stdout.splitlines() if log.returncode == 0 else []
        titles = (arguments.title,) if arguments.title else tuple(subjects)
    inputs = PlanInputs(
        parent=parent,
        complexity=str(complexity),
        impact=arguments.impact,
        kind=arguments.kind,
        files=tuple(files),
        titles=titles,
        ask=arguments.ask or "",
        effort=arguments.effort,
        security_sensitive=arguments.security_sensitive,
        architecture=arguments.architecture,
        refactor=arguments.refactor,
        toolkit=is_toolkit_repository(repo),
        deep=arguments.deep,
        adversarial=arguments.adversarial,
        reachable=_reachable(root, arguments),
        demoted=_demoted(arguments),
        allow_degraded=arguments.allow_degraded,
        base=base,
        branch_base=branch,
        extra=extra,
    )
    payload = plan_review(inputs, routing_families(root))
    print(json.dumps(payload, indent=2, sort_keys=True) if arguments.json else render_plan(payload))
    return 0 if payload["status"] == "ready" else 3


def _review_merge(arguments: argparse.Namespace, root: Path) -> int:
    lanes = read_envelopes(arguments.result)
    if arguments.plan:
        try:
            planned = json.loads(Path(arguments.plan).read_text(encoding="utf-8"))
            coverage = list(planned["coverage"]["required"])
            reachable = frozenset(planned["reachable"])
            demoted = frozenset(planned["demoted"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ReviewPlanError(f"cannot read the plan {arguments.plan}: {error}") from error
    else:
        repo = git_toplevel(Path.cwd())
        base = arguments.base or (review_branch_base(repo) if repo else None)
        coverage = (
            [
                item.path
                for item in local_changes(repo, base)
                if item.status != "deleted" and excluded_reason(item) is None
            ]
            if repo and base
            else None
        )
        reachable = _reachable(root, arguments)
        demoted = _demoted(arguments)
    payload = merge_review(
        lanes,
        routing_families(root),
        coverage_required=coverage,
        reproduced=arguments.reproduced or (),
        demoted=demoted,
        reachable=reachable,
    )
    print(json.dumps(payload, indent=2, sort_keys=True) if arguments.json else render_merge(payload))
    return 0


def _review(arguments: argparse.Namespace) -> int:
    root = _root(arguments.root)
    try:
        if arguments.review_action == "plan":
            return _review_plan(arguments, root)
        return _review_merge(arguments, root)
    except (ReviewPlanError, ModelRouteError, ProjectStateError) as error:
        print(f"review {arguments.review_action}: {error}", file=sys.stderr)
        return 1


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

    project_state = subparsers.add_parser(
        "project-state", help="read or update the PROJECT.md v2 routing snapshot"
    )
    state_actions = project_state.add_subparsers(dest="state_action", required=True)
    for action in ("init", "show", "set", "gate", "advance", "phases", "phase", "op"):
        state_action = state_actions.add_parser(
            action,
            help=(
                "record a provider operation (--id) or check whether it ran (--check; exit 0 ran, 3 not yet)"
                if action == "op"
                else f"{action} the routing snapshot"
            ),
        )
        state_action.add_argument(
            "--file",
            help="PROJECT.md path (default: ./PROJECT.md, else the one at the git root)",
        )
        state_action.add_argument("--json", action="store_true")
        if action in {"init", "set", "gate"}:
            state_action.add_argument(
                "--format",
                choices=("line", "block"),
                default="line",
                help="block prints the Complexity Gate (init, set) or Gate (gate) block to paste",
            )
            state_action.add_argument("--evidence", help="one line for the block's Evidence (gate) or Reason (init, set)")
        if action == "gate":
            state_action.add_argument("--next", help="the block's Next line (default: what the outcome calls for)")
            state_action.add_argument("--strength", choices=STRENGTHS, help="the block's Strength line")
            state_action.add_argument(
                "--reason",
                help="why: printed in the block and used as the observation detail for RECLASSIFY or a repeated failure",
            )
            state_action.add_argument(
                "--result",
                action="append",
                help="review gate: a `bin/aitk model-run` JSON envelope file to record (repeatable)",
            )
            state_action.add_argument(
                "--exception",
                choices=REVIEW_EXCEPTIONS,
                help="review gate: a review exception backed by this phase's passing verification run",
            )
        if action == "op":
            which = state_action.add_mutually_exclusive_group(required=True)
            which.add_argument("--id", help="record that this operation ran (push:<sha>, reply:<thread-id>, ...)")
            which.add_argument("--check", help="report whether this operation already ran")
        if action == "init":
            state_action.add_argument("--workflow", required=True)
            state_action.add_argument("--complexity", required=True)
            state_action.add_argument("--size", required=True, choices=("S", "M", "L", "XL"))
            state_action.add_argument(
                "--phaseability",
                default="unassessed",
                choices=("none", "repetitive", "phased", "unassessed"),
            )
            state_action.add_argument("--confidence", default="HIGH", choices=("HIGH", "MEDIUM", "LOW"))
            state_action.add_argument("--modifier", action="append")
            state_action.add_argument("--reason", help="phaseability reason")
            state_action.add_argument("--phase", default="intake")
            state_action.add_argument("--replace", action="store_true")
        if action == "set":
            state_action.add_argument("--complexity")
            state_action.add_argument("--size", choices=("S", "M", "L", "XL"))
            state_action.add_argument(
                "--phaseability", choices=("none", "repetitive", "phased", "unassessed")
            )
            state_action.add_argument("--confidence", choices=("HIGH", "MEDIUM", "LOW"))
            state_action.add_argument("--modifier", action="append")
            state_action.add_argument("--reason")
        if action == "gate":
            state_action.add_argument("--gate", required=True)
            state_action.add_argument(
                "--status",
                required=True,
                choices=("PASS", "RETRY", "ESCALATE", "RECLASSIFY", "USER_DECISION", "BLOCKED"),
            )
            state_action.add_argument("--unit", help="reasoning unit charged for a failure")
            state_action.add_argument("--same-failure", action="store_true")
            state_action.add_argument(
                "--editorial",
                action="store_true",
                help="a wording, path, or rollback-note fix; recorded but never charged to the budget",
            )
        if action == "advance":
            state_action.add_argument("--to", required=True)
        if action == "phases":
            state_action.add_argument("--phases-json", required=True)
        if action == "phase":
            state_action.add_argument("--name", required=True)
            state_action.add_argument(
                "--status", required=True, choices=("pending", "active", "done", "blocked")
            )
            state_action.add_argument(
                "--sha",
                help="commit or tree SHA the phase ended on; required with --status done, it is the next phase's review base",
            )
        state_action.set_defaults(handler=_project_state)

    delivery = subparsers.add_parser(
        "deliver",
        help=(
            "commit, push and open (or reuse) a draft PR once review PASS and a STRONG "
            "verification run hold on the current tree"
        ),
        description=(
            "Refuses (exit 1, nothing changed) without a review record, without a passing "
            "STRONG `verify --run` record, or when the tree changed after them; holds "
            "(exit 3, `## PR Not Opened`) on an ambiguous push target or a PR conflict."
        ),
    )
    delivery.add_argument("--workflow", help="the owning workflow (chained); omit for a standalone create-pr")
    delivery.add_argument("--phase", help="the phase being delivered (recorded)")
    delivery.add_argument("--title", help="PR title (also the commit message when --message is absent)")
    delivery.add_argument("--body-file", help="file holding the PR body (after the PII scrub)")
    delivery.add_argument("--message", help="commit message for uncommitted changes")
    delivery.add_argument("--base", help="base branch (default: the repository's default branch)")
    delivery.add_argument("--no-pr", action="store_true", help="stop after the push")
    delivery.add_argument(
        "--ready",
        action="store_true",
        help="open a non-draft PR; only when the user asked for one in words (needs AITK_PR_READY=1)",
    )
    delivery.add_argument("--file", help="PROJECT.md path (default: ./PROJECT.md, else the one at the git root)")
    delivery.add_argument("--json", action="store_true")
    delivery.set_defaults(handler=_deliver)

    verify = subparsers.add_parser(
        "verify",
        help="run a check and record it on the verification gate (PASS only on exit 0)",
    )
    verify.add_argument("--run", required=True, metavar="CMD", help="the command to run (through bash)")
    verify.add_argument(
        "--strength",
        choices=STRENGTHS,
        help="default: STRONG when CMD is the acceptance command in PLAN.md or the RCA record, else PARTIAL",
    )
    verify.add_argument("--unit", help="reasoning unit charged when the run fails")
    verify.add_argument("--same-failure", action="store_true")
    verify.add_argument("--timeout-seconds", type=int, default=1800)
    verify.add_argument("--evidence", help="override the block's Evidence line")
    verify.add_argument("--next", help="the block's Next line")
    verify.add_argument("--reason", help="why the run failed, for the block and the observation queue")
    verify.add_argument("--file", help="PROJECT.md path (default: ./PROJECT.md, else the one at the git root)")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(handler=_verify)

    observe = subparsers.add_parser(
        "observe",
        help="append one line to .ai-toolkit/observations.jsonl (the reflection queue)",
    )
    observe.add_argument("--kind", required=True, choices=OBSERVATION_KINDS)
    observe.add_argument("--detail", required=True, help="one sentence, free of PII")
    observe.add_argument("--workflow", help="default: the routing snapshot's workflow")
    observe.add_argument("--phase", help="default: the routing snapshot's phase")
    observe.add_argument("--evidence", help="where the evidence is, e.g. PROJECT.md#gate-review")
    observe.add_argument("--eval-candidate", action="store_true")
    observe.add_argument("--file", help="PROJECT.md path (default: ./PROJECT.md, else the one at the git root)")
    observe.add_argument("--json", action="store_true")
    observe.set_defaults(handler=_observe)

    review = subparsers.add_parser(
        "review", help="plan a review's lanes, or merge their findings (local-review.md)"
    )
    review_actions = review.add_subparsers(dest="review_action", required=True)
    review_plan = review_actions.add_parser(
        "plan",
        help="classify the diff and list the lanes to launch (exit 3 when BLOCKED)",
    )
    review_plan.add_argument("--parent", choices=PROVIDERS, help="the provider running this session (default: claude under Claude Code)")
    review_plan.add_argument("--kind", choices=("local", "pr"), default="local")
    review_plan.add_argument("--pr", help="with --kind pr: the PR number, URL or branch")
    review_plan.add_argument("--base", help="review base (default: the last finished phase's tree, else the branch base)")
    review_plan.add_argument("--complexity", choices=("TRIVIAL", "STANDARD", "COMPLEX"), help="default: the snapshot's")
    review_plan.add_argument("--impact", choices=("CORE", "STANDARD", "PERIPHERAL"), default="STANDARD", help="from assess-impact.md")
    review_plan.add_argument("--security-sensitive", action="store_true", help="classifier flag the paths alone do not show")
    review_plan.add_argument("--architecture", action="store_true", help="classifier flag: architecture change")
    review_plan.add_argument("--refactor", action="store_true", help="classifier flag: refactor-shaped")
    review_plan.add_argument("--title", help="change title (default: the commit subjects since the base)")
    review_plan.add_argument("--ask", help="the user's words, for escalation phrases and lens asks")
    review_plan.add_argument("--effort", choices=("max", "ultra"), help="an explicit max or ultra effort ask")
    review_plan.add_argument("--deep", action="store_true", help="deep-tier escalation (review-pr --deep)")
    review_plan.add_argument("--adversarial", action="store_true", help="an explicit adversarial ask")
    review_plan.add_argument("--allow-degraded", action="store_true", help="the user's USER_DECISION to run without the other provider")
    review_plan.add_argument("--unreachable", action="append", choices=PROVIDERS, help="treat a provider as unreachable")
    review_plan.add_argument("--metrics", help="metrics file for yield demotions (default: ./.ai-toolkit/metrics.jsonl)")
    review_plan.add_argument("--file", help="PROJECT.md path (default: ./PROJECT.md, else the one at the git root)")
    review_plan.add_argument("--json", action="store_true")
    review_merge = review_actions.add_parser(
        "merge", help="dedupe lane findings, compute convergence, and list majors to verify"
    )
    review_merge.add_argument(
        "--result", action="append", required=True, metavar="[LANE=]PATH",
        help="a reviewer lane's saved model-run envelope; label deep lenses, e.g. adversarial=adv.json",
    )
    review_merge.add_argument("--plan", help="saved `review plan --json` output (coverage, reachability, demotions)")
    review_merge.add_argument("--reproduced", action="append", metavar="FILE:LINE", help="a major the parent reproduced, or whose locking assertion failed")
    review_merge.add_argument("--base", help="without --plan: the base for the coverage check")
    review_merge.add_argument("--unreachable", action="append", choices=PROVIDERS, help="without --plan: treat a provider as unreachable")
    review_merge.add_argument("--metrics", help="without --plan: metrics file for yield demotions")
    review_merge.add_argument("--json", action="store_true")
    review.set_defaults(handler=_review)

    lane_yield = subparsers.add_parser(
        "lane-yield",
        help="apply the review-lane yield thresholds to .ai-toolkit/metrics.jsonl",
    )
    lane_yield.add_argument("--metrics", help="metrics file (default: ./.ai-toolkit/metrics.jsonl)")
    lane_yield.add_argument("--json", action="store_true")
    lane_yield.set_defaults(handler=_lane_yield)

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
            lifecycle.add_argument(
                "--no-hooks",
                action="store_true",
                help="do not register the toolkit hooks in Claude Code settings",
            )
        else:
            lifecycle.set_defaults(with_pgm=False, no_hooks=False)
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
