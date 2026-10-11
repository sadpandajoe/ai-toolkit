"""Review planning in code: which lanes run, how their findings merge, lane yield.

`skills/review/references/local-review.md` and `pr-review.md` keep the parent's
judgment (validating findings, deciding what is substantive, locking tests,
disputes). The deterministic half lives here:

- ``bin/aitk review plan`` classifies the diff (classify-diff.md's numbers:
  domains, file and changed-line counts without lockfiles and generated files,
  the refactor heuristic, the escalation phrase match, toolkit-sensitive path
  hits, touch weight per lens) and answers which lanes to launch: boundary,
  route, provider and family for the independent lane, the second family, the
  deep lenses under their two-lens cap, the verifier family, the delta rule,
  and ``BLOCKED (degraded)`` when an independent judgment cannot be had.
- ``bin/aitk review merge`` dedupes the lanes' findings by file:line, computes
  convergence, applies the coverage check, and lists the single-source majors
  that still need a verifier on the other family.
- ``bin/aitk lane-yield`` applies the Yield Thresholds in
  ``rules/code-review.md`` to the metrics file and appends a ``low-yield-lane``
  observation for each new demotion. The thresholds are the constants below.

The coverage check (D13) has its single home in :func:`coverage_gaps`: a clean
verdict counts only when the lane's ``verification`` list covers every changed
file other than generated files and lockfiles.

The ``review.lanes`` schema (N10)
---------------------------------
A metrics event may carry ``review.lanes``: a map from lane name to that run's
counts. Lane names are ``independent``, ``second-family``, ``verify-major``,
``delta`` and the deep lenses ``adversarial``, ``deep-quality`` and
``architecture`` (a lens path such as ``skills/review/references/adversarial.md``
reads as its bare name). Each count is a non-negative integer; a missing count
reads as zero:

- ``raised``: ``[major]`` and ``[minor]`` findings the lane returned;
- ``accepted``: those the parent accepted after validation;
- ``converged``: accepted findings another lane also raised;
- ``confirmed`` / ``refuted``: the verifier's verdicts (``verify-major``), or
  first-lane majors the second family refuted (``second-family``);
- ``not_fixed`` / ``introduced``: the delta pass's grades (``delta``).

``review merge --json`` returns ``lanes`` in this shape with ``raised`` and
``converged`` filled in; the parent adds ``accepted`` after validating. A lane
with fewer runs than its window is not judged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Iterable, Mapping

from .model_routing import ModelRouteError, load_model_routing, run_model
from .project_state import (
    COMPLEXITIES,
    append_observation,
    git_toplevel,
    state_pathspecs,
    toolkit_data_root,
)


class ReviewPlanError(ValueError):
    """The planner or merger could not read its inputs."""


# --- Yield thresholds (rules/code-review.md, Yield Thresholds) -------------

DEEP_LENSES = ("adversarial", "deep-quality", "architecture")
LENS_WINDOW = 5
LANE_WINDOW = 10
# The rule reads "CONFIRMED on fewer than 3 in 10": a rate over the majors the
# verifier actually judged in the window, not an absolute count of confirmations.
VERIFIER_CONFIRMED_PER_TEN = 3
NEVER_DEMOTED = ("independent",)


@dataclass(frozen=True)
class Demotion:
    lane: str
    window: int
    runs: int
    observed: dict[str, int]
    consequence: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_events(path: Path) -> list[dict[str, object]]:
    """Read the metrics file; skip lines that are not JSON objects."""
    if not path.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _count(stats: object, name: str) -> int:
    if not isinstance(stats, dict):
        return 0
    value = stats.get(name, 0)
    return int(value) if isinstance(value, (int, float)) and value >= 0 else 0


def lane_name(lane: str) -> str:
    """Lens paths and bare names refer to the same lane."""
    name = lane.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name


def lane_history(events: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Return per-lane run stats, oldest first, from ``review.lanes``."""
    history: dict[str, list[dict[str, object]]] = {}
    for event in events:
        review = event.get("review")
        lanes = review.get("lanes") if isinstance(review, dict) else None
        if not isinstance(lanes, dict):
            continue
        for lane, stats in lanes.items():
            if isinstance(lane, str) and isinstance(stats, dict):
                history.setdefault(lane_name(lane), []).append(stats)
    return history


def _sum(runs: list[dict[str, object]], name: str) -> int:
    return sum(_count(stats, name) for stats in runs)


