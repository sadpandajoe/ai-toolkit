# Changelog

## 0.4.0 (unreleased)

The workflow engine is retired: the toolkit is facts and boundaries.
Current models plan, verify and escalate on their own, so procedure, gates and
routing that compensated for weaker models are removed, and what remains has
to pass the admission rule in `AGENTS.md`. Remove a v0.3 install first with
`git checkout 0.3.0 && ./install.sh --uninstall` (README, Migrating).

- Removed: the `aitk` package and `bin/aitk` (project-state snapshots,
  complexity/size/shape classification, PASS/RETRY/ESCALATE gates, `deliver`,
  `verify --run`, review-lane planning, model routing and the route markers,
  metrics, evals, the installer and its ledger), `interfaces/`, `evals/`,
  `config/`, the generated agents and `agents/specialists/`, every rule but
  `rules/universal.md`, and the `workflows`, `planning`, `pm`, `reporting`,
  `testing`, `verification-loop`, `implement-change`, `preflight`,
  `reflection`, `debug`, `qa`, `feedback`, `pr-watch` and
  `archive-project-file` skills.
- Skills are one per outcome and trigger on their descriptions: `fix-bug`,
  `build-feature`, `fix-ci`, `review`, `address-feedback`, `create-pr`,
  `watch-pr`, `test-pr` and `handoff` are new; `cherry-pick`, `shortcut`,
  `superset-local`, `preset-rbac-setup`, `pgm` and `agent-setup-maintainer`
  keep their facts and lose their procedure. About 55k words of skills,
  rules and agents become about 19k.
- Three hand-written agents, each a Claude `.md` and a Codex `.toml` with one
  body: `reviewer`, `ci-investigator` and `qa-runner`.
- `rules/universal.md` holds only the boundaries: authorization, the hooks,
  before/after evidence for UI changes, PII, and precedence. There is no
  review-before-PR gate; a PR opens as a draft when the change is believed
  correct.
- The git guard runs standalone from `hooks/lib/` and now also blocks a
  non-draft `gh pr create` without `AITK_PR_READY=1`, the one check the
  retired review gate held that still applies. The review-gate, plan-drift
  and observation-reminder hooks are gone.
- `skills/review/scripts/second-opinion.py` asks the other model family for a
  read-only review of a diff, or with `--file` of a plan, and pins the models.
- Install is the plugin on both CLIs; `install.sh` only links the Codex
  agents, which a Codex plugin cannot ship. `scripts/check.py` replaces
  `bin/aitk check`, and `scripts/show-cost.py` replaces `bin/aitk cost`.
- `PROJECT_TEMPLATE.md` moves to `skills/handoff/project-template.md`; the
  host table moves to `skills/test-pr/references/preset-environments.md`;
  `scripts/superset-local/up.sh` moves to `skills/superset-local/scripts/`.

## 0.3.0 — 2026-10-30 (the last engine release, tag `0.3.0`)

- A pre-push check that runs past its budget now warns and the push proceeds;
  a real lint or test failure still blocks. Each check runs in its own process
  group with stdin closed, and the group (descendants included) is ended when
  the check ends. Only a check the watchdog itself stopped after its deadline,
  or that exited 0 after the watchdog's TERM, counts as overdue; any other
  exit status or signal, and a pre-commit run that already printed a failed
  hook, blocks. Check output is replayed when the check ends.
