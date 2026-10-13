"""`bin/aitk eval`: the judgment cases, run on one provider and graded.

Each ``mode: judgment`` case in ``evals/<family>/cases.jsonl`` goes to a model
through the ``model-run`` transport (``aitk.routing_transport.run_resolved``):
the worker plays the parent session, with its family's contracts
(``FAMILY_CONTRACTS``) in the instruction channel and the case's situation as
the task, and answers one JSON object with the case's ``expected`` keys. A
second dispatch grades that answer against ``expected`` under
``evals/grader.md``; its summary opens with ``Verdict: PASS`` or
``Verdict: FAIL``. The run appends a section to
``evals/results/<date>-<provider>.md``: passes and API-equivalent cost per
model and effort, per family and per case, and the misses.

Nothing here decides a route. ``--model`` and ``--effort`` change what one run
measures (the planning route, the orchestrator, the effort sweep), never what
``model-run`` dispatches for a workflow, and the results file records both. Cases a test already covers
(``expected.covered_by``) are skipped.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable, Iterable, Sequence

from .pricing import compute_cost
from .routing_manifest import ROUTE_EFFORTS, load_model_routing
from .routing_policy import DEFAULT_TIMEOUT, PROVIDERS, ModelRouteError, ResolvedRoute
from .routing_transport import run_resolved


# What the parent reads for each family's decisions: the always-on rule, then
# the files that own those decisions.
ALWAYS_ON = ("rules/universal.md",)
FAMILY_CONTRACTS: dict[str, tuple[str, ...]] = {
    "complexity": ALWAYS_ON + ("rules/complexity-gate.md",),
    "gates": ALWAYS_ON
    + (
        "rules/gates.md",
        "rules/code-review.md",
        "rules/severity.md",
        "rules/specialist-handoff.md",
        "skills/review/references/local-review.md",
        "skills/review/references/classify-diff.md",
        "skills/review/references/pr-posting.md",
    ),
    "planning": ALWAYS_ON
    + (
        "rules/complexity-gate.md",
        "rules/gates.md",
        "skills/planning/SKILL.md",
        "skills/planning/references/decompose-work.md",
        "skills/planning/references/plan-implementation.md",
        "skills/planning/references/validate-plan.md",
        "skills/workflows/references/create-feature.md",
    ),
    "skill_routing": ALWAYS_ON + ("skills/workflows/SKILL.md", "interfaces/workflows.json"),
    "workflows": ALWAYS_ON
    + (
        "rules/complexity-gate.md",
        "rules/gates.md",
        "skills/workflows/SKILL.md",
        "skills/workflows/references/start.md",
        "skills/workflows/references/fix-bug.md",
    ),
}
# Directories under evals/ that hold no cases.
NON_FAMILY_DIRS = frozenset({"replay", "results"})
GRADER = "evals/grader.md"
RESULTS_DIR = Path("evals") / "results"
# Keys of `expected` that qualify the others rather than name a decision.
QUALIFIER_KEYS = frozenset({"never", "or", "covered_by"})
VERDICT = re.compile(r"^[ \t]*Verdict:[ \t]*(PASS|FAIL)[ \t]*$")
TOOLS = ("Read", "Grep", "Glob")
ANSWER_RESTRICTIONS = (
    "Decide as the parent session that follows the contracts above would; this is "
    "an evaluation case, not live work.",
    "Do not edit files, run commands, or mutate external state.",
)
GRADER_RESTRICTIONS = (
    "Grade the answer against the expected value under evals/grader.md; do not "
    "solve the case yourself.",
    "Do not edit files, run commands, or mutate external state.",
)

Dispatch = Callable[[ResolvedRoute, str], tuple[int, dict[str, object]]]


class EvalError(ValueError):
    """The run cannot start: an unknown family, case, model or setting."""


@dataclass(frozen=True)
class Case:
    family: str
    id: str
    input: object = field(hash=False)
    expected: dict[str, object] = field(hash=False)


@dataclass(frozen=True)
class Setting:
    """One model family at one effort on the run's provider."""

    model: str
    selector: str
    effort: str

    @property
    def label(self) -> str:
        return f"{self.model}/{self.effort}"


