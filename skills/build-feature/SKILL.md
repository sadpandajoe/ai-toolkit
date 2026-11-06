---
name: build-feature
description: Build a feature or other planned non-bug change end to end — scope it, plan when the work calls for it, implement with tests, and open a draft PR. Use for requests like "add X" or "support Y" and for feature tickets (sc-12345, GitHub issues). Do NOT use for bug fixes (use fix-bug), failing CI (use fix-ci), or questions about how something works.
---

# Build Feature

## Scope

Fetch a Shortcut reference with the `shortcut` skill. A ticket with clear
acceptance criteria is already the brief.

Write a short brief first when the request is loose, spans several product
surfaces, or has unclear acceptance criteria. It always lists **non-goals**:
without them reviewers suggest additions that were left out on purpose.

A product or UX trade-off the brief can't settle goes to the user once, with
options.

## When to plan in a file

Plan inline by default. Write `PLAN.md` (local notes, never committed) when
any of these hold:
- the work spans sessions;
- it needs several phases;
- the approach needs the user's approval: several plausible designs, a risky
  change (as the `review` skill defines it), or a new architectural pattern.

Put questions for the user under **Decisions needed** at the end of the plan.
Have a risky plan checked cold before coding, given the brief and the plan but
not your reasoning: `<toolkit-root>/skills/review/scripts/second-opinion.py
--file PLAN.md --brief "<the request>"` asks the other model family.

Cosmetic changes (theme, copy, spacing, a button variant) need no plan, however
many files they touch.

## Splitting

Split a unit before implementing it when it would:
- change more than 10 files or 500 lines;
- be a horizontal layer (all models, then all APIs, then all UI);
- leave the system broken if deployed alone;
- be too big to review in one sitting.

When evidence breaks the plan, tell the user rather than quietly re-planning.

A repeated mechanical change (a rename, a codemod) is one transformation
applied in waves, not phases. Verify and review the first wave fully, and later
identical waves by their checks.

Phases on one branch share one draft PR. Keep the whole change in a single PR
when a migration cannot ship ahead of its consumer or a contract must flip
atomically.

## Finish

- A risky change (as the `review` skill defines it) gets a second opinion from
  the `review` skill. Multi-phase work gets one more over the whole branch at
  the end.
- A fresh git worktree shares `.git` but not dependencies, build outputs or
  `.env` files. Install from the lockfile and copy the `.env*` files from the
  main checkout. Ask before copying one named for production.
- User-visible changes carry before/after evidence per the toolkit rules;
  capture it with the `test-pr` skill, starting with **before** while the app
  still runs the unchanged code.
- Open the draft PR with the `create-pr` skill. For work that spans sessions,
  keep notes per the `handoff` skill.