- The git guard, the review gate and the pre-push hook read commands through
  one shared tokenizer (`aitk/hooks/shell_tokens.py`). It follows every
  command the shell would run: separators and fused operator runs (`;(`,
  `)&&`), subshells, `sh -c` and `eval` payloads, command substitutions,
  function bodies, wrappers (`env`, `sudo`, `timeout`, `xargs`, `flock`, `uv
  run`, `find -exec`, ...), dashed entry points (`git-push`), git and gh in
  any letter case, and `git -C` and `cd` directories. Text that git itself
  runs (an inline alias, `rebase -x`, `bisect run`, `submodule foreach`,
  `for-each-repo`) is not resolved: when it mentions a push or a gated PR
  operation, the command blocks as unreadable. A push or PR creation whose
  directory the hook cannot read literally (a variable, `--git-dir`, a glob)
  blocks instead of being checked against the wrong repository; `cd
  "$(git rev-parse --show-toplevel)"` is followed. Each hook stops itself
  before its Claude Code timeout, because a PreToolUse hook that times out
  does not block the tool call: the git guard and the review gate then
  block, and the pre-push hook reads the command as unreadable. The scan is a tripwire, not a
  sandbox; its known limits and accepted over-blocks are listed in the
  `git_guard`, `review_gate` and `shell_tokens` module docstrings.
- `bin/aitk review plan` calls the second-family lane on CORE impact only at
  40 or more changed lines or on a CORE path: auth, payment or data integrity,
  and in the toolkit repo also its `TOOLKIT_SENSITIVE` paths (routing manifest,
  agents, build, installer, deliver, review plan, hooks, plugin manifests).
  Either end of a rename counts, lockfiles and generated files included. The
  line count leaves out lockfiles and generated files by name only, never by
  a content header the diff author writes. The
  plan discloses when a smaller CORE diff runs without the lane. PR plans read
  the paginated REST file list, so a rename's origin reaches the CORE check.
  Toolkit identity also counts committed HEAD or base evidence (or the PR's
  base commit), so deleting a sentinel file in the diff cannot turn it off.
- `bin/aitk project-state gate --exception` enforces what it can measure: a
  micro-fix must be one counted file of ten changed lines or fewer by numstat
  (lockfiles and generated files excluded by name), and either exception is
  refused on a CORE path (either end of a rename, whatever the file's name or
  header says), on a diff with no counted file, and in a repository with no
  base to measure against. Zero-logic is the caller's declaration; the gate
  does not read the change. `review plan` reports `exception_available` from
  the same rule and reviews a TRIVIAL diff on a CORE path as STANDARD.
- `AITK_PR_READY`, `SKIP_PR_GATE` and `SKIP_PRECHECK` count only from the
  environment the session started with, and `no` and `off` are off everywhere
  (the git guard, the review gate and the pre-push hook share one rule). The
  git guard blocks a command that assigns, appends to or exports one, and it
  fails closed on override names, including without Python; the review gate
  and pre-push hook no longer read a command-prefix override.
- `bin/aitk deliver` can never open a ready PR: `--ready` and its
  `AITK_PR_READY` read are gone, and it always runs `gh pr create --draft`.
  Taking a PR out of draft is the user running `gh pr ready` with
  `AITK_PR_READY=1` set in the session environment, which the git guard
  already enforces. A pre-existing non-draft PR is still reused as it is.
- `fix-review` now makes a new commit on the current PR branch for every fix
  by default; fixup, autosquash and force-push are an opt-in history rewrite,
  used only when the user authorizes it for the round.

- `bin/aitk model-run --experiment reviewer-runs-test --test-command <cmd>`
  lets the independent reviewer run one test from an allowlist given on the
  command line, in a disposable copy of its worktree, for the D11
  measurement. Claude enforces the allowlist with `dontAsk` allow rules and
  its Bash sandbox; on Codex the allowlist is an instruction and the
  `workspace-write` sandbox rooted at the copy, with no network, is the
  boundary. Every `model-run` envelope gains an `experiment` field, `null`
  without the flag.

- Workflow state is one block: `bin/aitk checkpoint`, `aitk/checkpoint.py`,
  `aitk/artifact_lock.py`, `rules/durable-workflows.md` and the checkpoint
  machine-block template are gone. `bin/aitk project-state` writes the only
  machine block in `PROJECT.md`, under the file lock that used to live in
  `artifact_lock.py`, and `deliver` and the PR gate read its gates.
  `interfaces/contracts.json` is version 3: each workflow keeps its effect,
  authorization, state, resume flag and verification strength, and
  `list --details` no longer prints phases. An existing `aitk-checkpoint:v1`
  block in a `PROJECT.md` is now ordinary text and can be deleted.