@dataclass(frozen=True)
class Outcome:
    case: Case
    setting: Setting
    verdict: str  # PASS, FAIL, ERROR (no answer) or UNGRADED (no verdict)
    detail: tuple[str, ...]
    answer_cost: float | None
    grader_cost: float | None


@dataclass(frozen=True)
class EvalRun:
    provider: str
    grader: Setting
    grader_provider: str
    started: datetime
    families: tuple[str, ...]
    settings: tuple[Setting, ...]
    outcomes: tuple[Outcome, ...]
    skipped: tuple[tuple[Case, str], ...]
    toolkit: str
    command: str | None = None


def families(root: Path) -> list[str]:
    """The case families: every directory under evals/ that holds cases."""
    directory = root / "evals"
    return sorted(
        path.name
        for path in directory.iterdir()
        if path.is_dir() and path.name not in NON_FAMILY_DIRS
    )


def load_cases(
    root: Path,
    selected: Sequence[str] | None = None,
    case_ids: Sequence[str] | None = None,
) -> tuple[list[Case], list[tuple[Case, str]]]:
    """The judgment cases to run, and the ones skipped because a test covers them."""
    available = families(root)
    chosen = list(dict.fromkeys(selected or available))
    unknown = [name for name in chosen if name not in available or name not in FAMILY_CONTRACTS]
    if unknown:
        raise EvalError(
            f"unknown eval family: {', '.join(unknown)}; known: {', '.join(available)}"
        )
    cases: list[Case] = []
    skipped: list[tuple[Case, str]] = []
    for family in chosen:
        path = root / "evals" / family / "cases.jsonl"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise EvalError(f"{path.relative_to(root)}:{number} is not JSON") from error
            if row.get("mode") != "judgment":
                continue
            expected = row.get("expected")
            if not isinstance(expected, dict) or not expected:
                raise EvalError(f"{path.relative_to(root)}:{number} has no expected object")
            case = Case(family, str(row["id"]), row.get("input"), expected)
            if "covered_by" in expected:
                skipped.append((case, f"covered by {expected['covered_by']}"))
            else:
                cases.append(case)
    if case_ids:
        wanted = list(dict.fromkeys(case_ids))
        known = {case.id for case in cases} | {case.id for case, _ in skipped}
        missing = [item for item in wanted if item not in known]
        if missing:
            raise EvalError(f"unknown judgment case: {', '.join(missing)}")
        cases = [case for case in cases if case.id in wanted]
        skipped = [item for item in skipped if item[0].id in wanted]
    return cases, skipped


def _route_item(payload: dict[str, object], name: str) -> dict[str, object]:
    for item in payload["routes"]:  # type: ignore[union-attr]
        if item["name"] == name:
            return item
    raise EvalError(f"route {name} is missing from interfaces/model-routing.json")


def _setting(payload: dict[str, object], provider: str, model: str, effort: str) -> Setting:
    catalog = payload["providers"][provider]["models"]  # type: ignore[index]
    if model not in catalog:
        raise EvalError(
            f"unknown {provider} model family: {model}; known: {', '.join(sorted(catalog))}"
        )
    if effort not in ROUTE_EFFORTS:
        raise EvalError(f"effort must be one of {', '.join(ROUTE_EFFORTS)}")
    return Setting(model, str(catalog[model]["selector"]), effort)


def settings_for(
    payload: dict[str, object],
    provider: str,
    family: str,
    models: Sequence[str] = (),
    effort: str | None = None,
) -> list[Setting]:
    """What one family runs on: `--model` and `--effort`, else its owner's defaults.

    Planning cases run on the planning route's model and effort; every other
    family is the parent's judgment, so it runs on the orchestrator model
    (`policy.orchestrator`) at the standard effort.
    """
    if family == "planning":
        item = _route_item(payload, "planning")
        default_model = str(item["providers"][provider]["model"])  # type: ignore[index]
        default_effort = str(item["effort"])
    else:
        default_model = str(payload["policy"]["orchestrator"][provider])  # type: ignore[index]
        default_effort = str(payload["policy"]["efforts"]["standard"])  # type: ignore[index]
    return [
        _setting(payload, provider, model, effort or default_effort)
        for model in (list(dict.fromkeys(models)) or [default_model])
    ]