def evaluate(events: list[dict[str, object]]) -> list[Demotion]:
    """Apply the yield table to the lane history and return the demotions."""
    demotions: list[Demotion] = []
    for lane, runs in sorted(lane_history(events).items()):
        if lane in NEVER_DEMOTED:
            continue
        if lane in DEEP_LENSES:
            window = runs[-LENS_WINDOW:]
            if len(window) < LENS_WINDOW:
                continue
            raised, accepted = _sum(window, "raised"), _sum(window, "accepted")
            if accepted == 0 or accepted * 4 < raised:
                demotions.append(
                    Demotion(
                        lane,
                        LENS_WINDOW,
                        len(window),
                        {"raised": raised, "accepted": accepted},
                        "opt-in only: run on an explicit ask until reflect reviews it; "
                        "record the classifier flag as deferred (low yield)",
                    )
                )
            continue
        window = runs[-LANE_WINDOW:]
        if len(window) < LANE_WINDOW:
            continue
        if lane == "second-family":
            unique = sum(max(_count(s, "accepted") - _count(s, "converged"), 0) for s in window)
            refuted = _sum(window, "refuted")
            if unique == 0 and refuted == 0:
                demotions.append(
                    Demotion(
                        lane,
                        LANE_WINDOW,
                        len(window),
                        {"unique_accepted": unique, "refuted": refuted},
                        "COMPLEX only: drop the CORE trigger",
                    )
                )
        elif lane == "verify-major":
            confirmed, refuted = _sum(window, "confirmed"), _sum(window, "refuted")
            verified = confirmed + refuted
            if verified and confirmed * 10 < verified * VERIFIER_CONFIRMED_PER_TEN:
                demotions.append(
                    Demotion(
                        lane,
                        LANE_WINDOW,
                        len(window),
                        {"confirmed": confirmed, "refuted": refuted, "verified": verified},
                        "single-source majors from the raising lane default to [minor]; "
                        "write a low-yield-lane observation for that lane",
                    )
                )
        elif lane == "delta":
            not_fixed, introduced = _sum(window, "not_fixed"), _sum(window, "introduced")
            if not_fixed == 0 and introduced == 0:
                demotions.append(
                    Demotion(
                        lane,
                        LANE_WINDOW,
                        len(window),
                        {"not_fixed": not_fixed, "introduced": introduced},
                        "delta pass runs only after a [major] fix",
                    )
                )
    return demotions


def default_metrics_file(cwd: Path | None = None) -> Path:
    """The metrics file `bin/aitk metrics emit` writes: `.ai-toolkit/` at the repository top."""
    return toolkit_data_root(cwd or Path.cwd()) / ".ai-toolkit" / "metrics.jsonl"


def record_demotions(directory: Path, demotions: Iterable[Demotion]) -> list[str]:
    """Append a ``low-yield-lane`` observation for each demotion not yet queued.

    A demotion already in the queue with the same numbers is not appended
    again, so re-running ``lane-yield`` over unchanged metrics adds nothing.
    """
    queue = toolkit_data_root(directory) / ".ai-toolkit" / "observations.jsonl"
    seen: set[tuple[str, str]] = set()
    for entry in load_events(queue):
        if entry.get("kind") == "low-yield-lane" and isinstance(entry.get("lane"), str):
            seen.add((str(entry["lane"]), json.dumps(entry.get("observed"), sort_keys=True)))
    appended: list[str] = []
    for item in demotions:
        key = (item.lane, json.dumps(item.observed, sort_keys=True))
        if key in seen:
            continue
        observed = ", ".join(f"{name}={value}" for name, value in item.observed.items())
        append_observation(
            directory,
            {
                "kind": "low-yield-lane",
                "workflow": "review-code",
                "lane": item.lane,
                "observed": item.observed,
                "detail": f"{item.lane} below its yield threshold over the last {item.runs} runs "
                f"({observed}): {item.consequence}",
                "evidence": "bin/aitk lane-yield",
            },
        )
        seen.add(key)
        appended.append(item.lane)
    return appended


# --- Diff classification (classify-diff.md) --------------------------------

PROVIDERS = ("codex", "claude")
IMPACTS = ("CORE", "STANDARD", "PERIPHERAL")
KINDS = ("local", "pr")
LOCKFILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
        "Cargo.lock",
        "go.sum",
        "Gemfile.lock",
        "composer.lock",
    }
)
GENERATED_PATTERNS = (
    "build/*",
    "dist/*",
    "node_modules/*",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.pb.go",
    "*.generated.*",
    "*/__snapshots__/*",
    "*.snap",
)
GENERATED_HEADER = re.compile(
    r"@generated|Code generated .{0,80}DO NOT EDIT|Generated by .{0,80}do not edit",
    re.IGNORECASE,
)
# When reviewing ai-toolkit itself: agent capability configuration, worker
# context assembly, and trust boundaries (publish or push authorization,
# sandbox enforcement, hooks). classify-diff.md names the same paths in prose;
# tests/test_review_plan.py keeps the two lists in step.
TOOLKIT_SENSITIVE = (
    "interfaces/model-routing.json",
    "aitk/model_routing.py",
    "aitk/routing_*.py",
    "agents/*",
    "aitk/build.py",
    "aitk/installer.py",
    "aitk/deliver.py",
    "aitk/review_plan.py",
    "aitk/hooks/*",
    "aitk/claude_hooks.py",
    "hooks/*",
    ".codex-plugin/*",
    ".mcp.json",
)
DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tests", ("*_test.*", "*.test.*", "*.spec.*", "tests/*", "*/tests/*", "test/*", "*/test/*", "conftest.py", "*/conftest.py")),
    ("Infrastructure", ("Dockerfile", "*/Dockerfile", "*.dockerfile", ".github/workflows/*", ".gitlab-ci.yml", "terraform/*", "*/terraform/*", "*.tf")),
    ("Frontend", ("*.tsx", "*.jsx", "*.vue", "*.css", "*.scss", "components/*", "*/components/*")),
    ("Backend", ("*.py", "*.go", "*.rs", "*.java", "api/*", "*/api/*", "server/*", "*/server/*")),
    ("Config", ("*.toml", "*.ini", ".env*", "*/.env*", "settings.*", "*/settings.*", "*.cfg")),
)
SECURITY_WORDS = re.compile(
    r"auth|security|permission|crypt|token|secret|session|login|password|oauth|acl|rbac|sandbox|sql",
    re.IGNORECASE,
)
REFACTOR_TITLE = re.compile(r"^\s*refactor", re.IGNORECASE)
REFACTOR_WORDS = re.compile(r"\b(restructur\w*|extract\w*|decompos\w*|clean[- ]?up)\b", re.IGNORECASE)
# The refactor heuristic: a net-neutral line delta with high churn, or renames,
# and no test file changed. Net-neutral means the delta is within a tenth of
# the churn; high churn is at least this many changed lines.
REFACTOR_CHURN = 200
REFACTOR_NET_RATIO = 0.1
ESCALATION_PHRASES = ("deep quality review", "deep review", "thermonuclear")
ESCALATION_EFFORTS = ("max", "ultra")
ADVERSARIAL_ASK = re.compile(r"\badversarial\b|red[- ]team", re.IGNORECASE)
CODE_JUDO_ASK = re.compile(r"code[- ]judo", re.IGNORECASE)
LENS_PATHS = {
    "adversarial": "skills/review/references/adversarial.md",
    "deep-quality": "skills/review/references/deep-quality.md",
    "architecture": "skills/review/references/architecture.md",
}
# The two-lens cap. On a security-sensitive diff adversarial is never dropped:
# deep-quality goes first, then architecture. Otherwise the lens the diff
# touches least goes, ties broken in this order.
DROP_ORDER = ("deep-quality", "architecture", "adversarial")
MAX_LENSES = 2