- The validators are gone: `aitk/conformance.py` and `aitk/interfaces.py` are
  deleted, `bin/aitk doctor` checks links, skill descriptions, the routing
  manifest, personal paths and secret output, and a malformed manifest fails
  when it is loaded. `interfaces/support.json` becomes README's Support
  section, and `interfaces/providers.json` drops `document`.
- The route table lives only in `interfaces/model-routing.json`: the pinned
  copy, the per-field schema, `count`, `explicit_only`,
  `policy.automatic_max` and `fallback` are gone. A route's model must be a
  catalog family, and each route's write controls and tool box stay pinned in
  `aitk/routing_policy.py`.
- `model-run` checks the provider CLI against the route's version floor and
  no longer scans `--help` output for flags.

- Workflows deliver through `bin/aitk deliver`: `create-feature`, `fix-bug`,
  `fix-ci`, `tests` and `create-pr` no longer carry their own push and PR
  procedure. `bin/aitk route` is gone; the router is the model reading
  `bin/aitk list --details --json`. The `metrics-emit` skill is retired
  (`bin/aitk metrics emit` fills the event). The lane-yield table in
  `docs/ARCHITECTURE.md` is generated from `aitk/review_plan.py`. A routed
  selector without an exact price now warns in the test suite instead of
  failing it.

- `review-code --adversarial` replaces the `review-code-adversarial` workflow:
  the same primary and second-vote adversarial lanes, `--allow-degraded`, and
  the adversarial rating, run from `review-code`.

- One `tests` workflow replaces `create-tests` and `update-tests`: it improves
  an existing suite, or switches to writing the first suite when there is no
  real one (`--step` stops at the switch). Delivery runs `bin/aitk deliver
  --workflow tests`. The testing skill's create and update references are
  folded into it.

- Plugin preview: the repository root is also a Claude Code plugin
  (`.claude-plugin/plugin.json`, served with the Codex plugin by the one-plugin
  marketplace in `.claude-plugin/marketplace.json`), and the Codex plugin now
  ships the PGM skill and declares `hooks/hooks.json`. Hook commands resolve
  the toolkit as `${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}`; `bin/aitk install`
  still writes the absolute toolkit root into Claude Code settings, so
  installed commands do not change. The plugin-only `hooks/session-start.sh`
  loads the always-on rules and the provider binding pointer, and warns when a
  `bin/aitk install` is still in place. `./install.sh` stays the supported
  install until `scripts/plugin-proof.sh` passes on both providers
  (docs/MIGRATION.md).

- The statusline effort label shows the live session effort (`/effort`,
  `--effort`) instead of the `effortLevel` saved in `settings.json`, which made
  it read the saved default no matter what the session ran. It is omitted when
  the model reports no effort, and `xhigh` is colored like `high`.

- Model selectors move to the newest releases: the Codex workhorse is GPT-6
  Sol (was GPT-5.6 Sol, which Codex now migrates) and the Claude judgment tier
  is Opus 5.5 (was Opus 5), so Codex-lane reviews and implementation run on
  GPT-6 Sol and Claude-lane reviews on Opus 5.5. The provider CLI floors rise
  to the versions that introduced them (Codex 0.155.0 for GPT-6 Sol, Claude
  Code 2.1.280 for Opus 5.5); older CLIs now fail preflight. Pricing adds both
  at their published rates (GPT-6 Sol $2/$10, Opus 5.5 $4/$20 with 0.05x cache
  reads) and keeps the older entries so past session records still price. A
  test now requires every routed selector to have an exact pricing key so a
  promotion cannot silently fall back to its predecessor's rate. The pricing
  tables do not model GPT-6's long-context surcharge (prompts over 272K input
  tokens), which applies to every Codex family.

