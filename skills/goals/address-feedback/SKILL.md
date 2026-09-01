---
name: address-feedback
description: Use when a PR has review comments that need investigation, fixes, replies, or thread handling — covers what address-feedback does today (gather, triage, fix, verify, reply, resolve). Do NOT use for a code review with no PR comments to address (skills/goals/code-review), CI failures unrelated to review feedback (skills/goals/fix-ci), or bug fixing with no PR context (skills/goals/fix-bug).
---

# Address Feedback

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `address-feedback`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Authorization Boundary

Authorization mode: `invocation`. The workflow invocation grants only the
documented default commit, current-branch push, bot reply, and eligible
thread resolution scope; every invariant pause still requires explicit
input.

## Before Starting

Read `rules/gates.md` (six-state gate contract) and the `address-feedback`
entry in `interfaces/contracts.json` (durable runtime: effect
`external_effect`, authorization mode `invocation` with gates
`publish-explicit`/`verification`/`pii-scrub`, phases
prepare→execute→verify→report, resumable via `PROJECT.md`) before
continuing. This skill is the v2 goal-skill entry point for PR review
feedback; it delegates the actual procedure to three existing references
rather than reimplementing them — read all three before continuing, since
this skill's steps assume their Inputs/Procedure/Output shape:

- `skills/feedback/references/gather-triage.md` — gather + triage, with its
  own Complexity Gate against `rules/complexity-gate.md`'s TRIVIAL/STANDARD/
  COMPLEX vocabulary — the same tiers every other goal skill uses.
- `skills/feedback/references/fix-review.md` — apply approved fixes, review.
- `skills/feedback/references/reply-resolve.md` — draft/post replies,
  resolve eligible bot threads, PII scrub.

## Scope

**In scope:** a PR's review comments and threads needing triage, fixes,
verification, replies, or resolution — the full gather → triage → fix →
verify → reply → resolve cycle.

**Out of scope:** reviewing code that has no PR comments yet — that is
`skills/goals/code-review`, which this skill dispatches internally for its
own Review Gate step (see step 3), not a substitute for this skill. Also out
of scope: bug fixes unrelated to review feedback (`skills/goals/fix-bug`)
and CI failures (`skills/goals/fix-ci`).

## Steps

1. Normalize the target: a PR number or URL, plus `--draft`/`--step` flags
   (`--auto` is a legacy no-op alias for the default). Check identity with
   `gh auth status` up front — `reply-resolve.md`'s posting rules need this
   before any reply is drafted, and it should surprise no one that this run
   is posting under a given account.
2. Follow `gather-triage.md`'s procedure in full: the mandatory Reviewer
   Inventory before any triage, its own Complexity Gate (TRIVIAL/STANDARD/
   COMPLEX — do not re-derive a separate tier here), investigation, and the
   Triage Output table. `gather-triage.md` does not write PROJECT.md itself —
   this skill appends the `## Feedback Triage` section it describes before
   any checkpoint + context_reset. Do not restate its dispatch steps here;
   this skill delegates rather than reimplementing them.
3. Follow `fix-review.md`'s procedure in full: fix order, wave batching for
   independent fixes (reuses the existing `feedback.comment-fix-groups`
   dispatch boundary — do not declare a new one), and commit strategy. Its
   Verify Fixes step chains `skills/verification-loop/SKILL.md` against gate
   name `address-feedback-verify` before its Review Gate step — follow that
   skill's RETRY/ESCALATE handling exactly. Its Review Gate step becomes:
   dispatch `skills/goals/code-review` against the changed files, translating
   the former review-status vocabulary's skip/micro-fix exceptions through
   `rules/gates.md`'s Mapping From the Old Mechanisms section — the same
   substitution `skills/goals/code-review/SKILL.md` step 2 already makes.
   `fix-review.md` does not write PROJECT.md itself — this skill appends the
   `## Feedback Round N` entry it describes, including the
   `address-feedback-verify` Gate outcome, before any checkpoint +
   context_reset.
4. Follow `reply-resolve.md`'s procedure in full: draft replies, run the PII
   scrub over every drafted reply, top-level comment, and commit message
   before posting or pushing, then apply its Posting Rules and Resolve
   Threads sections.

   The PII scrub and the invariant pauses below are restated in full here,
   not just cited, because they are the one place a caller reading only this
   skill (not the underlying reference) could accidentally post PII or an
   unauthorized mutation. They apply on every path, tier, and invocation —
   never optional, never abbreviated for a lower complexity tier:

   - Strip customer/workspace names, internal ticket IDs (Shortcut/Linear/
     Jira), internal URLs, reporter identity, and credentials from every
     reply, comment, and commit message before it is posted or pushed.
   - `--draft` was passed — never post or resolve.
   - A human-thread reply needs the user's own wording.
   - The next git step would amend, rebase, or force-push.
   - The push target is ambiguous (not the current PR branch, or tracks an
     unexpected remote).
   - Verification failed, or the fix is not yet visible on the PR branch.
   - The next action would approve or request changes on the PR.

   Everything else — new commits on the current PR branch, pushes, bot-thread
   replies, eligible bot-thread resolution once the fix is verified — is the
   default unattended action; `--step` adds a pre-post/pre-resolve
   confirmation on top of the invariant pauses above.
5. Once all three phases complete (or the run stops cleanly at an invariant
   pause above): record the `## Feedback Posted` PROJECT.md entry and emit
   `reply-resolve.md`'s terminal Summary Contract for the user. A clean stop
   at an invariant pause is not a failure — resume continues from the
   PROJECT.md hard-gate entries already written by steps 2–3.

## Output

The Reviewer Inventory + Triage table, the Review Gate result, and
`reply-resolve.md`'s terminal `## Address-Feedback Complete` summary — or an
earlier invariant-pause stop with the reason and the PROJECT.md state needed
to resume.

## Notes

- This skill is now the live dispatch target for natural-language "address PR
  feedback" / "fix review comments" requests — Claude Code's own skill
  selection prefers this narrower description over the general
  `skills/workflows` router, same as `fix-bug`. The
  `interfaces/workflows.json` `address-feedback` entry now points its
  `reference` directly at this file; the standalone
  `skills/workflows/references/address-feedback.md` (`aitk/checkpoint.py`'s
  `_contract()` never read its content) has been deleted, along with its
  now-orphaned `workflows.feedback-fix-wave` dispatch boundary — the marker
  it matched only ever lived in that deleted file.
- Declares no dispatch boundaries of its own — `feedback.comment-fix-groups`,
  already registered in `interfaces/model-routing.json`, covers the fix-wave
  batching this skill's procedure reaches; the Review Gate step dispatches
  `skills/goals/code-review`, which likewise declares no boundaries of its
  own.
- Shares its name with the `address-feedback` entry in
  `interfaces/contracts.json` and `interfaces/workflows.json` by design —
  this skill is the goal-skill counterpart to that legacy workflow, not a
  new contract. The durable-runtime shape it follows (phases, authorization
  gates, resumability) is the one already declared there; this skill does
  not need — and must not add — a second contract entry, since
  `aitk/conformance.py`'s `validate_contracts` resolves contract names
  against `interfaces/workflows.json`, not `interfaces/skills.json`.