@dataclass(frozen=True)
class ChangedFile:
    path: str
    added: int = 0
    deleted: int = 0
    status: str = "modified"  # modified | added | deleted | renamed
    binary: bool = False
    old_path: str | None = None
    generated_header: bool = False

    @property
    def churn(self) -> int:
        return self.added + self.deleted


def _match(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def excluded_reason(item: ChangedFile) -> str | None:
    """`lockfile` or `generated` for files the counts and coverage leave out."""
    if PurePosixPath(item.path).name in LOCKFILES:
        return "lockfile"
    if item.generated_header or _match(item.path, GENERATED_PATTERNS):
        return "generated"
    return None


def domain_of(path: str) -> str:
    for domain, patterns in DOMAIN_RULES:
        if _match(path, patterns):
            return domain
    return "Other"


def toolkit_sensitive(path: str) -> bool:
    return _match(path, TOOLKIT_SENSITIVE)


def is_toolkit_repository(root: Path | None) -> bool:
    return bool(root) and (root / "interfaces/model-routing.json").is_file() and (root / "aitk").is_dir()


def _phrases(ask: str) -> tuple[str | None, bool]:
    """The escalation phrase in the ask, and whether a bare deep-quality ask remains."""
    text = " ".join(ask.lower().split())
    escalation = next((phrase for phrase in ESCALATION_PHRASES if phrase in text), None)
    remainder = text.replace("deep quality review", " ")
    return escalation, "deep quality" in remainder or "deep-quality" in remainder


def classify(
    files: Iterable[ChangedFile],
    *,
    titles: Iterable[str] = (),
    ask: str = "",
    effort: str | None = None,
    security_sensitive: bool = False,
    architecture: bool = False,
    refactor: bool = False,
    toolkit: bool = False,
    deep: bool = False,
    adversarial: bool = False,
) -> dict[str, object]:
    """classify-diff.md's deterministic numbers and flags for one diff."""
    files = list(files)
    counted = [item for item in files if excluded_reason(item) is None]
    domains: dict[str, list[str]] = {}
    for item in counted:
        domains.setdefault(domain_of(item.path), []).append(item.path)
    added = sum(item.added for item in counted)
    deleted = sum(item.deleted for item in counted)
    churn = added + deleted
    renames = sum(1 for item in counted if item.status == "renamed")
    tests_changed = "Tests" in domains
    hits = sorted(item.path for item in files if toolkit and toolkit_sensitive(item.path))

    escalation_phrase, deep_quality_ask = _phrases(ask)
    escalation_why = None
    if deep:
        escalation_why = "--deep"
    elif escalation_phrase:
        escalation_why = f'"{escalation_phrase}" ask'
    elif effort in ESCALATION_EFFORTS:
        escalation_why = f"{effort} effort"

    titles = [title for title in titles if title.strip()]
    refactor_why = None
    if refactor:
        refactor_why = "caller flag"
    elif any(REFACTOR_TITLE.search(title) for title in titles):
        refactor_why = "title starts with refactor"
    elif any(REFACTOR_WORDS.search(title) for title in titles):
        refactor_why = "title names a restructuring"
    elif not tests_changed and counted and (
        renames or (churn >= REFACTOR_CHURN and abs(added - deleted) <= churn * REFACTOR_NET_RATIO)
    ):
        refactor_why = (
            f"{renames} rename(s), tests unchanged"
            if renames
            else f"net-neutral delta (+{added}/-{deleted}) with high churn, tests unchanged"
        )

    security_why = []
    if security_sensitive:
        security_why.append("caller flag")
    if hits:
        security_why.append("toolkit-sensitive paths: " + ", ".join(hits))

    def lines(selected: Iterable[ChangedFile]) -> int:
        return sum(item.churn for item in selected)

    touch = {
        "adversarial": lines(
            item for item in counted if item.path in hits or SECURITY_WORDS.search(item.path)
        ),
        "deep-quality": lines(item for item in counted if domain_of(item.path) in {"Backend", "Frontend"}),
        "architecture": lines(item for item in counted if item.status != "modified"),
    }
    explicit = {
        "adversarial": adversarial or bool(ADVERSARIAL_ASK.search(ask)),
        "deep-quality": deep_quality_ask,
        "code-judo": bool(CODE_JUDO_ASK.search(ask)),
    }
    return {
        "files": len(counted),
        "changed_lines": churn,
        "added": added,
        "deleted": deleted,
        "renames": renames,
        "excluded": {item.path: excluded_reason(item) for item in files if excluded_reason(item)},
        "domains": {name: sorted(paths) for name, paths in sorted(domains.items())},
        "security_sensitive": bool(security_why),
        "security_why": "; ".join(security_why) or None,
        "toolkit_sensitive_hits": hits,
        "architecture_change": architecture,
        "refactor_shaped": refactor_why is not None,
        "refactor_why": refactor_why,
        "deep_tier_escalation": escalation_why is not None,
        "escalation_why": escalation_why,
        "explicit_asks": sorted(name for name, asked in explicit.items() if asked),
        "code_judo": bool(
            escalation_why or any(REFACTOR_TITLE.search(title) for title in titles) or explicit["code-judo"]
        ),
        "touch": touch,
    }


# --- Diff collection --------------------------------------------------------


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _git_value(repo: Path, *arguments: str) -> str | None:
    result = _git(repo, *arguments)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _header_says_generated(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(2048)
    except OSError:
        return False
    return bool(GENERATED_HEADER.search(head.decode("utf-8", errors="replace")))


def _text_lines(path: Path) -> tuple[int, bool]:
    try:
        data = path.read_bytes()
    except OSError:
        return 0, False
    if b"\0" in data[:8192]:
        return 0, True
    return data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1), False


def local_changes(repo: Path, base: str) -> list[ChangedFile]:
    """The diff from ``base`` to the working tree, untracked files included.

    Local workflow state (PROJECT.md and the other state files, `.ai-toolkit/`)
    is left out, as it is from the tree `deliver` pushes.
    """
    pathspecs = ["--", ".", *state_pathspecs()]
    numstat = _git(repo, "diff", "--numstat", "-z", "-M", base, *pathspecs)
    statuses = _git(repo, "diff", "--name-status", "-z", "-M", base, *pathspecs)
    if numstat.returncode or statuses.returncode:
        raise ReviewPlanError(f"git diff against {base} failed: {(numstat.stderr or statuses.stderr).strip()}")
    status_of: dict[str, str] = {}
    fields = statuses.stdout.split("\0")
    index = 0
    while index < len(fields) and fields[index]:
        code = fields[index][0]
        if code in "RC":
            status_of[fields[index + 2]] = "renamed" if code == "R" else "added"
            index += 3
            continue
        status_of[fields[index + 1]] = {"A": "added", "D": "deleted"}.get(code, "modified")
        index += 2
    changes: list[ChangedFile] = []
    records = numstat.stdout.split("\0")
    index = 0
    while index < len(records) and records[index]:
        added, deleted, path = records[index].split("\t", 2)
        old_path = None
        if not path:
            old_path, path = records[index + 1], records[index + 2]
            index += 3
        else:
            index += 1
        binary = added == "-"
        changes.append(
            ChangedFile(
                path,
                0 if binary else int(added),
                0 if binary else int(deleted),
                status_of.get(path, "modified"),
                binary,
                old_path,
                _header_says_generated(repo / path),
            )
        )
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z", *pathspecs)
    for path in filter(None, untracked.stdout.split("\0")):
        lines, binary = _text_lines(repo / path)
        changes.append(ChangedFile(path, lines, 0, "added", binary, None, _header_says_generated(repo / path)))
    return sorted(changes, key=lambda item: item.path)


def pr_changes(cwd: Path, reference: str, env: Mapping[str, str] | None = None) -> tuple[list[ChangedFile], str, str]:
    """The files, title and base branch of a PR, from ``gh pr view``."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", reference, "--json", "title,files,baseRefName"],
            cwd=cwd,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except OSError as error:
        raise ReviewPlanError(f"gh could not run: {error}") from error
    if result.returncode:
        raise ReviewPlanError(f"gh pr view {reference} failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
        files = [
            ChangedFile(str(item["path"]), int(item["additions"]), int(item["deletions"]))
            for item in payload["files"]
        ]
        return sorted(files, key=lambda item: item.path), str(payload["title"]), str(payload["baseRefName"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ReviewPlanError(f"gh pr view {reference} returned an unexpected shape") from error


def branch_base(repo: Path) -> str | None:
    """The merge-base with the remote default branch (or main/master)."""
    candidates = []
    remote_head = _git_value(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if remote_head:
        candidates.append(remote_head)
    candidates += ["refs/remotes/origin/main", "refs/remotes/origin/master", "refs/heads/main", "refs/heads/master"]
    for ref in candidates:
        if _git_value(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
            merge_base = _git_value(repo, "merge-base", "HEAD", ref)
            if merge_base:
                return merge_base
    return None


def phase_base(snapshot: Mapping[str, object] | None) -> str | None:
    """The tree the last finished phase recorded, when a later phase is current."""
    if not snapshot:
        return None
    phases = snapshot.get("phases")
    if not isinstance(phases, list):
        return None
    tree = None
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        if phase.get("name") == snapshot.get("current_phase"):
            break
        if phase.get("status") == "done" and isinstance(phase.get("tree"), str):
            tree = str(phase["tree"])
    return tree


# --- Planning ---------------------------------------------------------------


def families(root: Path) -> dict[str, dict[str, str]]:
    """route -> provider -> model family, from the routing manifest."""
    manifest = load_model_routing(root)
    table: dict[str, dict[str, str]] = {}
    for route in manifest["routes"]:  # type: ignore[union-attr]
        table[str(route["name"])] = {
            str(provider): str(binding["model"]) for provider, binding in route["providers"].items()
        }
    return table


def provider_reachable(root: Path, provider: str) -> bool:
    """The transport preflight: the provider CLI exists and meets the routing floor."""
    with tempfile.TemporaryDirectory(prefix="aitk-preflight-") as directory:
        prompt = Path(directory) / "prompt.md"
        prompt.write_text("preflight\n", encoding="utf-8")
        try:
            code, _payload = run_model(
                root, "review", provider, "review.independent", prompt, cwd=Path(directory), dry_run=True
            )
        except (ModelRouteError, OSError):
            return False
    return code == 0


def _other(provider: str) -> str:
    return "claude" if provider == "codex" else "codex"


@dataclass
class _Lane:
    lane: str
    boundary: str
    route: str
    provider: str
    family: str
    lens: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items()}


@dataclass(frozen=True)
class PlanInputs:
    parent: str
    complexity: str
    impact: str = "STANDARD"
    kind: str = "local"
    files: tuple[ChangedFile, ...] = ()
    titles: tuple[str, ...] = ()
    ask: str = ""
    effort: str | None = None
    security_sensitive: bool = False
    architecture: bool = False
    refactor: bool = False
    toolkit: bool = False
    deep: bool = False
    adversarial: bool = False
    reachable: frozenset[str] = frozenset(PROVIDERS)
    demoted: frozenset[str] = frozenset()
    allow_degraded: bool = False
    base: str | None = None
    branch_base: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


def _boundary(kind: str, lane: str) -> str:
    if kind == "pr" and lane in {"independent", "second-family", "deep-lenses"}:
        return f"review.pr-{lane}"
    return f"review.{lane}"


def plan(inputs: PlanInputs, table: Mapping[str, Mapping[str, str]]) -> dict[str, object]:
    """Which lanes to launch for one review, and why (local-review.md, pr-review.md)."""
    if inputs.parent not in PROVIDERS:
        raise ReviewPlanError(f"parent must be one of {', '.join(PROVIDERS)}")
    if inputs.kind not in KINDS:
        raise ReviewPlanError(f"kind must be one of {', '.join(KINDS)}")
    if inputs.impact not in IMPACTS:
        raise ReviewPlanError(f"impact must be one of {', '.join(IMPACTS)}")
    if inputs.complexity not in COMPLEXITIES:
        raise ReviewPlanError(f"complexity must be one of {', '.join(COMPLEXITIES)}")
    facts = classify(
        inputs.files,
        titles=inputs.titles,
        ask=inputs.ask,
        effort=inputs.effort,
        security_sensitive=inputs.security_sensitive,
        architecture=inputs.architecture,
        refactor=inputs.refactor,
        toolkit=inputs.toolkit,
        deep=inputs.deep,
        adversarial=inputs.adversarial,
    )
    escalated = bool(facts["deep_tier_escalation"])
    security = bool(facts["security_sensitive"])
    core = inputs.impact == "CORE"
    complexity = inputs.complexity
    complexity_note = None
    if escalated and complexity != "COMPLEX":
        complexity, complexity_note = "COMPLEX", f"pinned by escalation ({facts['escalation_why']})"
    elif complexity == "TRIVIAL" and core:
        complexity, complexity_note = "STANDARD", "TRIVIAL with CORE impact is reviewed as STANDARD"
    route = "deep-review" if escalated else "review"
    parent, other = inputs.parent, _other(inputs.parent)
    reachable = inputs.reachable
    lanes: list[_Lane] = []
    disclosures: list[str] = []
    status, reason = "ready", None

    # Independent lane: the other provider when reachable; the parent's own
    # provider otherwise, unless the diff is security-sensitive or deep-tier.
    independent_provider = None
    if other in reachable:
        independent_provider = other
    elif parent in reachable and not (security or escalated):
        independent_provider = parent
        disclosures.append("Independent review: same-provider")
    elif parent in reachable and inputs.allow_degraded:
        independent_provider = parent
        disclosures.append("Independent review: same-provider (--allow-degraded, USER_DECISION)")
    elif parent in reachable:
        status = "BLOCKED (degraded)"
        reason = (
            f"{other} is unreachable and the diff is "
            + ("security-sensitive" if security else "deep-tier")
            + "; wait for it or pass --allow-degraded (USER_DECISION)"
        )
    else:
        status, reason = "BLOCKED", "no review provider is reachable"
    if independent_provider:
        lanes.append(
            _Lane(
                "independent",
                _boundary(inputs.kind, "independent"),
                route,
                independent_provider,
                table[route][independent_provider],
            )
        )

    # Second family: COMPLEX, or CORE impact unless the lane's yield demoted it.
    triggers = []
    if complexity == "COMPLEX":
        triggers.append("COMPLEX")
    if core:
        if "second-family" in inputs.demoted:
            disclosures.append("Second family: CORE trigger dropped (low yield; COMPLEX only)")
        else:
            triggers.append("CORE")
    second_note = None
    if triggers and independent_provider:
        second_provider = _other(independent_provider)
        if second_provider in reachable:
            lanes.append(
                _Lane(
                    "second-family",
                    _boundary(inputs.kind, "second-family"),
                    route,
                    second_provider,
                    table[route][second_provider],
                    note=" and ".join(triggers),
                )
            )
        elif security and not inputs.allow_degraded:
            status = "BLOCKED (degraded)"
            reason = f"{second_provider} is unreachable for the second family on a security-sensitive diff"
        else:
            second_note = f"not run: {second_provider} unreachable"
            disclosures.append(f"Second family: {second_note}")
    elif not triggers:
        second_note = "not required"

    # Deep lenses: at most two, on the other provider's deep family when reachable.
    fired: dict[str, str] = {}
    if security or "adversarial" in facts["explicit_asks"]:  # type: ignore[operator]
        fired["adversarial"] = "security-sensitive" if security else "explicit ask"
    if facts["refactor_shaped"] or "deep-quality" in facts["explicit_asks"] or escalated:  # type: ignore[operator]
        fired["deep-quality"] = (
            "refactor-shaped" if facts["refactor_shaped"] else "explicit ask" if not escalated else "deep-tier escalation"
        )
    if facts["architecture_change"] and complexity in {"STANDARD", "COMPLEX"}:
        fired["architecture"] = "architecture change"
    deferred = []
    for lens in list(fired):
        asked = lens in facts["explicit_asks"] or (lens == "deep-quality" and escalated)  # type: ignore[operator]
        if lens in inputs.demoted and not asked:
            deferred.append(lens)
            del fired[lens]
    dropped = None
    if len(fired) > MAX_LENSES:
        if security:
            victim = next(lens for lens in DROP_ORDER if lens in fired and lens != "adversarial")
            why = "security-sensitive diff keeps adversarial"
        else:
            touch = facts["touch"]
            victim = min(fired, key=lambda lens: (touch[lens], DROP_ORDER.index(lens)))  # type: ignore[index]
            why = f"touched least ({touch[victim]} changed lines)"  # type: ignore[index]
        dropped = {"lens": victim, "reason": why}
        del fired[victim]
    for lens, why in fired.items():
        provider = other if other in reachable else parent if parent in reachable else None
        if provider is None or status != "ready":
            continue
        note = why if provider == other else f"{why}; same-provider deep family (disclosed)"
        if provider != other:
            disclosures.append(f"Deep lens {lens}: {other} unreachable, ran on {table['deep-review'][parent]}")
        lanes.append(
            _Lane(lens, _boundary(inputs.kind, "deep-lenses"), "deep-review", provider, table["deep-review"][provider], LENS_PATHS[lens], note)
        )
    if facts["code_judo"] and independent_provider and status == "ready":
        provider = other if other in reachable else parent
        lanes.append(_Lane("code-judo", "review.code-judo", "deep-review", provider, table["deep-review"][provider], note="proposals, not findings"))

    # Verifier: the family that did not raise a single-source major. Not run
    # when the second family ran; on one family it moves to the deep route.
    verifier = None
    verifier_note = None
    if any(lane.lane == "second-family" for lane in lanes):
        verifier_note = "not needed: the second family ran"
    elif "verify-major" in inputs.demoted:
        verifier_note = "demoted: single-source majors default to [minor]"
    elif independent_provider:
        target = _other(independent_provider)
        if target in reachable:
            verifier = {"route": route, "provider": target, "family": table[route][target]}
        elif route == "review":
            verifier = {"route": "deep-review", "provider": independent_provider, "family": table["deep-review"][independent_provider]}
            verifier_note = "single family: the deep route is the other family"
        else:
            verifier_note = "unavailable — single family; single-source majors stay capped at [minor]"
    if verifier:
        verifier["boundary"] = "review.verify-major"

    if inputs.kind == "pr":
        delta = "none"
    elif complexity == "TRIVIAL":
        delta = "none"
    elif "delta" in inputs.demoted:
        delta = "after-major-fix"
    else:
        delta = "after-substantive-fix"
    coverage = sorted(item.path for item in inputs.files if excluded_reason(item) is None and item.status != "deleted")
    return {
        "command": "review plan",
        "kind": inputs.kind,
        "status": status,
        "reason": reason,
        "parent": parent,
        "reachable": sorted(reachable),
        "base": inputs.base,
        "branch_base": inputs.branch_base,
        "complexity": complexity,
        "complexity_note": complexity_note,
        "impact": inputs.impact,
        "exception_available": inputs.kind == "local" and complexity == "TRIVIAL",
        "classification": facts,
        "lanes": [lane.as_dict() for lane in lanes] if status == "ready" else [],
        "second_family": {"triggers": triggers, "note": second_note},
        "deep_lenses": {
            "fired": list(fired),
            "launched": list(fired) if status == "ready" else [],
            "dropped": dropped,
            "deferred": [{"lens": lens, "reason": "deferred (low yield)"} for lens in deferred],
        },
        "verifier": verifier if status == "ready" else None,
        "verifier_note": verifier_note,
        "delta": delta,
        "coverage": {"required": coverage},
        "demoted": sorted(inputs.demoted),
        "disclosures": disclosures,
        **inputs.extra,
    }


def render_plan(payload: Mapping[str, object]) -> str:
    facts = payload["classification"]
    assert isinstance(facts, dict)
    lenses = payload["deep_lenses"]
    assert isinstance(lenses, dict)
    lines = [
        "## Review Plan",
        f"Status: {payload['status']}" + (f" — {payload['reason']}" if payload["reason"] else ""),
        f"Complexity: {payload['complexity']}"
        + (f" ({payload['complexity_note']})" if payload["complexity_note"] else "")
        + f" | Impact: {payload['impact']}",
        f"Base: {payload['base'] or 'n/a'} | Branch base: {payload['branch_base'] or 'n/a'}",
        f"Files analyzed: {facts['files']} ({facts['changed_lines']} changed lines; "
        f"{len(facts['excluded'])} lockfile/generated excluded)",
        f"Security-sensitive: {'YES — ' + str(facts['security_why']) if facts['security_sensitive'] else 'NO'}",
        f"Architecture change: {'YES' if facts['architecture_change'] else 'NO'}",
        f"Refactor-shaped: {'YES — ' + str(facts['refactor_why']) if facts['refactor_shaped'] else 'NO'}",
        f"Deep-tier escalation: {'YES — ' + str(facts['escalation_why']) if facts['deep_tier_escalation'] else 'NO'}",
        f"Code-judo lane: {'YES' if facts['code_judo'] else 'NO'}",
        "Deep lenses: "
        + (", ".join(lenses["fired"]) or "none")  # type: ignore[arg-type]
        + ("" if lenses["launched"] or not lenses["fired"] else " (not launched: blocked)")
        + (f" — dropped {lenses['dropped']['lens']}: {lenses['dropped']['reason']}" if lenses["dropped"] else ""),
        "",
        "### Lanes",
    ]
    for lane in payload["lanes"]:  # type: ignore[union-attr]
        lens = f" --lens {lane['lens']}" if lane["lens"] else ""
        note = f"  ({lane['note']})" if lane["note"] else ""
        lines.append(
            f"- {lane['lane']}: bin/aitk model-run {lane['route']} --provider {lane['provider']} "
            f"--boundary {lane['boundary']}{lens} → {lane['family']}{note}"
        )
    if not payload["lanes"]:
        lines.append("- none")
    verifier = payload["verifier"]
    lines.append(
        "Verifier: "
        + (f"{verifier['route']} on {verifier['provider']} ({verifier['family']})" if isinstance(verifier, dict) else "none")
        + (f" — {payload['verifier_note']}" if payload["verifier_note"] else "")
    )
    lines.append(f"Delta: {payload['delta']}")
    for item in lenses["deferred"]:  # type: ignore[union-attr]
        lines.append(f"Deferred lens: {item['lens']} — {item['reason']}")
    for line in payload["disclosures"]:  # type: ignore[union-attr]
        lines.append(f"Disclosed: {line}")
    return "\n".join(lines)


# --- Merging ----------------------------------------------------------------

SEVERITIES = ("major", "minor", "nitpick")
SEVERITY_TAG = re.compile(r"^\s*\[(major|minor|nitpick)\]\s*", re.IGNORECASE)
CITATION = re.compile(r"((?:[\w.@+-]+/)*[\w.@+-]+\.[A-Za-z0-9]+):(\d+)")
LANE_LABELS = ("independent", "second-family", *DEEP_LENSES)
MERGE_BOUNDARIES = {
    "review.independent": "independent",
    "review.pr-independent": "independent",
    "review.second-family": "second-family",
    "review.pr-second-family": "second-family",
    "review.deep-lenses": None,
    "review.pr-deep-lenses": None,
}


@dataclass(frozen=True)
class LaneResult:
    lane: str
    provider: str
    route: str
    family: str
    findings: tuple[str, ...]
    verification: tuple[str, ...]


def lane_result(envelope: object, label: str | None = None, index: int = 0) -> LaneResult:
    """Read one saved `model-run` envelope as a reviewer lane."""
    if not isinstance(envelope, dict):
        raise ReviewPlanError("a result must be a model-run envelope (a JSON object)")
    boundary = envelope.get("boundary")
    if boundary not in MERGE_BOUNDARIES:
        raise ReviewPlanError(
            f"review merge takes reviewer lanes, not {boundary!r}; verifier and delta results are graded by the parent"
        )
    result = envelope.get("result")
    if envelope.get("dry_run") or not isinstance(result, dict):
        raise ReviewPlanError(f"the {boundary} envelope carries no worker result")
    if result.get("status") != "completed":
        raise ReviewPlanError(f"the {boundary} lane did not complete (status {result.get('status')!r})")
    findings, verification = result.get("findings"), result.get("verification")
    if not isinstance(findings, list) or not isinstance(verification, list):
        raise ReviewPlanError(f"the {boundary} result lacks findings or verification")
    lane = label or MERGE_BOUNDARIES[boundary] or f"deep-lens-{index}"
    request = envelope.get("request")
    family = str(request.get("family")) if isinstance(request, dict) else ""
    return LaneResult(
        lane,
        str(envelope.get("provider")),
        str(envelope.get("route")),
        family,
        tuple(str(item) for item in findings),
        tuple(str(item) for item in verification),
    )


def coverage_gaps(required: Iterable[str], verification: Iterable[str]) -> list[str]:
    """Changed files a clean verdict's verification list does not mention (D13).

    A file is covered when its path appears in a verification entry, or its
    file name does and no other required file shares that name.
    """
    required = list(required)
    text = "\n".join(verification)
    names: dict[str, int] = {}
    for path in required:
        names[PurePosixPath(path).name] = names.get(PurePosixPath(path).name, 0) + 1
    missing = []
    for path in required:
        name = PurePosixPath(path).name
        if path in text or (names[name] == 1 and re.search(rf"(?<![\w./-]){re.escape(name)}(?![\w-])", text)):
            continue
        missing.append(path)
    return missing


def _finding_key(text: str) -> tuple[str, str | None, str]:
    match = SEVERITY_TAG.match(text)
    severity = match.group(1).lower() if match else "minor"
    body = text[match.end():] if match else text
    citation = CITATION.search(body)
    key = f"{citation.group(1)}:{citation.group(2)}" if citation else " ".join(body.lower().split())
    return key, citation.group(0) if citation else None, severity


def merge(
    lanes: Iterable[LaneResult],
    table: Mapping[str, Mapping[str, str]],
    *,
    coverage_required: Iterable[str] | None = None,
    reproduced: Iterable[str] = (),
    demoted: Iterable[str] = (),
    reachable: Iterable[str] = PROVIDERS,
) -> dict[str, object]:
    """Dedupe by file:line, compute convergence, and list the majors to verify."""
    lanes = list(lanes)
    names = [lane.lane for lane in lanes]
    if len(set(names)) != len(names):
        raise ReviewPlanError("each lane may appear once; label repeated deep lenses with LENS=PATH")
    reproduced, demoted, reachable = set(reproduced), set(demoted), set(reachable)
    merged: dict[str, dict[str, object]] = {}
    for lane in lanes:
        for text in lane.findings:
            key, citation, severity = _finding_key(text)
            entry = merged.setdefault(
                key, {"key": key, "citation": citation, "severity": severity, "lanes": [], "texts": []}
            )
            if SEVERITIES.index(severity) < SEVERITIES.index(str(entry["severity"])):
                entry["severity"] = severity
            if lane.lane not in entry["lanes"]:  # type: ignore[operator]
                entry["lanes"].append(lane.lane)  # type: ignore[union-attr]
            entry["texts"].append(text)  # type: ignore[union-attr]
    findings = sorted(merged.values(), key=lambda item: (SEVERITIES.index(str(item["severity"])), str(item["key"])))
    for entry in findings:
        entry["convergent"] = len(entry["lanes"]) > 1  # type: ignore[arg-type]
    counts: dict[str, dict[str, int]] = {}
    for lane in lanes:
        own = [entry for entry in findings if lane.lane in entry["lanes"] and entry["severity"] != "nitpick"]  # type: ignore[operator]
        counts[lane.lane] = {
            "raised": len(own),
            "converged": sum(1 for entry in own if entry["convergent"]),
        }
    by_name = {lane.lane: lane for lane in lanes}
    second_family_ran = "second-family" in by_name
    verify: list[dict[str, object]] = []
    settled: list[dict[str, object]] = []
    for entry in findings:
        if entry["severity"] != "major" or entry["convergent"]:
            continue
        raiser = by_name[entry["lanes"][0]]  # type: ignore[index]
        base = {"finding": entry["key"], "lane": raiser.lane}
        if entry["key"] in reproduced:
            settled.append({**base, "outcome": "accepted: reproduced or its locking assertion failed"})
        elif second_family_ran:
            settled.append({**base, "outcome": "capped at [minor]: the second family ran and did not raise it"})
        elif "verify-major" in demoted:
            settled.append({**base, "outcome": f"capped at [minor]: verifier demoted; low-yield-lane for {raiser.lane}"})
        else:
            target = _other(raiser.provider)
            route = raiser.route if raiser.route in table else "review"
            if target in reachable:
                verify.append({**base, "route": route, "provider": target, "family": table[route][target]})
            elif route == "review" and table["deep-review"].get(raiser.provider) not in {None, raiser.family}:
                verify.append(
                    {**base, "route": "deep-review", "provider": raiser.provider, "family": table["deep-review"][raiser.provider]}
                )
            else:
                settled.append({**base, "outcome": "capped at [minor]: verifier unavailable — single family"})
    rerun: dict[str, list[str]] = {}
    if coverage_required is not None:
        required = list(coverage_required)
        for lane in lanes:
            # The clean-verdict rule binds the lanes that review the whole span.
            if lane.lane in {"independent", "second-family"} and not lane.findings:
                missing = coverage_gaps(required, lane.verification)
                if missing:
                    rerun[lane.lane] = missing
    return {
        "command": "review merge",
        "lanes": counts,
        "findings": findings,
        "verify": verify,
        "settled": settled,
        "coverage_rerun": rerun,
    }


def render_merge(payload: Mapping[str, object]) -> str:
    lines = ["## Review Merge"]
    counts = payload["lanes"]
    assert isinstance(counts, dict)
    lines.append(
        "Lanes: " + ", ".join(f"{name} {stats['raised']} raised/{stats['converged']} converged" for name, stats in counts.items())
    )
    lines.append("")
    lines.append("| Severity | Finding | Lanes | Convergent |")
    lines.append("|---|---|---|---|")
    for entry in payload["findings"]:  # type: ignore[union-attr]
        lines.append(
            f"| {entry['severity']} | {entry['citation'] or entry['key']} | {', '.join(entry['lanes'])} | "
            f"{'yes' if entry['convergent'] else 'no'} |"
        )
    for item in payload["verify"]:  # type: ignore[union-attr]
        lines.append(
            f"Verify: {item['finding']} ({item['lane']}) → bin/aitk model-run {item['route']} "
            f"--provider {item['provider']} --boundary review.verify-major ({item['family']})"
        )
    for item in payload["settled"]:  # type: ignore[union-attr]
        lines.append(f"Settled: {item['finding']} ({item['lane']}) — {item['outcome']}")
    for lane, files in payload["coverage_rerun"].items():  # type: ignore[union-attr]
        lines.append(f"Coverage rerun: {lane} on {', '.join(files)}")
    return "\n".join(lines)


def read_envelopes(arguments: Iterable[str]) -> list[LaneResult]:
    """``[LANE=]PATH`` arguments to lane results."""
    lanes = []
    for index, argument in enumerate(arguments, 1):
        label, _, path = argument.partition("=")
        if not path or label not in LANE_LABELS:
            label, path = "", argument
        try:
            envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReviewPlanError(f"cannot read result {path}: {error}") from error
        lanes.append(lane_result(envelope, label or None, index))
    return lanes


def parent_from_environment(environ: Mapping[str, str] | None = None) -> str | None:
    """`claude` inside Claude Code (CLAUDECODE=1); otherwise the caller says."""
    environ = os.environ if environ is None else environ
    return "claude" if environ.get("CLAUDECODE") == "1" else None