- Commits and pushes to the current feature branch no longer wait for
  confirmation: once verification and review pass, workflows (`create-feature`,
  `create-tests`, `update-tests`, `rules/implementation.md`) commit and push
  without asking. After the push, `create-feature`, `fix-bug`, `fix-ci`,
  `create-tests`, and `update-tests` open a draft PR through `create-pr
  --draft` (`--no-pr` opts out; phases sharing a branch share one draft PR,
  and `--deliver-per-phase` means a separate branch and draft PR per phase,
  otherwise a no-op alias; `create-tests` and `update-tests` open the draft PR through
  `create-pr`'s own contract, and their contracts do not declare a
  `published_pr` effect). Marking a PR ready for review, reviewers, merging, and a non-draft
  PR need the user's explicit words. Amend, rebase, force-push, and
  protected-branch pushes still need explicit authorization. A PR requested for a change that never entered a
  workflow (a chore) runs `review-code` first to record the review gate, then
  opens the PR, instead of asking the user to override or review;
  `review-code` now ensures a routing snapshot, `create-pr` checks the gate,
  and the hook's block message says to run the review. Multi-phase deliveries read `pushed — awaiting PR
  request` where they read `prepared — awaiting publish authorization`.
- `hooks/require-review-gate.sh` (PreToolUse, Bash) blocks `gh pr create`
  unless the `PROJECT.md` routing snapshot records the `review` gate as `PASS`
  for the current phase, using the same `gate_blockers` check `checkpoint
  reserve` applies. A missing `PROJECT.md` or snapshot blocks too, since that
  is the shape of a change that never entered a workflow; a pending
  `published_pr` reservation also counts, so a multi-phase run that advanced
  after `reserve` can still open its PR. `SKIP_PR_GATE=1` is the user's
  override; the block message tells the agent to ask instead. Registered in
  `hooks/hooks.json` and `install-hooks.sh`. Known limits: the snapshot has no
  branch or tree binding, so a review PASS left by an earlier workflow in the
  same `PROJECT.md` still satisfies it, and command matching is static
  (conditional or subshell `cd`, `gh api`, and aliases are not followed; a
  single-quoted `$(...)` literal blocks in an ungated repo; a linked worktree
  does not see the main checkout's `PROJECT.md`). It follows `cd`, `env -C`
  and `env -S`, comments, line continuations, `bash -c`, `eval`, and quoted
  substitutions, checks every PR creation in a request, and blocks a command
  it cannot parse when that command also changes directory.
- `rules/universal.md` gains an always-on entry rule: a request to add or
  change behavior loads the `workflows` skill before the first edit, on intent,
  so the workflow no longer depends on the session choosing to enter it.
- The Stop hooks (`hooks/observation-reminder.sh`, `hooks/check-plan-drift.sh`)
  return their nudge as JSON with a `systemMessage` on stdout, which the
  runtime shows to the user; they used to write to stderr and exit 0, which
  Claude Code sends only to the debug log, so the reminder was never seen.
  `tests/test_stop_hooks.py` covers both thresholds and the fail-open path.
- The finding-verifier yield threshold is the rate the rule states: `aitk
  lane-yield` demotes `verify-major` when fewer than three in ten of the
  single-source majors it verified in the window came back `CONFIRMED`, and a
  window that verified nothing is not judged; it no longer counts three
  confirmations as an absolute floor.
- `skills/metrics-emit` defines the `review.lanes` counts lane-yield reads:
  `converged` (findings the other lane also raised), `confirmed` and `refuted`
  (verifier verdicts), and the delta lane's `not_fixed` and `introduced`.
- `watch-pr` records `complexity` in the current vocabulary: `trivial` for a
  watch that dispatched no fix, otherwise the dispatched fix's `standard` or
  `complex`.

- Gate runtime: only `RETRY` charges the attempt budget; `--editorial` records
  a wording-only fix without charging; `USER_DECISION` and `BLOCKED` never
  charge; `ESCALATE` climbs a per-unit ladder (three steps, then
  `USER_DECISION`) and resets the budget for the next owner; `RECLASSIFY`
  resets counters. Snapshots gain an `escalations` map; older snapshots read
  as empty. The `## Routing Snapshot` heading in `PROJECT_TEMPLATE.md` is
  reused instead of duplicated.
