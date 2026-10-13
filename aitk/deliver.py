"""`bin/aitk deliver`: commit, push and open (or reuse) a draft PR once the gates hold.

The workflows used to copy the push and PR procedure into their prose
(create-pr's identity, lookup and creation steps, and each owner's delivery
list). This module is that procedure, so the model runs one command instead of
re-typing it:

1. **Preconditions** (nothing changes when one fails, status `refused`): a
   routing snapshot; review PASS with a reviewer record and a verification run
   that exited 0 at `STRONG`, both in the current phase (`gate_blockers`); the
   working tree, state files left out, equal to the tree the run and the review
   saw; a branch that is not detached and not `main`, `master` or the default
   branch; `--title` and `--body-file` unless `--no-pr`; and, for `--ready`,
   the user's `AITK_PR_READY=1`.
2. **Push target**: the upstream's remote; else `branch.<name>.pushRemote`,
   `remote.pushDefault`, `origin`. A renamed upstream or push ref, a push
   remote that differs from the upstream remote, or no candidate is a hold
   (status `held`, nothing committed or pushed).
3. **Commit** the paths that differ from `HEAD` in the verified tree, by name
   (never `-A`), then check the commit's tree is the verified tree.
4. **Push** `HEAD:refs/heads/<branch>` (with `-u` when there is no upstream),
   only when the remote is behind, then check the head identity again.
5. **PR** (skipped with `--no-pr`): base identity from `gh repo view`, the
   fork rules, the paginated open-PR lookup for this head, then reuse
   (`PR Exists`) or `gh pr create --draft` (`--ready` drops `--draft`). A
   failed or unknown creation is reconciled with one more lookup.
6. **Record** `## PR Created` (or `## Delivered` for `--no-pr`) with a
   `Delivered as:` line naming the verification command in PROJECT.md, once.

There are no reservations or operation ids: every step reads the state it
would change (the commit, the remote ref, the open PRs) first, so a re-run
after a crash finishes the delivery instead of repeating it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess

from .project_state import (
    ProjectStateError,
    append_section,
    gate_blockers,
    git_toplevel,
    parse_project_state,
    working_tree_sha,
)


PROTECTED_BRANCHES = ("main", "master")
GITHUB_URL = re.compile(
    r"^(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$"
)


class DeliverStop(Exception):
    """Delivery ends here; `status` is `refused`, `held` or `failed`."""

    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass
class DeliverOptions:
    cwd: Path
    project_file: Path
    workflow: str | None = None
    phase: str | None = None
    title: str | None = None
    body_file: Path | None = None
    message: str | None = None
    base: str | None = None
    no_pr: bool = False
    ready: bool = False
    env: dict[str, str] | None = None


@dataclass
class DeliverResult:
    status: str
    reason: str = ""
    branch: str | None = None
    remote: str | None = None
    commit: str | None = None
    committed: bool = False
    pushed: bool = False
    pr: dict[str, object] | None = None
    verification: dict[str, object] | None = None
    recorded: bool = False
    steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "command": "deliver",
            "status": self.status,
            "reason": self.reason,
            "branch": self.branch,
            "remote": self.remote,
            "commit": self.commit,
            "committed": self.committed,
            "pushed": self.pushed,
            "pr": self.pr,
            "verification": self.verification,
            "recorded": self.recorded,
            "steps": list(self.steps),
        }

    @property
    def exit_code(self) -> int:
        return {"delivered": 0, "held": 3}.get(self.status, 1)


def _run(
    argv: list[str], cwd: Path, env: dict[str, str] | None, *, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            capture_output=True,
            input=stdin,
            stdin=None if stdin is not None else subprocess.DEVNULL,
            check=False,
            env=env,
        )
    except OSError as error:
        return subprocess.CompletedProcess(argv, 127, "", str(error))


def _git(repo: Path, env: dict[str, str] | None, *arguments: str) -> subprocess.CompletedProcess[str]:
    return _run(["git", *arguments], repo, env)


def _git_value(repo: Path, env: dict[str, str] | None, *arguments: str) -> str:
    result = _git(repo, env, *arguments)
    return result.stdout.strip() if result.returncode == 0 else ""


def _tail(text: str, lines: int = 5) -> str:
    return " | ".join(line.strip() for line in text.strip().splitlines()[-lines:] if line.strip())


# Head identity -------------------------------------------------------------


@dataclass(frozen=True)
class HeadRefs:
    branch: str
    up_remote: str
    up_ref: str
    push_remote: str
    push_ref: str


def head_refs(repo: Path, env: dict[str, str] | None = None) -> HeadRefs:
    """The branch and what git would push it to; STOP on a detached HEAD."""
    branch = _git_value(repo, env, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise DeliverStop("refused", "STOP: detached HEAD")
    line = _git_value(
        repo,
        env,
        "for-each-ref",
        "--format=%(upstream:remotename)|%(upstream:remoteref)|%(push:remotename)|%(push:remoteref)",
        f"refs/heads/{branch}",
    )
    up_remote, up_ref, push_remote, push_ref = (line.split("|") + ["", "", "", ""])[:4]
    return HeadRefs(branch, up_remote, up_ref, push_remote, push_ref)


def check_tracking(refs: HeadRefs) -> None:
    """The push-shape STOPs from create-pr's identity block, for a branch with an upstream."""
    if refs.up_ref != f"refs/heads/{refs.branch}":
        raise DeliverStop(
            "held",
            f"STOP: no upstream or renamed upstream ref ({refs.up_remote or 'none'} {refs.up_ref or 'none'})",
        )
    if refs.push_remote and refs.push_remote != refs.up_remote:
        raise DeliverStop(
            "held",
            f"STOP: push remote {refs.push_remote} differs from upstream remote {refs.up_remote}",
        )
    if refs.push_ref and refs.push_ref != f"refs/heads/{refs.branch}":
        raise DeliverStop("held", f"STOP: renamed push ref {refs.push_ref}")


