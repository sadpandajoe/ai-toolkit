# Initialize Session

Use the repository-root [PROJECT_TEMPLATE.md](../../../PROJECT_TEMPLATE.md) when a new durable state file is required.

> **When**: Beginning any work session.
> **Produces**: Loaded PROJECT.md context and session entry.

## Effect Boundary

Effect: `local_mutation`.

This command is the only supported entrypoint for resuming work after `context_reset`.
It restores workflow state from PROJECT.md rather than relying on chat memory.

## Steps

0. **Model/Advisor Preflight**

   Before loading state or resuming any workflow, validate any explicitly configured worker/advisor profile. An invalid profile can fail only after dispatch, where recovery is expensive.

   - Identify the active main model from the environment.
   - If an advisor/secondary model is configured (settings, env, or the user's request), verify the model ID exists and the pairing is one the API accepts.
<!-- aitk-model-route-exempt:preflight-before-later-dispatch -->
   - If the user requested an alias, ask the provider adapter to resolve it to a concrete available profile **before** dispatching anything that spawns subagents with it.
   - On any unknown ID or incompatible pairing, emit this hard gate and stop — do not resume a checkpoint or dispatch a workflow on a config that will fail mid-run:

     ```markdown
     ## Model Preflight Failed
     Active model: [id]
     Problem: [unknown model id | incompatible advisor pairing: <a> + <b>]
     Fix: [exact setting change or valid model id]
     ```

   - Clean config → continue silently. This step produces no output when healthy.

1. **Find PROJECT.md**

   Search these locations in order (stop at first match):
   1. Current working directory: `PROJECT.md`
   2. Git repo root: `$(git rev-parse --show-toplevel)/PROJECT.md`
   3. Additional working directories from the environment

   The file may be a real file or a **symlink** — both are valid. Read it normally either way.

   - If found: Read completely
   - If not found anywhere: create one from `PROJECT_TEMPLATE.md`, announce the creation in the session summary, and continue (it's local-only and trivially deletable); `--ask` restores the prompt

   **If PROJECT.md is a symlink, resolve it before writing.** Some provider file tools refuse writes through symlinks. Run `readlink -f <path-to-PROJECT.md>` to get the real target, then edit that resolved path when adding the session entry or any later updates. Reads through the symlink are fine. This same rule applies to PLAN.md and any other toolkit-managed file in the working directory.

2. **Check for Continuation Checkpoint**

   If PROJECT.md contains a `## Continuation Checkpoint` section:
   - Read the checkpoint state:
     - top-level workflow
     - phase
     - **active plan** (PLAN.md or none)
     - resume target
     - completed items
     - key workflow state
   - Add a session entry noting this is a continuation:
     ```markdown
     ### [Timestamp] - Session Resumed
     - Branch: [current branch]
     - Resuming from: [checkpoint timestamp]
     - Command: [top-level workflow from checkpoint]
     - Phase: [saved phase]
     - Active plan: [PLAN.md or none]
     - Resume target: [saved item or iteration]
     ```
   - **For STANDARD top-level commands, emit a Remaining Phase Plan block** showing what's left and where clears will fire. Derive it from the command's STANDARD happy path minus the phases already completed (use the saved Phase + Current Status `Done:` list). Example:

     ```markdown
     ### Remaining Phase Plan
     Completed: plan ✓ → plan-review ✓
     Ahead: implement-slice → [clear] → review-code → [clear] → feature-validation → summary
     Next clear after: `## Slice 1 Complete` written to PROJECT.md.
     ```

     This makes the cadence visible after every resume, so the user knows when the next clear fires without needing to recall the original phase plan. Skip this block for MODERATE/TRIVIAL resumes — they don't have planned phase boundaries.
   - **Defer loading PLAN.md.** Read PROJECT.md alone for orientation. Only load PLAN.md when the next phase actually requires it (entering review iterations or starting an implementation slice). This keeps context lean for resumes that are just status checks or fix-it work.
   - **Automatically resume the saved top-level workflow** from the checkpoint. Do not prompt the user.
   - The resumed command loads its own rules, skills, and supporting files on demand.
   - After the resume succeeds, clear or replace the stale checkpoint so the same state is not resumed twice unintentionally.

3. **Normal Session** (no checkpoint)

   Add session entry:
   ```markdown
   ### [Timestamp] - Session Start
   - Branch: [current branch]
   - Status: [summary from Current Status]
   - Goal: [ask user]
   ```

   ```
   "Session initialized. What would you like to work on?"
   ```

   Suggest relevant commands based on context:
   - New feature or planned refactor → `create-feature`
   - Bug report, broken behavior, or RCA-first debugging → `fix-bug`
   - Updating an existing test suite → `update-tests`
   - Creating the first meaningful tests → `create-tests`
   - Validating a story, PR, or environment without fixing it → `run-test-plan`
   - Open PR with pending CI or fresh review comments → `watch-pr`
   - Cherry-picking → `/cherry-pick`
   - Ready to open a PR → `create-pr`
   - Capturing a pattern or reviewing memories → `reflect`
   - Completed phases cluttering PROJECT.md → [`archive-project-file`](../../archive-project-file/SKILL.md)
   - Want to see all available commands → `custom-skills-info`

4. **Recommend Archiving When Useful**

   Run these checks against PROJECT.md and the repo root:

   **Concrete signals** (high-confidence — surface the suggestion explicitly):
   - PROJECT.md contains one or more `Completed: <date> — <feature>` entries (workflow finished, content not yet archived)
   - A stale `PLAN.md` exists at the repo root with no Continuation Checkpoint pointing to it (workflow finished but the plan file still sits there)

   **Soft signals** (lower-confidence — mention only if a concrete signal already fired):
   - Long Development Log sections for work already complete
   - Resolved blockers still in active sections
   - Active work becoming hard to find

   If any **concrete signal** fires, surface the nudge prominently — before suggesting next commands — using this format:

   ```
   📦 Archive suggestion: [N] completed phase(s) detected, [stale PLAN.md present | no stale plan].
       Run archive-project-file to clean up before the next major phase.
   ```

   If only soft signals fire, mention briefly at the end of the session entry.

   Always recommend, never auto-run. `archive-project-file` is the only deletion path; workflows do not auto-delete.