- Verification strength (`STRONG` / `PARTIAL` / `WEAK`) maps to gate outcomes
  in `rules/gates.md`; auto-commit and push in `fix-bug`, `fix-ci`, and
  `watch-pr` require `STRONG`; `--gate-strict` removes the `WEAK` downstream
  carve-out.
- COMPLEX and CORE-impact reviews run a second cold lane on the other model
  family (`review.second-family`, `review.pr-second-family`) merged by
  convergence; elsewhere single-source `[major]` findings are verified by a
  fresh lane on the other model family (`review.verify-major`,
  `agents/specialists/finding-verifier.md`) before they block; security-sensitive, `--deep`, and adversarial reviews are
  `BLOCKED (degraded)` without a cross-provider lane unless `--allow-degraded`.
- Plan validation cases are one list: every decomposition, every COMPLEX plan,
  and a STANDARD plan at `LOW` classification confidence.
- The independent reviewer contract inlines the tests, frontend, and backend
  checklists; the plan validator inlines the implementation and test-plan
  checklists; the unused plan lens floor is gone. Batch PR reviews report
  deep-quality among deferred lenses.
- Phase model: per-unit reviews measure a phase base and the branch base is
  reserved for a new integrated review that gates `## Feature Complete` and
  `## Bug Fix Complete` on MULTI_PHASE and BATCHED work; `## Phase Complete`
  carries a roadmap check whose `no` is `RECLASSIFY` plus one decomposition
  revalidation; one commit or PR per phase is the default delivery with a
  recorded single-PR opt-out; the phase-size guard has numbers (10 files, 500
  lines) and the horizontal-layer and one-sitting checks; size L leans
  MULTI_PHASE and the runtime refuses L or XL `none` without a reason.
- Pricing table covers the Codex families: Astra at its published API rate and
  Sol at its promotional rate with the standard rate returning after
  2026-11-21, timestamp-aware like the Sonnet promotion, so `show-cost` no
  longer reports Codex runs as unpriced.
- Fable is the Claude planner: the `planning` route and the `aitk-planner`
  agent run Fable at `high` for COMPLEX decompositions and phase plans, while
  Opus keeps the Claude side of `review` and `rca` so Fable stays a
  distinct escalation rung above them. A COMPLEX plan now spends Fable quota
  from a Claude parent; STANDARD work is still planned inline by Sonnet.
- GPT-6 Astra is the Codex deep tier: `deep-review` and `deep-rca` run on
  Astra at `xhigh` (Codex CLI 0.153.0 or newer) while Sol keeps the workhorse
  routes, mirroring Fable over Sonnet and Opus. Deep lenses now follow the
  other-provider preference, so from a Claude parent they run on Astra and
  spend no Claude quota; Fable is the second vote, the escalation, and the
  single-provider verifier fallback.
- Pre-switch review controls: a clean verdict on a STANDARD diff above 200
  lines or 5 files calls the second family after the fact; a `[major]` the
  parent wants to reject goes to the verifier and `CONFIRMED` overrides the
  rejection; the reviewer can report a missing classifier flag and the parent
  reclassifies and runs the lens; yield is recorded per lane and four
  thresholds with defined consequences demote low-yield lanes
  (`rules/code-review.md`, Yield Thresholds).
- Review depth follows the tier (`rules/code-review.md`, Review Shape by Tier):
  TRIVIAL gets one lane and no delta, BATCHED reviews the transformation on the
  first wave and verifies later waves, MULTI_PHASE reviews per phase on the
  phase base; create-feature has a feature complexity signal table with an
  explicit cosmetic row; an XL decomposition is validated by both families
  (`planning.validate-second-family`).
- Delivery matches the durable contract: per-phase commits are prepared and
  pushed only under `publish-explicit` (authorization at intake with
  `--deliver-per-phase` or at the first phase boundary), each as a
  `published_pr` record keyed `phase:<name>`; the create-feature and fix-bug
  phase graphs gain the review → plan / implement edges phased work needs; the
  phase tree SHA is recorded with `project-state phase --sha` (required for
  `done`) and is the next phase's review base; `Delivered as` has a
  `prepared — awaiting publish authorization` value.