def grader_setting(payload: dict[str, object], provider: str) -> Setting:
    """The grader runs on the provider's review route: its model and effort."""
    item = _route_item(payload, "review")
    model = str(item["providers"][provider]["model"])  # type: ignore[index]
    return _setting(payload, provider, model, str(item["effort"]))


def eval_route(
    payload: dict[str, object],
    provider: str,
    setting: Setting,
    boundary: str,
    contracts: tuple[str, ...],
    restrictions: tuple[str, ...],
    summary_form: str | None = None,
) -> ResolvedRoute:
    """A read-only dispatch on `setting`, with exactly `contracts` inlined."""
    if provider == "codex":
        controls: dict[str, object] = {"model": setting.model, "sandbox": "read-only"}
    else:
        controls = {
            "model": setting.model,
            "permission_mode": "plan",
            "disallowed_tools": ["Write", "Edit", "NotebookEdit"],
        }
    return ResolvedRoute(
        name="eval",
        boundary=boundary,
        required_contracts=contracts,
        provider=provider,
        family=setting.model,
        selector=setting.selector,
        effort=setting.effort,
        responsibility="evaluation",
        restrictions=restrictions,
        controls=controls,
        minimum_cli=str(payload["providers"][provider]["minimum_cli"]),  # type: ignore[index]
        summary_form=summary_form,
        tools=TOOLS,
    )


def _situation(case: Case) -> str:
    return case.input if isinstance(case.input, str) else json.dumps(case.input, sort_keys=True)


def answer_keys(case: Case) -> list[str]:
    return [key for key in case.expected if key not in QUALIFIER_KEYS]


def answer_prompt(case: Case) -> str:
    """The task for the model under test: the situation and the keys, never the values.

    The case id stays out: ids such as `route-fix-bug` name the answer.
    """
    keys = ", ".join(f"`{key}`" for key in answer_keys(case))
    return (
        f"Evaluation case (family `{case.family}`).\n\n"
        f"Situation:\n{_situation(case)}\n\n"
        "Decide what the toolkit's parent session does in this situation, following "
        "the contracts in your instructions. Do not ask questions; decide from what "
        "is given.\n\n"
        "Return status `completed`. In `summary`, put exactly one JSON object with "
        f"these keys and no others: {keys}. Use the contracts' own vocabulary for "
        "values, and null for a key the contracts leave undecided. Leave `findings` "
        "empty. In `verification`, name the contract sections you relied on.\n"
    )


def grader_prompt(case: Case, answer: str) -> str:
    return (
        f"Grade this answer.\n\nCase: `{case.id}` (family `{case.family}`)\n\n"
        f"Situation:\n{_situation(case)}\n\n"
        f"Expected:\n{json.dumps(case.expected, indent=2, sort_keys=True)}\n\n"
        "Answer under test, verbatim:\nANSWER_BEGIN\n"
        f"{answer}{'' if answer.endswith(chr(10)) else chr(10)}ANSWER_END\n"
    )


def _failure(code: int, envelope: dict[str, object]) -> str | None:
    error = envelope.get("error")
    if isinstance(error, dict):
        category = error.get("category")
        prefix = f"refused ({category})" if category else str(error.get("code", "error"))
        return f"{prefix}: {error.get('message', '')}".strip()
    result = envelope.get("result")
    if not isinstance(result, dict):
        return f"no result (exit {code})"
    if result.get("status") != "completed":
        return f"worker {result.get('status')}: {str(result.get('summary', ''))[:200]}"
    return None


