"""Routing vocabulary: the values, shapes, and errors every other layer speaks.

Owns what a route *is* -- the enumerations a manifest is checked against, the
selector and marker patterns, the error type, the resolved-route record, and the
accessors that read one dispatch boundary's own fields. It depends on nothing else
in the routing subsystem, which is what lets validation, closure derivation, and
transport share one vocabulary instead of three restatements of it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


PROVIDERS = {"codex", "claude"}


REASONING = {"standard", "deep"}


RESPONSIBILITIES = {"implementation", "review", "rca", "operations"}


SANDBOXES = {"read-only", "workspace-write"}


PERMISSION_MODES = {"plan", "acceptEdits", "dontAsk"}


DISALLOWED_TOOLS = {"Write", "Edit", "NotebookEdit"}


ROUTE_NAMES = {
    "implementation",
    "review",
    "deep-review",
    "rca",
    "deep-rca",
    "operations",
    "planning",
}


ROUTE_RESTRICTIONS = {
    "implementation": (
        "Implement only the bounded task contract.",
        "Do not commit, push, publish, or widen scope.",
    ),
    "review": (
        "Perform an independent read-only review.",
        "Do not edit files or mutate external state.",
    ),
    "deep-review": (
        "Perform an independent read-only architecture, security, adversarial, or cold review.",
        "Do not edit files or mutate external state.",
    ),
    "rca": (
        "Synthesize root cause from supplied evidence.",
        "Do not edit files, decide implementation scope, or mutate external state.",
    ),
    "deep-rca": (
        "Synthesize ambiguous, intermittent, history-dependent, or cross-system root cause from supplied evidence.",
        "Do not edit files, decide implementation scope, or mutate external state.",
    ),
    "operations": (
        "Collect read-only evidence, produce deterministic reports, or prepare already-authored API, ticket, or Playwright steps for parent execution.",
        "Do not perform external mutations, execute tests, design tests, diagnose failures, perform RCA, review, decide fixes, or modify product code.",
    ),
    "planning": (
        "Produce a durable plan or investigation artifact for COMPLEX work, decomposed into the smallest implementable slices.",
        "Do not implement, edit files, run tests, review, or self-approve the plan — planning only proposes.",
    ),
}


LENS_DOMAINS = ("code", "plan")


# The output vocabulary each review domain grades in (`rules/severity.md`). This
# exists as data because `lens_domain` used to reach only the worker prompt: a
# code lane could return `[High]` findings and a plan lane could return an
# untagged finding, and both passed the generic envelope check. The domain is
# the contract the aggregator relies on -- code findings dedupe by severity tag
# -- so it is enforced on the result, not just described in the prompt.
CODE_SEVERITIES = ("[major]", "[minor]", "[nitpick]")


PLAN_SEVERITIES = ("[High]", "[Medium]", "[Low]")


DOMAIN_SEVERITIES = {"code": CODE_SEVERITIES, "plan": PLAN_SEVERITIES}


def _severity_pattern(tags: tuple[str, ...]) -> re.Pattern[str]:
    """Compile the anchored form of one domain's severity vocabulary.

    A finding must *open* with its tag. Substring containment accepted anything
    that mentioned a tag anywhere, so a plan finding reading
    `[High] ... compare to a [major] code defect` satisfied a code-domain check
    on the incidental word in its prose, and an untagged finding satisfied it by
    quoting one. The tag is the sort key the aggregator reads off the front of
    the string, so the front is where it has to be.

    A leading list or heading marker and surrounding emphasis are formatting,
    not content, so they may precede the tag. The line drawn is "the tag opens
    the finding", not "the finding is unstyled": rejecting `**[major]** ...`
    would fail a worker that answered correctly and teach the next one to strip
    Markdown rather than to tag.
    """
    alternatives = "|".join(re.escape(tag) for tag in tags)
    return re.compile(
        rf"^[ \t]*(?:[-*+][ \t]+|#{{1,6}}[ \t]+)?[*_]{{0,2}}"
        rf"(?:{alternatives})[*_]{{0,2}}(?=[ \t:]|$)"
    )


DOMAIN_FINDING_PATTERNS = {
    domain: _severity_pattern(tags) for domain, tags in DOMAIN_SEVERITIES.items()
}


# The three-state verdict a plan-domain lens renders (`agents/codex/
# plan-validator.md`, `agents/claude/{plan-review-worker,
# deep-plan-review-worker}.md`): `APPROVE` / `CHANGES REQUIRED` / `REPLAN`.
# A plan lens never emits `rules/gates.md`'s `## Gate` block itself -- that
# contract is explicit that "this contract renders the verdict only; the
# calling workflow owns the gate mapping" -- so the transport checks for this
# vocabulary, not a gate block, on a plan-domain summary. `rules/
# specialist-handoff.md`'s Output Contract does not fix a literal field label
# for this -- the Evidence summary is free prose that "opens with the
# verdict" -- so the pattern must match a bare `APPROVE` line (the minimal
# valid case a fresh reviewer with no findings returns), an optionally
# emphasised `**Verdict:** REPLAN` label, and a verdict followed by trailing
# prose on the same line (`REPLAN -- the invalidated assumption is X`, the
# natural shape of a `REPLAN`/`CHANGES REQUIRED` Evidence summary that also
# states blocking issues or the invalidated assumption per that contract's
# Output section) -- not just a line containing nothing else, and with the
# same leading-marker/emphasis leniency `_severity_pattern` allows.
PLAN_VERDICTS = ("APPROVE", "CHANGES REQUIRED", "REPLAN")


_PLAN_VERDICT_LINE = (
    r"^[ \t]*(?:[-*+][ \t]+|#{1,6}[ \t]+)?"
    r"(?:[*_]{0,2}Verdict:[*_]{0,2}[ \t]*)?"
    r"[*_]{0,2}(%s)[*_]{0,2}(?=[ \t:—-]|$)"
)


PLAN_VERDICT_PATTERN = re.compile(
    _PLAN_VERDICT_LINE % ("?:" + "|".join(PLAN_VERDICTS)), re.MULTILINE
)


# Same anchoring as `PLAN_VERDICT_PATTERN`, but with the verdict word captured
# rather than merely detected -- `_domain_problem` uses this to collect every
# verdict a summary opens a line with, not just whether one exists. A summary
# that renders `APPROVE` on one line and `REPLAN` on another satisfies
# `PLAN_VERDICT_PATTERN.search()` (at least one verdict is present) but is
# self-contradictory: the contract renders exactly one verdict per lens.
PLAN_VERDICT_CAPTURE_PATTERN = re.compile(
    _PLAN_VERDICT_LINE % "|".join(PLAN_VERDICTS), re.MULTILINE
)


# `rules/gates.md`'s Block Format: `## Gate` opens the block a *calling
# workflow* renders after translating a verdict -- "this contract renders the
# verdict only; the calling workflow owns the gate mapping" (`agents/codex/
# plan-validator.md`). A plan lens that renders this heading itself (even
# alongside a valid verdict line, e.g. `APPROVE\n## Gate\nState: BLOCKED`) has
# stepped past its own contract and pre-empted the caller's gate decision.
PLAN_GATE_BLOCK_PATTERN = re.compile(r"^[ \t]*#{1,6}[ \t]*Gate\b", re.MULTILINE)


# The named summary shapes a boundary may require of its worker. A domain fixes
# the vocabulary of the `findings` array; it says nothing about `summary`, which
# most lanes are right to leave as prose. A few lanes are not: the batch PR
# reviewer's summary is the *only* place the PR number, the recommendation, and
# the residual risk travel, and the main thread renders a GitHub comment from
# them. Stated as prose alone, a worker that returned a paragraph passed the
# envelope check and the main thread had nothing to post. The patterns live here
# rather than in the manifest for the same reason `ROUTE_RESTRICTIONS` does:
# JSON is where a lane declares *which* contract it takes, not where the
# contract's grammar is authored.
SUMMARY_FORMS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "pr-batch": (
        (
            "PR: #<N> <title>",
            re.compile(
                r"^[ \t]*[*_]{0,2}PR:[*_]{0,2}[ \t]*#\d+[ \t]+\S.*$",
                re.MULTILINE,
            ),
        ),
        (
            "Recommendation: approve | request-changes | comment",
            re.compile(
                r"^[ \t]*[*_]{0,2}Recommendation:[*_]{0,2}[ \t]*"
                r"[*_]{0,2}(?:approve|request-changes|comment)[*_]{0,2}[ \t]*$",
                re.MULTILINE,
            ),
        ),
        (
            "Residual risk: <one line, or none>",
            re.compile(
                r"^[ \t]*[*_]{0,2}Residual risk:[*_]{0,2}[ \t]*\S.*$",
                re.MULTILINE,
            ),
        ),
        # The batch lane inlines six of the eight code lenses; the classifier it
        # also inlines can still trigger the two it does not carry. Without a
        # slot for that, a worker's only options are to skip the lens silently
        # or to improvise it from the classifier's one-line description, and the
        # main thread never learns which PR needs escalating. `none` is a real
        # answer here, so the value is required rather than the line.
        (
            "Deferred lenses: <names, or none>",
            re.compile(
                r"^[ \t]*[*_]{0,2}Deferred lenses:[*_]{0,2}[ \t]*\S.*$",
                re.MULTILINE,
            ),
        ),
    ),
}


LENS_CATALOG = "skills/review/references/classify-diff.md"


ROUTE_ERROR = "MODEL_ROUTE_INVALID"


UNAVAILABLE_ERROR = "MODEL_ROUTE_UNAVAILABLE"


PROMPT_LIMIT = 1024 * 1024


DEFAULT_TIMEOUT = 1800


PREFLIGHT_TIMEOUT = 15


BLOCKED_EXIT = 4


FAILED_EXIT = 5


VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")


CODEX_SELECTOR = re.compile(r"gpt-[0-9]+\.[0-9]+(?:\.[0-9]+)?-sol")


CLAUDE_SELECTOR = re.compile(r"claude-(opus|fable|sonnet)-[0-9]+(?:-[0-9]+)*")


DISPATCH_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:automatically\s+)?"
    r"(?:ask|use)\b.*\b(?:agents?|subagents?|workers?|reviewers?)\b"
    r"|"
    r"\b(?:spawn(?:s|ed|ing)?|launch(?:es|ed|ing)?|dispatch(?:es|ed|ing)?|"
    r"delegat(?:e|es|ed|ing)|hand(?:s|ed|ing)?\s+off|send(?:s|ing)?|sent|"
    r"fan\s+out)\b.*\b(?:agents?|subagents?|workers?|reviewers?)\b"
    r")",
    re.IGNORECASE,
)


ROUTE_MARKER = re.compile(r"^<!-- aitk-model-route:([a-z0-9]+(?:[.-][a-z0-9]+)*) -->$")


EXEMPT_MARKER = re.compile(r"^<!-- aitk-model-route-exempt:(.+) -->$")


MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


BACKTICK_MARKDOWN_PATH = re.compile(r"`([^`\n]+\.md(?:#[^`\n]+)?)`")


WORKER_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "findings", "verification"],
    "properties": {
        "status": {"enum": ["completed", "blocked", "failed"]},
        "summary": {"type": "string", "minLength": 1},
        "findings": {"type": "array", "items": {"type": "string"}},
        "verification": {"type": "array", "items": {"type": "string"}},
    },
}


class ModelRouteError(ValueError):
    """A model route is invalid or cannot be honored."""

    def __init__(self, message: str, code: str = ROUTE_ERROR) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ResolvedRoute:
    name: str
    boundary: str | None
    required_contracts: tuple[str, ...]
    provider: str
    family: str
    selector: str
    effort: str
    responsibility: str
    restrictions: tuple[str, ...]
    controls: dict[str, object]
    minimum_cli: str
    unscored: bool = False
    # Retired with the reviewer-lens fan-out mechanism; always `None` now. Kept
    # as a field (rather than deleted) because `routing_transport.py`'s worker
    # prompt still emits it as a header line every worker reads.
    lens: str | None = None
    # Which artefact this dispatch grades: `code` for shipped code, `plan` for a
    # written plan, `None` for a lane that grades neither (e.g. implementation).
    # A code lane and a plan lane want different output vocabularies -- severity
    # tags for code, the `APPROVE`/`CHANGES REQUIRED`/`REPLAN` verdict vocabulary
    # for plan (never `rules/gates.md`'s block -- the calling workflow renders
    # that) -- so the mode travels here and `_domain_problem` keys its result
    # check on it.
    lens_domain: str | None = None
    # Which named summary grammar (`SUMMARY_FORMS`) this lane's result is checked
    # against, or `None` for the lanes whose summary is free prose.
    summary_form: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "route": self.name,
            "boundary": self.boundary,
            "required_contracts": self.required_contracts,
            "unscored": self.unscored,
            "lens": self.lens,
            "lens_domain": self.lens_domain,
            "summary_form": self.summary_form,
            "provider": self.provider,
            "family": self.family,
            "selector": self.selector,
            "effort": self.effort,
            "responsibility": self.responsibility,
            "controls": self.controls,
        }


def _load(path: Path) -> object:
    return json.loads(path.read_text())


def _safe_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        return None
    target = root / path
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            return None
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
        resolved_target.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return path if resolved_target.is_file() else None


def _safe_dispatch_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        return None
    target = root / path
    if target.exists():
        return _safe_path(root, value)
    if (
        len(path.parts) >= 3
        and path.parts[0] == "extensions"
        and not (root / "extensions" / path.parts[1]).exists()
    ):
        return path
    return None


def _boundary_contracts(boundary: dict[str, object]) -> tuple[str, ...]:
    """Return the contracts this one dispatch lane declares for itself.

    A document's `## Required Context` is the right channel for what every lane
    in that document needs, and it stays the primary channel. It cannot express
    a *per-lane* dependency, because several documents host more than one
    boundary: `local-review.md` hosts four, `cherry-pick/SKILL.md` three.
    Declaring one lane's contract at document level pushes it into every sibling
    lane's closure, which is exactly the defect that handing every plan reviewer
    all six sibling lenses was. These are per-boundary, so the adversarial lane
    can require the adversarial lens without the three lanes beside it inheriting
    it. This field does not suppress `## Required Context`; the closure seeds are
    the union.
    """
    contracts = boundary.get("contracts")
    return tuple(str(item) for item in contracts) if isinstance(contracts, list) else ()


def _lens_domain(boundary: dict[str, object]) -> str | None:
    """Return which artefact a lane grades -- shipped `code` or a written `plan`.

    Reference docs shared by both domains (architecture review, test review)
    read it to pick their output vocabulary: `code` means the severity tags in
    `rules/code-review.md`, `plan` means the `APPROVE`/`CHANGES REQUIRED`/
    `REPLAN` verdict vocabulary (never `rules/gates.md`'s block, which only the
    calling workflow renders). A lane that grades neither (implementation,
    operations) leaves this `None`.
    """
    domain = boundary.get("lens_domain")
    return domain if isinstance(domain, str) and domain in LENS_DOMAINS else None


def _summary_form(boundary: dict[str, object]) -> str | None:
    """Return the named `SUMMARY_FORMS` grammar this lane requires of its summary."""
    form = boundary.get("summary_form")
    return form if isinstance(form, str) and form in SUMMARY_FORMS else None


def _route_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return {}
    return {
        str(item.get("name")): item
        for item in routes
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