- Review quality: the reviewer greps for the pattern a bug fix replaced, cites
  the fixing hunk and asks the resolved-state question in delta mode, always
  sees the whole recorded span, and the diff is reclassified before the delta
  pass; RCA confidence has a calibration table; `fix-bug` has its complexity
  signal table back; a `PASS` gate is never a stop signal; a shallow
  `CHANGES_REQUIRED` re-runs the validator at `deep-review` instead of
  revising the plan; on a single-provider machine the finding verifier runs on
  `deep-review` or the finding stays capped at `[minor]`.
- Restored `USER_DECISION` heuristics, the stop-on-no-logs rule in `fix-ci`,
  the per-unit `## Phase Complete` hard gate, and TRIVIAL-plus-CORE review
  escalation; `review-plan` and `fix-ci` record snapshot gates.

- Replaced the control plane: the parent session runs the cheap workhorse
  (Sonnet on Claude, Sol on Codex), classifies complexity (TRIVIAL / STANDARD /
  COMPLEX), size (S / M / L / XL), and execution shape, and drives goal
  workflows through `PASS / RETRY / ESCALATE / RECLASSIFY / USER_DECISION /
  BLOCKED` gates with a one-retry budget (`rules/gates.md`).
- Added the `PROJECT.md` v2 routing snapshot and `aitk project-state`
  (`init`, `show`, `set`, `gate`, `advance`, `phases`, `phase`) so resume and
  escalation read durable data; legacy `MODERATE` reads as `STANDARD`.