def head_identity(repo: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    """Resolve the remote, ref and sha a PR would open from, or STOP.

    The same six STOP cases as create-pr's identity block: detached HEAD, no
    upstream or a renamed upstream ref, a push remote that differs from the
    upstream remote, a renamed push ref, no remote-tracking ref, and a remote
    sha that is not HEAD.
    """
    refs = head_refs(repo, env)
    check_tracking(refs)
    remote_sha = _git_value(repo, env, "rev-parse", "--verify", "--quiet", f"{refs.branch}@{{upstream}}")
    if not remote_sha:
        raise DeliverStop("held", f"STOP: no remote-tracking ref for {refs.branch}")
    head = _git_value(repo, env, "rev-parse", "HEAD")
    if remote_sha != head:
        raise DeliverStop(
            "held", f"STOP: {refs.up_remote}/{refs.branch} is at {remote_sha}, HEAD differs"
        )
    return {"remote": refs.up_remote, "ref": f"refs/heads/{refs.branch}", "sha": remote_sha}


def normalize_head_repo(url: str) -> str:
    """`owner/repo` in lowercase for a github.com URL; empty for anything else."""
    match = GITHUB_URL.match(url.strip())
    return match.group(1).lower() if match else ""


def head_repo(repo: Path, remote: str, env: dict[str, str] | None = None) -> str:
    """The push URL of `remote` (the fetch URL when none is set), normalized."""
    return normalize_head_repo(_git_value(repo, env, "remote", "get-url", "--push", remote))


def push_target(repo: Path, refs: HeadRefs, env: dict[str, str] | None = None) -> str:
    """Where this branch is pushed: the upstream's remote, else pushRemote, pushDefault, origin."""
    if refs.up_remote:
        check_tracking(refs)
        return refs.up_remote
    remotes = set(_git_value(repo, env, "remote").split())
    for candidate in (
        _git_value(repo, env, "config", "--get", f"branch.{refs.branch}.pushRemote"),
        _git_value(repo, env, "config", "--get", "remote.pushDefault"),
    ):
        if candidate:
            if candidate not in remotes:
                raise DeliverStop("held", f"ambiguous push target: remote {candidate} is not configured")
            return candidate
    if "origin" in remotes:
        return "origin"
    raise DeliverStop(
        "held", "ambiguous push target: no upstream, pushRemote, pushDefault or origin"
    )


# Open-PR lookup -------------------------------------------------------------


def _json_values(text: str) -> list[object]:
    """Decode concatenated JSON values (what `gh api --paginate` prints, one array per page)."""
    decoder = json.JSONDecoder()
    values: list[object] = []
    index = 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            return values
        value, index = decoder.raw_decode(text, index)
        values.append(value)


def lookup_open_prs(
    repo: Path,
    base_repo: str,
    head_owner: str,
    branch: str,
    head_repository: str,
    env: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Every open PR for exactly this head, across every page.

    `head=<owner>:<branch>` narrows the query, and each row is kept only when
    its head ref is this branch and its head repository is `head_repository`
    (case-insensitive), so a same-named branch on a fork never matches. A gh
    failure, an unparseable page or a row with a missing field is
    indeterminate: DeliverStop("held").
    """
    if not all((branch, head_repository, base_repo, head_owner)):
        raise DeliverStop("held", "indeterminate lookup: the branch, head or base repository is unknown")
    result = _run(
        [
            "gh", "api", "--paginate", "-X", "GET", f"repos/{base_repo}/pulls",
            "-f", "state=open", "-f", "per_page=100", "-f", f"head={head_owner}:{branch}",
        ],
        repo,
        env,
    )
    if result.returncode != 0:
        raise DeliverStop("held", f"indeterminate lookup: gh exited {result.returncode} ({_tail(result.stderr)})")
    try:
        pages = _json_values(result.stdout)
    except ValueError as error:
        raise DeliverStop("held", f"indeterminate lookup: a page is not JSON ({error})") from error
    rows: list[dict[str, object]] = []
    for page in pages:
        if not isinstance(page, list):
            raise DeliverStop("held", "indeterminate lookup: a page is not a list of pull requests")
        for pull in page:
            if not isinstance(pull, dict):
                raise DeliverStop("held", "indeterminate lookup: a row is not an object")
            head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
            head_repo_value = head.get("repo") if isinstance(head.get("repo"), dict) else {}
            full_name = str((head_repo_value or {}).get("full_name") or "").lower()
            if head.get("ref") != branch or full_name != head_repository:
                continue
            base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
            row = {
                "number": pull.get("number"),
                "draft": pull.get("draft"),
                "base": base.get("ref"),
                "url": pull.get("html_url"),
            }
            if (
                not isinstance(row["number"], int)
                or not isinstance(row["draft"], bool)
                or not row["base"]
                or not row["url"]
            ):
                raise DeliverStop("held", "indeterminate lookup: a matching row is missing a field")
            rows.append(row)
    return rows


def choose_pr(
    rows: list[dict[str, object]], base: str, *, explicit_base: bool, chained: bool, head: str
) -> dict[str, object] | None:
    """create-pr's row rules: reuse one on this base, refuse ambiguity, else create (None)."""
    on_base = [row for row in rows if row["base"] == base]
    if len(on_base) == 1:
        return on_base[0]
    if len(on_base) > 1:
        numbers = ", ".join(f"#{row['number']}" for row in on_base)
        raise DeliverStop("held", f"PR conflict: open PRs {numbers} for {head} target {base}; nothing created")
    if rows and (chained or not explicit_base):
        other = rows[0]
        raise DeliverStop(
            "held",
            f"PR conflict: open PR #{other['number']} for {head} targets {other['base']}; "
            f"this run resolved {base}; nothing created",
        )
    return None


# The delivery ---------------------------------------------------------------


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() not in {"", "0", "false", "no", "off"}


def _preconditions(options: DeliverOptions, result: DeliverResult) -> tuple[Path, dict[str, object], str]:
    environment = options.env if options.env is not None else os.environ
    if options.ready and not _truthy(environment.get("AITK_PR_READY")):
        raise DeliverStop(
            "refused",
            "a ready (non-draft) PR needs the user's explicit request in words; without it deliver "
            "opens a draft. Stop and ask the user, who alone can override it.",
        )
    if options.no_pr and options.ready:
        raise DeliverStop("refused", "--ready and --no-pr contradict each other")
    repo = git_toplevel(options.cwd)
    if repo is None:
        raise DeliverStop("refused", "not inside a git repository")
    path = options.project_file
    try:
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        snapshot = parse_project_state(content)
    except (OSError, ProjectStateError) as error:
        raise DeliverStop("refused", f"the routing snapshot in {path} is unreadable ({error})") from error
    if snapshot is None:
        raise DeliverStop(
            "refused", f"no routing snapshot in {path}: run the workflow that owns this change first"
        )
    if options.workflow and snapshot["workflow"] != options.workflow:
        raise DeliverStop(
            "refused",
            f"PROJECT.md records workflow {snapshot['workflow']}, not {options.workflow}",
        )
    blockers = gate_blockers(snapshot, ["review", "verification"])
    gates = snapshot["gates"]
    run = gates.get("verification", {}).get("run") if isinstance(gates.get("verification"), dict) else None
    if run is not None and run.get("exit_code") != 0:
        blockers.append(f"the verification run `{run['command']}` exited {run['exit_code']}")
    if blockers:
        raise DeliverStop("refused", "gates not met: " + "; ".join(blockers))
    assert run is not None
    result.verification = {
        "command": run["command"],
        "exit_code": run["exit_code"],
        "strength": run["strength"],
        "tree": run["tree"],
    }
    if run["strength"] != "STRONG":
        raise DeliverStop(
            "refused",
            f"verification is {run['strength']}; deliver needs STRONG (the acceptance command "
            "run through `bin/aitk verify --run`)",
        )
    tree = working_tree_sha(repo)
    if tree is None or tree != run["tree"]:
        raise DeliverStop(
            "refused",
            "the working tree changed after the verification run; run `bin/aitk verify --run` "
            "again (and review the change) before delivering",
        )
    review = gates["review"]["review"]
    if review["tree"] != tree:
        raise DeliverStop(
            "refused", "the working tree changed after the review; review the change again before delivering"
        )
    if not options.no_pr and (not options.title or options.body_file is None):
        raise DeliverStop("refused", "a PR needs --title and --body-file (or pass --no-pr)")
    if options.body_file is not None and not options.body_file.is_file():
        raise DeliverStop("refused", f"--body-file {options.body_file} is not a file")
    return repo, snapshot, tree


def _changed_paths(repo: Path, tree: str, env: dict[str, str] | None) -> list[str]:
    if _git_value(repo, env, "rev-parse", "--verify", "--quiet", "HEAD"):
        listing = _git(repo, env, "diff", "--name-only", "--no-renames", "-z", "HEAD", tree)
    else:
        listing = _git(repo, env, "ls-tree", "-r", "--name-only", "-z", tree)
    if listing.returncode != 0:
        raise DeliverStop("failed", f"could not list the changed paths ({_tail(listing.stderr)})")
    return [item for item in listing.stdout.split("\0") if item]


def _commit(repo: Path, tree: str, message: str | None, env: dict[str, str] | None, result: DeliverResult) -> None:
    paths = _changed_paths(repo, tree, env)
    if paths:
        if not message:
            raise DeliverStop("refused", "there are changes to commit; pass --message (or --title)")
        added = _git(repo, env, "add", "-A", "--", *paths)
        if added.returncode != 0:
            raise DeliverStop("failed", f"git add failed ({_tail(added.stderr)})")
        committed = _git(repo, env, "commit", "--quiet", "-m", message, "--", *paths)
        if committed.returncode != 0:
            raise DeliverStop("failed", f"git commit failed ({_tail(committed.stderr or committed.stdout)})")
        result.committed = True
        result.steps.append(f"committed {len(paths)} path(s)")
    head_tree = _git_value(repo, env, "rev-parse", "HEAD^{tree}")
    if head_tree != tree:
        raise DeliverStop(
            "failed",
            f"HEAD's tree {head_tree or 'none'} is not the verified tree {tree}; nothing was pushed",
        )
    result.commit = _git_value(repo, env, "rev-parse", "HEAD")


def _push(repo: Path, refs: HeadRefs, remote: str, env: dict[str, str] | None, result: DeliverResult) -> None:
    head = result.commit or _git_value(repo, env, "rev-parse", "HEAD")
    if refs.up_remote:
        remote_sha = _git_value(repo, env, "rev-parse", "--verify", "--quiet", f"{refs.branch}@{{upstream}}")
        if remote_sha == head:
            result.steps.append(f"{remote}/{refs.branch} already at {head[:12]}")
            return
        pushed = _git(repo, env, "push", "--quiet", remote, f"HEAD:refs/heads/{refs.branch}")
    else:
        pushed = _git(repo, env, "push", "--quiet", "-u", remote, f"HEAD:refs/heads/{refs.branch}")
    if pushed.returncode != 0:
        raise DeliverStop(
            "held", f"push to {remote} was refused (ambiguous push target): {_tail(pushed.stderr)}"
        )
    result.pushed = True
    result.steps.append(f"pushed {head[:12]} to {remote}/{refs.branch}")
    identity = head_identity(repo, env)
    if identity["sha"] != head:
        raise DeliverStop("held", f"STOP: {remote}/{refs.branch} does not show HEAD after the push")


def _repo_view(repo: Path, env: dict[str, str] | None) -> dict[str, object]:
    view = _run(["gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef,isFork"], repo, env)
    if view.returncode != 0:
        raise DeliverStop("held", f"precondition: gh repo view failed ({_tail(view.stderr)})")
    try:
        payload = json.loads(view.stdout)
        base_repo = str(payload["nameWithOwner"]).lower()
        default = str((payload.get("defaultBranchRef") or {}).get("name") or "")
        is_fork = bool(payload.get("isFork"))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise DeliverStop("held", f"precondition: gh repo view returned no repository ({error})") from error
    if "/" not in base_repo:
        raise DeliverStop("held", "precondition: gh repo view returned no owner/repo")
    return {"base_repo": base_repo, "default": default, "is_fork": is_fork}


def _create(
    repo: Path,
    options: DeliverOptions,
    base: str,
    head: str,
    env: dict[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    argv = ["gh", "pr", "create"]
    if not options.ready:
        argv.append("--draft")
    argv += ["--base", base, "--head", head, "--title", str(options.title), "--body-file", str(options.body_file)]
    return _run(argv, repo, env)


def _record(path: Path, result: DeliverResult, options: DeliverOptions, base: str | None, head: str | None) -> None:
    verification = result.verification or {}
    verified = (
        f"verified by `{verification.get('command')}` (exit {verification.get('exit_code')}, "
        f"{verification.get('strength')})"
    )
    commit = (result.commit or "")[:12]
    if result.pr is None:
        section = "\n".join(
            [
                "## Delivered",
                f"Commit: {commit} on {result.remote}/{result.branch}",
                f"Delivered as: pushed — awaiting PR request (--no-pr); {verified}",
            ]
        )
        result.recorded = append_section(path, section, unless=f"Commit: {commit} on {result.remote}/{result.branch}")
        return
    pr = result.pr
    draft = "yes" if pr["draft"] else "no"
    kind = "draft PR" if pr["draft"] else "ready PR"
    section = "\n".join(
        [
            "## PR Created",
            f"PR #{pr['number']}: {options.title or ''}".rstrip(),
            f"URL: {pr['url']}",
            f"Base: {base} ← {head}",
            f"Draft: {draft}",
            f"Existing: {'yes' if pr['existing'] else 'no'}",
            f"Delivered as: {kind} #{pr['number']} (commit {commit}); {verified}",
        ]
    )
    result.recorded = append_section(path, section, unless=f"URL: {pr['url']}")


def deliver(options: DeliverOptions) -> DeliverResult:
    """Run the delivery; never raises DeliverStop (it becomes the result's status)."""
    result = DeliverResult(status="delivered")
    env = options.env
    base: str | None = None
    head_label: str | None = None
    try:
        repo, snapshot, tree = _preconditions(options, result)
        refs = head_refs(repo, env)
        result.branch = refs.branch
        if refs.branch in PROTECTED_BRANCHES:
            raise DeliverStop("refused", f"never deliver from {refs.branch}")
        remote = push_target(repo, refs, env)
        result.remote = remote
        remote_head = _git_value(repo, env, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD")
        if remote_head and remote_head.split("/", 1)[-1] == refs.branch:
            raise DeliverStop("refused", f"never deliver from the default branch {refs.branch}")
        view: dict[str, object] | None = None
        head_repository = ""
        if not options.no_pr:
            head_repository = head_repo(repo, remote, env)
            if not head_repository:
                raise DeliverStop("held", f"STOP: the push URL of {remote} is not a github.com owner/repo")
            view = _repo_view(repo, env)
            if view["default"] and view["default"] == refs.branch:
                raise DeliverStop("refused", f"never deliver from the default branch {refs.branch}")
            chained = options.workflow is not None
            if chained and (head_repository != view["base_repo"] or view["is_fork"]):
                raise DeliverStop(
                    "held",
                    f"precondition: the head repository {head_repository} is not the base "
                    f"repository {view['base_repo']} (or it is a fork); a workflow opens PRs "
                    "only on its own repository",
                )
        _commit(repo, tree, options.message or options.title, env, result)
        _push(repo, refs, remote, env, result)
        if options.no_pr:
            result.reason = "pushed; no PR (--no-pr)"
            _record(options.project_file, result, options, None, None)
            return result
        assert view is not None
        base = options.base or str(view["default"])
        if not base:
            raise DeliverStop("held", "precondition: no --base and the repository has no default branch")
        same_repo = head_repository == view["base_repo"]
        head_owner = (str(view["base_repo"]) if same_repo else head_repository).split("/", 1)[0]
        head_label = f"{head_owner}:{refs.branch}"
        rows = lookup_open_prs(repo, str(view["base_repo"]), head_owner, refs.branch, head_repository, env)
        existing = choose_pr(
            rows, base, explicit_base=options.base is not None, chained=options.workflow is not None,
            head=head_label,
        )
        if existing is not None:
            result.pr = {**existing, "existing": True}
            result.reason = "PR Exists"
        else:
            created = _create(repo, options, base, head_label, env)
            if created.returncode != 0:
                # Unknown outcome: the PR may exist anyway. One lookup decides.
                rows = lookup_open_prs(
                    repo, str(view["base_repo"]), head_owner, refs.branch, head_repository, env
                )
                existing = choose_pr(
                    rows, base, explicit_base=options.base is not None,
                    chained=options.workflow is not None, head=head_label,
                )
                if existing is None:
                    raise DeliverStop(
                        "failed",
                        f"gh pr create failed ({_tail(created.stderr)}) and no PR exists; "
                        "re-run the same `bin/aitk deliver` command",
                    )
                result.pr = {**existing, "existing": True}
                result.reason = "PR Exists (reconciled after a failed create)"
            else:
                url = created.stdout.strip().splitlines()[-1].strip() if created.stdout.strip() else ""
                number = re.search(r"/pull/(\d+)", url)
                if number is None:
                    rows = lookup_open_prs(
                        repo, str(view["base_repo"]), head_owner, refs.branch, head_repository, env
                    )
                    found = choose_pr(rows, base, explicit_base=True, chained=False, head=head_label)
                    if found is None:
                        raise DeliverStop("failed", f"gh pr create printed no PR URL ({_tail(created.stdout)})")
                    url, pr_number = str(found["url"]), int(found["number"])
                else:
                    pr_number = int(number.group(1))
                result.pr = {
                    "number": pr_number,
                    "url": url,
                    "draft": not options.ready,
                    "base": base,
                    "existing": False,
                }
                result.reason = "PR Created"
        _record(options.project_file, result, options, base, head_label)
        return result
    except DeliverStop as stop:
        result.status = stop.status
        result.reason = stop.reason
        return result


def render(result: DeliverResult) -> str:
    """The markdown block the workflow pastes."""
    lines: list[str] = []
    verification = result.verification or {}
    if result.status == "delivered" and result.pr is not None:
        pr = result.pr
        lines.append("## PR Exists" if pr.get("existing") else "## PR Created")
        lines.append(f"PR #{pr['number']}: {pr['url']}")
        lines.append(f"Base: {pr.get('base')} ← {result.branch}")
        lines.append(f"Draft: {'yes' if pr['draft'] else 'no'}")
        lines.append(f"Existing: {'yes' if pr.get('existing') else 'no'}")
    elif result.status == "delivered":
        lines.append("## Delivered")
        lines.append(f"Commit: {(result.commit or '')[:12]} pushed to {result.remote}/{result.branch}")
        lines.append("Record: pushed — awaiting PR request (--no-pr)")
    elif result.status == "held":
        lines.append("## PR Not Opened")
        lines.append(f"Reason: {result.reason}")
        if result.pushed or result.committed:
            lines.append(f"Record: pushed — awaiting PR request ({result.reason})")
        else:
            lines.append("Record: nothing committed or pushed")
    else:
        lines.append(f"## Delivery {result.status.capitalize()}")
        lines.append(f"Reason: {result.reason}")
        if result.committed or result.pushed:
            lines.append(f"Done before stopping: {'; '.join(result.steps)}")
        else:
            lines.append("Nothing was committed, pushed or opened.")
    if verification:
        lines.append(
            f"Verification: `{verification.get('command')}` exit {verification.get('exit_code')} "
            f"({verification.get('strength')})"
        )
    return "\n".join(lines)