def envelope_cost(envelope: dict[str, object], selector: str, when: datetime) -> float | None:
    """The provider's own cost figure, else the reported tokens priced by aitk/pricing.py.

    Zero when no provider process started; None (unpriced) when one ran and
    reported no usage.
    """
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        transport = envelope.get("transport")
        started = isinstance(transport, dict) and bool(transport.get("started"))
        return None if started else 0.0
    reported = usage.get("cost_usd")
    if isinstance(reported, (int, float)) and not isinstance(reported, bool):
        return float(reported)
    return compute_cost(usage, selector, when.isoformat())


def verdict(summary: str) -> str | None:
    """PASS or FAIL from the grader summary's first non-empty line, else None."""
    for line in summary.splitlines():
        if line.strip():
            match = VERDICT.match(line)
            return match.group(1) if match else None
    return None


def run_case(
    case: Case,
    setting: Setting,
    grader: Setting,
    answer_route: ResolvedRoute,
    grade_route: ResolvedRoute,
    dispatch: Dispatch,
    when: datetime,
) -> Outcome:
    """Answer one case on one setting, then grade the answer."""
    code, envelope = dispatch(answer_route, answer_prompt(case))
    answer_cost = envelope_cost(envelope, setting.selector, when)
    failure = _failure(code, envelope)
    if failure is not None:
        return Outcome(case, setting, "ERROR", (failure,), answer_cost, 0.0)
    answer = str(envelope["result"]["summary"])  # type: ignore[index]
    code, graded = dispatch(grade_route, grader_prompt(case, answer))
    grader_cost = envelope_cost(graded, grader.selector, when)
    failure = _failure(code, graded)
    if failure is not None:
        return Outcome(case, setting, "UNGRADED", (f"grader: {failure}",), answer_cost, grader_cost)
    result = graded["result"]
    decided = verdict(str(result["summary"]))  # type: ignore[index]
    if decided is None:
        return Outcome(
            case, setting, "UNGRADED", ("grader: no verdict on the first line",), answer_cost, grader_cost
        )
    misses = tuple(str(item) for item in result["findings"]) if decided == "FAIL" else ()  # type: ignore[index]
    return Outcome(case, setting, decided, misses, answer_cost, grader_cost)


