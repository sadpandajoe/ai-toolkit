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


REASONING = {"light", "standard", "deep"}


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
}


LENS_DOMAINS = ("code", "plan")


# The output vocabulary each lens domain grades in (`rules/severity.md`), and the
# score a plan lane must carry (`rules/scoring.md`). These exist as data because
# `lens_domain` used to reach only the worker prompt: a code lane could return
# `[High]` findings and a plan lane could return no score at all, and both passed
# the generic envelope check. The domain is the contract the aggregator relies on
# -- code findings dedupe by severity tag, plan findings iterate to 8/10 -- so it
# is enforced on the result, not just described in the prompt.
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


# The labelled score line `rules/scoring.md` defines, anchored to its own line.
# An unanchored `\b(?:10|[1-9])/10\b` matched any incidental ratio -- "7/10 of
# the call sites", "covers 3/10 branches" -- so a plan review that never scored
# itself passed as long as it mentioned a fraction somewhere. Emphasis around
# the label is formatting, for the same reason `_severity_pattern` allows it.
#
# So is a heading marker, and here that is not a hypothetical: every plan lens
# prints its score as `### Score: X/10` under a `## <Lens> Review` heading --
# see `skills/plan-review/references/architecture.md`. Accepting only the
# unheaded form rejected the exact template the worker was handed, which teaches
# the next one to deviate from its contract rather than to score. The list form
# rides along for the same reason `_severity_pattern` allows it -- no lens
# template prints it that way today, and a worker that does has still scored
# itself on a line of its own, which is all this check is asked to establish.
PLAN_SCORE_PATTERN = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+|#{1,6}[ \t]+)?[*_]{0,2}Score:[*_]{0,2}[ \t]*"
    r"(?:10|[1-9])[ \t]*/[ \t]*10[ \t]*$",
    re.MULTILINE,
)


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


# The floors `interfaces/model-routing.json` must honour, pinned here for the
# same reason the route table is: `_lens_route_problems` and
# `_lens_floor_problems` used to accept `null` and `{}`, so deleting the
# adversarial route floor or emptying the plan menu floor validated cleanly and
# the protection each exists to give disappeared with one quiet manifest edit.
#
# The two comparisons run in opposite directions, because the two floors fail in
# opposite directions. A *route* floor is breached by widening -- adding `review`
# to the adversarial lens lets the expensive lens run cheap -- so the manifest's
# allowed set must stay within the pinned one. A *menu* floor is breached by
# narrowing -- dropping a lens from a domain makes that lane unreachable -- so
# the manifest's floor must contain the pinned one. Either may still be edited;
# it just costs an edit here, where every boundary's exposure is visible at once.
LENS_ROUTE_FLOORS: dict[str, tuple[str, ...]] = {
    "skills/review/references/adversarial.md": ("deep-review",),
    "skills/plan-review/references/architecture.md": ("deep-review",),
}


LENS_DOMAIN_FLOORS: dict[str, tuple[str, ...]] = {
    "code": (
        "skills/review/references/code-quality.md",
        "skills/review/references/deep-quality.md",
        "skills/review/references/adversarial.md",
        "skills/testing/references/review-tests.md",
        "skills/testing/references/review-testplan.md",
        "skills/plan-review/references/architecture.md",
        "skills/plan-review/references/frontend.md",
        "skills/plan-review/references/backend.md",
    ),
    "plan": (
        "skills/plan-review/references/architecture.md",
        "skills/plan-review/references/implementation.md",
        "skills/plan-review/references/frontend.md",
        "skills/plan-review/references/backend.md",
        "skills/testing/references/review-testplan.md",
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
    lens: str | None = None
    # Which artefact this dispatch grades: `code` for shipped code, `plan` for a
    # written plan, `None` off a fan-out boundary. Several lenses sit in both a
    # code menu and a plan menu -- architecture review and test review most
    # obviously -- and the two want different output: severity tags for code,
    # scores for a plan. A document's Required Context cannot vary by dispatch,
    # so the mode travels here and the dual-use lens keys its output section on
    # it. Without it those lenses had to pick one vocabulary and be wrong at the
    # other boundary.
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


def _lens_menu(boundary: dict[str, object]) -> tuple[str, ...]:
    """Return the boundary's declared reviewer menu, empty when it does not fan out."""
    lenses = boundary.get("lenses")
    return tuple(lenses) if isinstance(lenses, list) else ()


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

    Lenses shared by both domains (architecture review, test review) read it to
    pick their output vocabulary: `code` means the severity tags in
    `rules/code-review.md`, `plan` means the scores in `rules/scoring.md`.

    This used to be spelled `lens_fanout` and doubled as the fan-out flag. The
    two are not the same property. A lane can grade code without fanning out --
    the batch PR reviewer applies its lenses sequentially in one context,
    precisely because a review route cannot dispatch -- and conflating them left
    that lane with `lens_domain=None`, so every result check keyed on the domain
    skipped it and its findings went ungraded. Fan-out is now what it always
    described in the data: the presence of a `lenses` menu (`_lens_menu`).
    """
    domain = boundary.get("lens_domain")
    return domain if isinstance(domain, str) and domain in LENS_DOMAINS else None


def _summary_form(boundary: dict[str, object]) -> str | None:
    """Return the named `SUMMARY_FORMS` grammar this lane requires of its summary."""
    form = boundary.get("summary_form")
    return form if isinstance(form, str) and form in SUMMARY_FORMS else None


def _lens_routes(payload: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return each lens's declared minimum-route set, keyed by lens path."""
    floors = payload.get("lens_routes")
    if not isinstance(floors, dict):
        return {}
    return {
        str(lens): tuple(str(route) for route in routes)
        for lens, routes in floors.items()
        if isinstance(routes, list)
    }


def _lens_floors(payload: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return the lenses every fan-out of a domain must offer, keyed by domain.

    `lens_routes` is a floor on *which route* a lens may run on; this is a floor
    on *which lenses a menu must contain*. Without it, per-boundary menus were
    checked for containment only and completeness was checked across their union,
    so a lens could vanish from one workflow's menu while a sibling menu still
    listed it and the union stayed whole. Narrowing a menu is still allowed --
    that is what scoping a lane means -- but it now costs an edit here, where the
    consequence is visible for every boundary at once, instead of one quiet
    deletion in one boundary's list.
    """
    floors = payload.get("lens_floors")
    if not isinstance(floors, dict):
        return {}
    return {
        str(domain): tuple(str(lens) for lens in lenses)
        for domain, lenses in floors.items()
        if isinstance(lenses, list)
    }


def _route_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return {}
    return {
        str(item.get("name")): item
        for item in routes
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