- Rewrote model routing: Sonnet implements, a new read-only `planning` route
  (Opus) plans only COMPLEX work, `review`/`rca` are independent specialists
  preferring the other provider, Fable stays a read-only deep advisor. Catalog
  moved to the Claude 5 family (Opus 5, Sonnet 5, Fable 5.1) and GPT-5.6 Sol.
  (The `planning` route's Opus selector here was superseded by the "Fable is
  the Claude planner" entry above.)
- Added the native worker roster (`agents/claude/*.md`, `agents/codex/*.toml`,
  installed to `~/.claude/agents` and `$CODEX_HOME/agents`) and the
  provider-neutral specialist contracts in `agents/specialists/` that the route
  runner inlines for cross-provider review, RCA, and plan validation.
- Simplified review to one independent review, validate-before-fix, one delta
  pass, and at most two conditional deep lenses; retired review ensembles,
  verifier diversity, the resolved-state audit, and `aitk review-ensemble`.
- Replaced the 8/10 multi-reviewer plan loop and cold read with one
  independent validator returning `APPROVE / CHANGES_REQUIRED / REPLAN`, plus
  size-aware decomposition and just-in-time phase planning.
- Added the shared `verification-loop` skill, the RCA evidence gate with an
  independent RCA specialist, the observation queue in `reflection`, richer
  metrics fields, and an `evals/` corpus with a deterministic runner.
- Retired `action-gate`, `rules/review-gate.md`, `rules/stop-rules.md`,
  `rules/scoring.md`, and the manual context-clear dependency; fresh workers
  are the phase boundary and auto-compaction protects the parent.
- Two records, one truth is enforced: the snapshot keeps a per-gate record
  (`gates`, one `{status, phase, units}` entry per gate) and `aitk checkpoint
  reserve` refuses an effect the contract gates on `verification` or `review`
  unless that gate is `PASS` in the snapshot of the same `PROJECT.md`, recorded
  in the current phase, with no reasoning unit left open; `advance` clears the
  phase-scoped gates; no snapshot or an unreadable one fails closed. Both
  runtimes take one lock per artifact path (`aitk/artifact_lock.py`), so a
  gate record and a reservation never overwrite each other and the gate check
  is atomic with the reservation. `advance` requires a recorded
  `PASS` (`PENDING` no longer advances); re-running `init` with a different
  classification is refused instead of silently keeping the old one;
  `--same-failure` escalates at once when the reason already exhausted a
  previous owner.
- Phase graphs carry the edges the prose already used: verification can
  reopen the diagnosis (`fix-bug`, `fix-ci`) or the plan (`create-feature`),
  the review workflows loop from `verify` back to `review` for the delta pass,
  and `fix-ci` can end after diagnosis when every failure is pre-existing.
  `interfaces/contracts.json` is back to one compact line per contract.
- Learning loop closed: `reflect observations` is routed and runs inside
  `complete-project` before the memory scan; `start` and a new Stop hook
  (`hooks/observation-reminder.sh`) suggest it at 10 unreviewed lines; the new
  `aitk lane-yield` command applies the review-lane yield thresholds to
  `.ai-toolkit/metrics.jsonl` and prints demotions; `review.lanes` gains the
  delta lane's `not_fixed` and `introduced` counts.
- `verify` reports the same strength tiers as `rules/gates.md` (what ran, not
  file coverage; a failure is never a strength). `aitk-reviewer` is documented
  as both the second-family lane and the same-provider fallback and discloses
  which role it ran in. Feedback, PR posting, reporting templates, CI fix
  table, test workflows, batch review, and watch-pr use the v2 vocabulary
  (tiers, gate statuses, lanes, handoff instead of context clears).
- Retired the unused `workstreams` skill.

## 0.2.0 — 2026-07-21

- Added canonical, fail-closed model and effort routes for Codex and Claude
  workers, including high-effort workhorse defaults, xhigh deep review/RCA,
  Sonnet operations-only constraints, and future-proof selector promotion.
- Added `aitk model-route` and `aitk model-run`, dispatch-boundary validation,
  provider CLI preflight, structured worker results, and no-downgrade behavior.
- Removed generated Claude slash-command aliases in favor of natural-language
  routing and the public `$workflows` and `$pgm` Agent Skills.
- Preserved upgrade-safe cleanup of toolkit-owned legacy command links while
  leaving unrelated personal commands untouched.
- Made CI portable across macOS path aliases and Python 3.11–3.14, enabled PEP
  517 build isolation, and eliminated duplicate push runs for PR branches.

## 0.1.0 — 2026-07-15

- Moved all daily workflow procedures from commands into a canonical provider-neutral workflow skill.
- Added the deterministic `aitk` build, route, list, doctor, and conformance interfaces.
- Added safe idempotent Claude/Codex guidance and skill installation while preserving unrelated user configuration.
- Added a validated Codex plugin manifest, Agent Skills metadata, and provider-neutral lifecycle hooks.
- Added routing, safety, installer, build, portability, resume, and behavioral contract tests.
- Standardized local metrics under `.ai-toolkit/metrics.jsonl` with legacy-read migration.
- Removed personal paths, unsafe secret diagnostics, `eval` retries, destructive RBAC defaults, and provider primitives from shared workflows.
- Migrated the optional PGM reports to a manifest-backed Agent Skill with generated aliases, opt-in routing, and reversible installation.
- Added SHA-pinned CI that initially ran the same complete conformance gate as
  local development on Python 3.11 and 3.14; the later expansion to Python
  3.11–3.14 is recorded below.
- Added strict v2 workflow contracts and a deterministic checkpoint CLI with
  phase, generation, reservation, reconciliation, and replay validation.
- Added a mode-0600 ownership ledger with atomic install/upgrade/uninstall,
  one-level rollback, moved-checkout migration, hostile-ledger refusal, and
  crash-boundary restoration.
- Classified every skill as public router, public direct, or internal support;
  source-linked installs expose only the public surface.
- Added PGM configuration preflight and timestamp-aware promotional pricing;
  missing/invalid historical timestamps remain unpriced.
- Expanded CI to the macOS/Ubuntu and Python 3.11-3.14 matrix with untracked
  generated-adapter rejection and isolated wheel smoke testing.
