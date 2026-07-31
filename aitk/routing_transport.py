"""Running a resolved route as a provider CLI worker.

Owns prompt assembly, argv construction, preflight capability checks, and result
parsing for each provider. It is the only layer that shells out, and it refuses to
soften anything the resolver pinned: no fallback model, no missing required flag, no
result that fails the worker schema.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable

from aitk.routing_policy import (
    BLOCKED_EXIT,
    DEFAULT_TIMEOUT,
    DOMAIN_FINDING_PATTERNS,
    DOMAIN_SEVERITIES,
    FAILED_EXIT,
    ModelRouteError,
    PLAN_SCORE_PATTERN,
    PREFLIGHT_TIMEOUT,
    PROMPT_LIMIT,
    ResolvedRoute,
    SUMMARY_FORMS,
    UNAVAILABLE_ERROR,
    VERSION_PATTERN,
    WORKER_SCHEMA,
)
from aitk.routing_closure import _contracts
from aitk.routing_resolver import resolve_route


def worker_prompt(
    route: ResolvedRoute,
    prompt: str,
    contracts: tuple[tuple[str, str, str], ...],
    workspace: Path | None = None,
) -> str:
    restrictions = json.dumps(route.restrictions, separators=(",", ":"))
    # The vocabulary the result is checked against, stated to the worker that has
    # to produce it. `_domain_problem` and `_summary_problem` reject a finding
    # that does not open with its domain's tag, a plan summary with no `Score:`
    # line, and a summary missing its declared form -- and a rule enforced
    # without being stated is a trap rather than a contract.
    grading = "-"
    if route.lens_domain is not None:
        tags = "|".join(DOMAIN_SEVERITIES[route.lens_domain])
        grading = f"every finding must begin with one of {tags}"
        if route.lens_domain == "plan":
            grading += "; summary must contain a `Score: X/10` line of its own"
    if route.summary_form is not None:
        lines = "; ".join(label for label, _ in SUMMARY_FORMS[route.summary_form])
        form = f"summary must contain these lines, one per line: {lines}"
        grading = form if grading == "-" else f"{grading}; {form}"
    prefix = (
        "AI_TOOLKIT_MODEL_ROUTE_V1\n"
        f"route={route.name}\nboundary={route.boundary}\n"
        f"provider={route.provider}\nfamily={route.family}\n"
        f"selector={route.selector}\neffort={route.effort}\n"
        f"responsibility={route.responsibility}\nrestrictions={restrictions}\n"
        # A dual-use lens reads these to choose its output vocabulary. They are
        # always emitted, including as `-`, so a worker never has to distinguish
        # "not a fan-out lane" from "header field the runner forgot".
        f"lens={route.lens or '-'}\nlens_domain={route.lens_domain or '-'}\n"
        f"grading={grading}\n"
        f"workspace={workspace if workspace is not None else '<caller-workspace>'}\n"
        "INLINE_CONTRACTS_BEGIN\n"
    )
    contract_text = ""
    for path, digest, content in contracts:
        contract_text += f"CONTRACT path={path} sha256={digest}\n{content}"
        if not contract_text.endswith("\n"):
            contract_text += "\n"
        contract_text += "CONTRACT_END\n"
    task = prompt + ("" if prompt.endswith("\n") else "\n")
    return (
        prefix
        + contract_text
        + "INLINE_CONTRACTS_END\nTASK_BEGIN\n"
        + task
        + "TASK_END\n"
    )


def _valid_worker(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"status", "summary", "findings", "verification"}
        and value.get("status") in {"completed", "blocked", "failed"}
        and isinstance(value.get("summary"), str)
        and bool(value.get("summary"))
        and all(
            isinstance(value.get(key), list)
            and all(isinstance(item, str) for item in value[key])
            for key in ("findings", "verification")
        )
    )


def _domain_problem(route: ResolvedRoute, result: dict[str, object]) -> str | None:
    """Check a graded lane's result against its lens domain's grading vocabulary.

    `_valid_worker` only proves the envelope is well-formed: every string passes.
    But the domain decides how the caller *consumes* the result -- code findings
    dedupe and escalate by `[major]`/`[minor]`/`[nitpick]`, plan findings iterate
    against a `X/10` score -- so an untagged or cross-tagged finding is silently
    dropped by the aggregator rather than rejected here. Enforcing the vocabulary
    at the boundary is what makes `lens_domain` more than prompt prose.

    The tag must open the finding and the score must own its line. Both were
    substring searches, which the aggregator's own parse is not: a plan finding
    that named `[major]` somewhere in its prose satisfied a code-domain check,
    and a summary that mentioned any `N/10` satisfied the plan score check.

    Only `completed` results are graded. A `blocked` or `failed` worker is
    reporting why it could not review, and demanding severity tags on that
    explanation would turn a legible failure into an unparseable one.
    """
    if route.lens_domain is None or result.get("status") != "completed":
        return None
    tags = DOMAIN_SEVERITIES[route.lens_domain]
    pattern = DOMAIN_FINDING_PATTERNS[route.lens_domain]
    untagged = [item for item in result["findings"] if not pattern.match(str(item))]
    if untagged:
        return (
            f"{route.lens_domain}-domain boundary {route.boundary} returned "
            f"{len(untagged)} finding(s) that do not open with a "
            f"{'/'.join(tags)} tag; the first is: {str(untagged[0])[:120]}"
        )
    if route.lens_domain == "plan" and not PLAN_SCORE_PATTERN.search(
        str(result["summary"])
    ):
        return (
            f"plan-domain boundary {route.boundary} returned no `Score: X/10` line "
            "in its summary; plan review iterates against that score"
        )
    return None


def _summary_problem(route: ResolvedRoute, result: dict[str, object]) -> str | None:
    """Check a lane's summary against the named grammar its boundary declares.

    Gated on `completed` for the same reason `_domain_problem` is: a worker
    saying why it could not review has no PR recommendation to give, and
    demanding the shape would replace a legible refusal with a schema error.
    """
    if route.summary_form is None or result.get("status") != "completed":
        return None
    summary = str(result["summary"])
    missing = [
        label
        for label, pattern in SUMMARY_FORMS[route.summary_form]
        if not pattern.search(summary)
    ]
    if not missing:
        return None
    return (
        f"boundary {route.boundary} returned a summary missing the "
        f"{route.summary_form} form's required line(s): {'; '.join(missing)}"
    )


def parse_codex_output(output: str, last_message: str) -> dict[str, object]:
    for line in output.splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ModelRouteError("invalid Codex event", UNAVAILABLE_ERROR)
        event_type = value.get("type")
        if event_type == "error" or (
            isinstance(event_type, str) and event_type.endswith(".failed")
        ):
            raise ModelRouteError("Codex returned an error event", UNAVAILABLE_ERROR)
    terminal = json.loads(last_message)
    if not _valid_worker(terminal):
        raise ModelRouteError(
            "Codex did not return one valid worker result", UNAVAILABLE_ERROR
        )
    return terminal


def parse_claude_output(output: str) -> dict[str, object]:
    value = json.loads(output)
    if (
        not isinstance(value, dict)
        or value.get("type") != "result"
        or value.get("subtype") != "success"
        or value.get("is_error") is not False
        or not _valid_worker(value.get("structured_output"))
    ):
        raise ModelRouteError(
            "Claude did not return one valid worker result", UNAVAILABLE_ERROR
        )
    return value["structured_output"]


def _version_tuple(value: str) -> tuple[int, int, int, int]:
    match = VERSION_PATTERN.search(value)
    if match is None:
        raise ModelRouteError(
            "provider CLI version could not be parsed", UNAVAILABLE_ERROR
        )
    token = match.group(0)
    core = token.split("-", 1)[0].split("+", 1)[0]
    major, minor, patch = (int(item) for item in core.split("."))
    stable = 0 if "-" in token else 1
    return major, minor, patch, stable


def _required_flags(route: ResolvedRoute) -> tuple[str, ...]:
    if route.provider == "codex":
        return (
            "--ephemeral",
            "--strict-config",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable",
            "--model",
            "--config",
            "--sandbox",
            "--cd",
            "--add-dir",
            "--output-schema",
            "--output-last-message",
            "--json",
        )
    flags = [
        "--print",
        "--no-session-persistence",
        "--safe-mode",
        "--strict-mcp-config",
        "--mcp-config",
        "--model",
        "--effort",
        "--permission-mode",
        "--json-schema",
        "--output-format",
        "--tools",
    ]
    if route.controls.get("disallowed_tools"):
        flags.append("--disallowedTools")
    return tuple(flags)


def _has_flag(help_text: str, flag: str) -> bool:
    return (
        re.search(rf"(?:^|\s){re.escape(flag)}(?=\s|[=,\[]|$)", help_text) is not None
    )


def _preflight(
    route: ResolvedRoute,
    executable: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    version = run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        timeout=PREFLIGHT_TIMEOUT,
        check=False,
    )
    version_text = version.stdout + version.stderr
    if version.returncode or _version_tuple(version_text) < _version_tuple(
        route.minimum_cli
    ):
        raise ModelRouteError(
            f"{route.provider} CLI does not meet minimum {route.minimum_cli}",
            UNAVAILABLE_ERROR,
        )
    help_argv = (
        [executable, "exec", "--help"]
        if route.provider == "codex"
        else [executable, "--help"]
    )
    help_result = run(
        help_argv,
        text=True,
        capture_output=True,
        timeout=PREFLIGHT_TIMEOUT,
        check=False,
    )
    help_text = help_result.stdout + help_result.stderr
    if help_result.returncode or any(
        not _has_flag(help_text, flag) for flag in _required_flags(route)
    ):
        raise ModelRouteError(
            f"{route.provider} CLI lacks required routing flags", UNAVAILABLE_ERROR
        )


def _argv(
    route: ResolvedRoute,
    executable: str,
    workspace: Path,
    schema: str,
    output_path: str | None = None,
    isolated_project_root: Path | str | None = None,
) -> list[str]:
    if route.provider == "codex":
        project_root = isolated_project_root or "<isolated-project-root>"
        return [
            executable,
            "exec",
            "--ephemeral",
            "--strict-config",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable",
            "hooks",
            "--model",
            route.selector,
            "--config",
            f'model_reasoning_effort="{route.effort}"',
            "--config",
            "mcp_servers={}",
            "--config",
            "project_doc_max_bytes=0",
            "--sandbox",
            str(route.controls["sandbox"]),
            "--cd",
            str(project_root),
            "--add-dir",
            str(workspace),
            "--output-schema",
            schema,
            "--output-last-message",
            output_path or "<last-message-path>",
            "--json",
            "-",
        ]
    result = [
        executable,
        "--print",
        "--no-session-persistence",
        "--safe-mode",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers": {}}',
        "--model",
        route.selector,
        "--effort",
        route.effort,
        "--permission-mode",
        str(route.controls["permission_mode"]),
    ]
    tools = route.controls.get("disallowed_tools", [])
    if tools:
        result.extend(["--disallowedTools", *tools])
    available_tools = (
        ["Read", "Grep", "Glob", "Edit", "Write"]
        if route.responsibility == "implementation"
        else ["Read", "Grep", "Glob"]
    )
    result.extend(["--tools", *available_tools])
    result.extend(["--json-schema", schema, "--output-format", "json"])
    return result


def _outer(
    route: ResolvedRoute,
    *,
    dry_run: bool,
    started: bool,
    exit_code: int | None,
    argv: list[str] | None,
    result: dict[str, object] | None,
    error: str | None,
) -> dict[str, object]:
    return {
        "command": "model-run",
        "dry_run": dry_run,
        "route": route.name,
        "boundary": route.boundary,
        "provider": route.provider,
        "request": {
            "family": route.family,
            "selector": route.selector,
            "effort": route.effort,
        },
        "transport": {"started": started, "exit_code": exit_code},
        "argv": argv,
        "result": result,
        "error": None
        if error is None
        else {"code": UNAVAILABLE_ERROR, "message": error},
    }


def run_model(
    root: Path,
    route_name: str,
    provider: str,
    boundary: str,
    prompt_path: Path,
    cwd: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    lens: str | None = None,
) -> tuple[int, dict[str, object]]:
    if not boundary:
        raise ModelRouteError("model-run requires a dispatch boundary")
    route = resolve_route(root, route_name, provider, boundary, lens)
    if not route.required_contracts:
        raise ModelRouteError("dispatch boundary has no required contracts")
    contracts = _contracts(root, route.required_contracts)
    if timeout_seconds <= 0:
        raise ModelRouteError("timeout must be positive")
    try:
        invalid_prompt = (
            prompt_path.is_symlink()
            or not prompt_path.is_file()
            or prompt_path.stat().st_size > PROMPT_LIMIT
        )
    except OSError as error:
        raise ModelRouteError("prompt file could not be inspected") from error
    if invalid_prompt:
        raise ModelRouteError("prompt file must be a regular file no larger than 1 MiB")
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ModelRouteError("prompt file must be UTF-8") from error
    except OSError as error:
        raise ModelRouteError("prompt file could not be read") from error
    try:
        selected_cwd = (cwd or Path.cwd()).resolve()
    except OSError as error:
        raise ModelRouteError("cwd could not be resolved") from error
    if not selected_cwd.is_dir():
        raise ModelRouteError("cwd must be an existing directory")
    executable = shutil.which(provider)
    if executable is None:
        return 3, _outer(
            route,
            dry_run=dry_run,
            started=False,
            exit_code=None,
            argv=None,
            result=None,
            error=f"{provider} executable not found",
        )
    try:
        _preflight(route, executable, runner)
    except (ModelRouteError, OSError, subprocess.TimeoutExpired) as error:
        return 3, _outer(
            route,
            dry_run=dry_run,
            started=False,
            exit_code=None,
            argv=None,
            result=None,
            error=str(error),
        )
    schema_json = json.dumps(WORKER_SCHEMA, separators=(",", ":"), sort_keys=True)
    if dry_run:
        schema_value = "<schema-path>" if provider == "codex" else schema_json
        argv = _argv(
            route,
            "<provider-executable>",
            selected_cwd,
            schema_value,
            "<last-message-path>" if provider == "codex" else None,
        )
        return 0, _outer(
            route,
            dry_run=True,
            started=False,
            exit_code=None,
            argv=argv,
            result=None,
            error=None,
        )
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        try:
            if provider == "codex":
                temporary = tempfile.TemporaryDirectory(prefix="aitk-model-route-")
                schema_path = Path(temporary.name) / "worker-schema.json"
                schema_path.write_text(schema_json)
                os.chmod(schema_path, 0o600)
                schema_value = str(schema_path)
                last_message_path = Path(temporary.name) / "last-message.json"
            else:
                schema_value = schema_json
                last_message_path = None
        except OSError:
            return 3, _outer(
                route,
                dry_run=False,
                started=False,
                exit_code=None,
                argv=None,
                result=None,
                error="worker schema could not be prepared",
            )
        argv = _argv(
            route,
            executable,
            selected_cwd,
            schema_value,
            str(last_message_path) if last_message_path is not None else None,
            Path(temporary.name) if provider == "codex" and temporary else None,
        )
        process_cwd = (
            Path(temporary.name) if provider == "codex" and temporary else selected_cwd
        )
        try:
            process = runner(
                argv,
                input=worker_prompt(route, prompt, contracts, selected_cwd),
                cwd=process_cwd,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except OSError as error:
            return 3, _outer(
                route,
                dry_run=False,
                started=False,
                exit_code=None,
                argv=None,
                result=None,
                error=str(error),
            )
        except subprocess.TimeoutExpired as error:
            return 3, _outer(
                route,
                dry_run=False,
                started=True,
                exit_code=None,
                argv=None,
                result=None,
                error=str(error),
            )
        if process.returncode:
            return 3, _outer(
                route,
                dry_run=False,
                started=True,
                exit_code=process.returncode,
                argv=None,
                result=None,
                error="provider process failed",
            )
        try:
            if provider == "codex":
                if last_message_path is None or not last_message_path.is_file():
                    raise ModelRouteError(
                        "Codex did not write its final response", UNAVAILABLE_ERROR
                    )
                try:
                    last_message = last_message_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as error:
                    raise ModelRouteError(
                        "Codex final result could not be read", UNAVAILABLE_ERROR
                    ) from error
                result = parse_codex_output(process.stdout, last_message)
            else:
                result = parse_claude_output(process.stdout)
            # An unscored lane emits proposals, not severity-graded findings.
            # Anything it puts in `findings` is treated as a scored finding by
            # every downstream consumer, so a non-empty array is a contract
            # violation rather than a formatting slip -- fail the run instead of
            # letting it enter the fix queue.
            if route.unscored and result["findings"]:
                raise ModelRouteError(
                    f"unscored boundary {route.boundary} returned "
                    f"{len(result['findings'])} findings; this lane must return "
                    "an empty findings array"
                )
            grading_problem = _domain_problem(route, result) or _summary_problem(
                route, result
            )
            if grading_problem is not None:
                raise ModelRouteError(grading_problem)
        except (ModelRouteError, json.JSONDecodeError) as error:
            return 3, _outer(
                route,
                dry_run=False,
                started=True,
                exit_code=0,
                argv=None,
                result=None,
                error=str(error),
            )
        result_exit = {
            "completed": 0,
            "blocked": BLOCKED_EXIT,
            "failed": FAILED_EXIT,
        }[result["status"]]
        return result_exit, _outer(
            route,
            dry_run=False,
            started=True,
            exit_code=0,
            argv=None,
            result=result,
            error=None,
        )
    finally:
        if temporary is not None:
            temporary.cleanup()