def transport_dispatch(
    root: Path,
    workspace: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Dispatch:
    """The real dispatch: one `model-run` worker per call, in an empty workspace."""

    def dispatch(route: ResolvedRoute, prompt: str) -> tuple[int, dict[str, object]]:
        return run_resolved(root, route, prompt, workspace, timeout_seconds, runner)

    return dispatch


def toolkit_version(root: Path) -> str:
    """The toolkit commit the run measured, marked when the tree had local edits."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            text=True, capture_output=True, check=False, timeout=30,
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            text=True, capture_output=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if head.returncode:
        return "unknown"
    return head.stdout.strip() + (" (with local changes)" if status.stdout.strip() else "")


@dataclass(frozen=True)
class Plan:
    """A resolved run: what to dispatch, what is skipped, and who grades."""

    provider: str
    pairs: tuple[tuple[Case, Setting], ...]
    skipped: tuple[tuple[Case, str], ...]
    grader: Setting
    grader_provider: str
    payload: dict[str, object]


def plan(
    root: Path,
    provider: str,
    selected: Sequence[str] | None = None,
    case_ids: Sequence[str] | None = None,
    models: Sequence[str] = (),
    effort: str | None = None,
    grader_provider: str | None = None,
) -> Plan:
    """Resolve a run without dispatching anything."""
    if provider not in PROVIDERS:
        raise EvalError(f"unknown provider: {provider}")
    grading = grader_provider or provider
    if grading not in PROVIDERS:
        raise EvalError(f"unknown grader provider: {grading}")
    try:
        payload = load_model_routing(root)
    except ModelRouteError as error:
        raise EvalError(str(error)) from error
    cases, skipped = load_cases(root, selected, case_ids)
    pairs: list[tuple[Case, Setting]] = []
    per_family: dict[str, list[Setting]] = {}
    for case in cases:
        if case.family not in per_family:
            per_family[case.family] = settings_for(payload, provider, case.family, models, effort)
        pairs.extend((case, setting) for setting in per_family[case.family])
    return Plan(
        provider, tuple(pairs), tuple(skipped), grader_setting(payload, grading), grading, payload
    )


def run_eval(
    root: Path,
    provider: str,
    selected: Sequence[str] | None = None,
    case_ids: Sequence[str] | None = None,
    models: Sequence[str] = (),
    effort: str | None = None,
    grader_provider: str | None = None,
    jobs: int = 1,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    dispatch: Dispatch | None = None,
    now: datetime | None = None,
    command: str | None = None,
) -> EvalRun:
    """Answer and grade every selected case on every setting."""
    if jobs < 1:
        raise EvalError("--jobs must be at least 1")
    resolved = plan(root, provider, selected, case_ids, models, effort, grader_provider)
    pairs, skipped, grader, payload = (
        resolved.pairs, resolved.skipped, resolved.grader, resolved.payload
    )
    started = now or datetime.now(timezone.utc)
    grade_route = eval_route(
        payload, resolved.grader_provider, grader, "eval.grade", (GRADER,),
        GRADER_RESTRICTIONS, "eval-verdict",
    )
    with tempfile.TemporaryDirectory(prefix="aitk-eval-") as workspace:
        send = dispatch or transport_dispatch(root, Path(workspace), timeout_seconds)

        def one(pair: tuple[Case, Setting]) -> Outcome:
            case, setting = pair
            route = eval_route(
                payload, provider, setting, f"eval.{case.family}",
                FAMILY_CONTRACTS[case.family], ANSWER_RESTRICTIONS,
            )
            try:
                return run_case(case, setting, grader, route, grade_route, send, started)
            except ModelRouteError as error:
                return Outcome(case, setting, "ERROR", (str(error),), 0.0, 0.0)

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            outcomes = tuple(pool.map(one, pairs))
    used = tuple(dict.fromkeys(setting for _case, setting in pairs))
    chosen = tuple(dict.fromkeys(case.family for case, _ in pairs)) or tuple(
        dict.fromkeys(case.family for case, _ in skipped)
    )
    return EvalRun(
        provider, grader, resolved.grader_provider, started, chosen, used, outcomes,
        skipped, toolkit_version(root), command,
    )


# --- Results ----------------------------------------------------------------


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _money(values: Iterable[float | None]) -> str:
    items = list(values)
    known = [value for value in items if value is not None]
    unpriced = len(items) - len(known)
    text = f"${sum(known):.4f}" if known else "–"
    return text + (f" ({unpriced} unpriced)" if unpriced and known else "")


def tally(outcomes: Iterable[Outcome]) -> dict[str, int]:
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "UNGRADED": 0}
    for outcome in outcomes:
        counts[outcome.verdict] += 1
    return counts


def render(run: EvalRun) -> str:
    """One run's section of the results file."""
    stamp = run.started.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"## Run {stamp}",
        "",
        f"- Provider: {run.provider}",
        f"- Grader: {run.grader_provider} {run.grader.model} at {run.grader.effort} effort, "
        f"`{GRADER}`",
        # Results are committed, and a selector written here would be a copy
        # the selector-home test refuses; the commit's catalog names it.
        f"- Toolkit: {run.toolkit} (its `interfaces/model-routing.json` names each "
        "family's model)",
        f"- Families: {', '.join(run.families) or 'none'}",
        f"- Cases: {len({o.case.id for o in run.outcomes})} judgment cases, "
        f"{len(run.settings)} setting(s), {len(run.skipped)} skipped",
    ]
    if run.command:
        lines.append(f"- Command: `{run.command}`")
    lines += [
        "",
        "Pass rate is passes over cases run; ERROR is no answer (outage, refusal, "
        "invalid result), UNGRADED is an answer the grader could not grade. Cost is "
        "API-equivalent USD (the provider's figure, else reported tokens priced by "
        "`aitk/pricing.py`).",
        "",
        "| Setting | Pass | Fail | Error | Ungraded | Pass rate | Answer cost | Grader cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for setting in run.settings:
        mine = [o for o in run.outcomes if o.setting == setting]
        counts = tally(mine)
        rate = f"{100 * counts['PASS'] / len(mine):.0f}%" if mine else "–"
        lines.append(
            f"| {setting.label} | {counts['PASS']} | {counts['FAIL']} | "
            f"{counts['ERROR']} | {counts['UNGRADED']} | {rate} | "
            f"{_money(o.answer_cost for o in mine)} | {_money(o.grader_cost for o in mine)} |"
        )
    header = " | ".join(setting.label for setting in run.settings)
    rule = "|".join("---" for _ in run.settings)
    lines += ["", "### By family", "", f"| Family | {header} |", f"|---|{rule}|"]
    for family in run.families:
        cells = []
        for setting in run.settings:
            mine = [o for o in run.outcomes if o.setting == setting and o.case.family == family]
            cells.append(f"{tally(mine)['PASS']}/{len(mine)}" if mine else "–")
        lines.append(f"| {family} | {' | '.join(cells)} |")
    lines += ["", "### Cases", "", f"| Case | Family | {header} |", f"|---|---|{rule}|"]
    cases = list(dict.fromkeys(o.case for o in run.outcomes))
    for case in cases:
        cells = []
        for setting in run.settings:
            found = [o for o in run.outcomes if o.case == case and o.setting == setting]
            cells.append(found[0].verdict if found else "–")
        lines.append(f"| `{case.id}` | {case.family} | {' | '.join(cells)} |")
    misses = [o for o in run.outcomes if o.verdict != "PASS"]
    lines += ["", "### Misses", ""]
    if not misses:
        lines.append("None.")
    for outcome in misses:
        detail = "; ".join(outcome.detail) or "no detail"
        for known in (*run.settings, run.grader):
            detail = detail.replace(known.selector, known.model)
        lines.append(
            f"- `{outcome.case.id}` on {outcome.setting.label}: {outcome.verdict} — {_cell(detail)}"
        )
    if run.skipped:
        lines += ["", "### Skipped", ""]
        for case, reason in run.skipped:
            lines.append(f"- `{case.id}` ({case.family}): {reason}")
    return "\n".join(lines) + "\n"


def results_path(root: Path, provider: str, started: datetime) -> Path:
    date = started.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return root / RESULTS_DIR / f"{date}-{provider}.md"


def write_results(root: Path, run: EvalRun, output: Path | None = None) -> Path:
    """Append the run's section to the day's results file for its provider."""
    path = output or results_path(root, run.provider, run.started)
    path.parent.mkdir(parents=True, exist_ok=True)
    section = render(run)
    if path.is_file() and path.stat().st_size:
        text = path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + section
    else:
        date = run.started.astimezone(timezone.utc).strftime("%Y-%m-%d")
        text = f"# Eval results: {run.provider}, {date}\n\n{section}"
    path.write_text(text, encoding="utf-8")
    return path


def render_plan(resolved: Plan) -> str:
    """What a run would dispatch, for `--dry-run`: no provider is called."""
    pairs, grader = resolved.pairs, resolved.grader
    lines = [
        f"eval plan: provider {resolved.provider}, {len(pairs)} answer dispatch(es) "
        "and as many grades",
        f"grader: {resolved.grader_provider} {grader.model} ({grader.selector}, "
        f"effort {grader.effort})",
    ]
    for family in dict.fromkeys(case.family for case, _ in pairs):
        settings = dict.fromkeys(
            f"{s.label} ({s.selector})" for c, s in pairs if c.family == family
        )
        count = len({c.id for c, _ in pairs if c.family == family})
        lines.append(
            f"- {family}: {count} case(s) on {', '.join(settings)}; "
            f"contracts {', '.join(FAMILY_CONTRACTS[family])}"
        )
    for case, reason in resolved.skipped:
        lines.append(f"- skipped {case.id}: {reason}")
    return "\n".join(lines)
