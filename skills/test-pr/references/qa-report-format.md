# QA Report Format

The body rules for a QA report posted anywhere other people read it: a
Shortcut comment, a GitHub PR or issue comment, Slack, email. Destination
mechanics live elsewhere (Shortcut: the `shortcut` skill; GitHub:
`gh pr comment <pr> --body-file <path>`). A results table is for the terminal
only; never paste it as an external comment.

## Tone

Write like a non-engineer QA reviewer: whether the thing looks and works
right, not how. A reader should be able to confirm the verdict from the
narrative alone, without opening the video.

- Say: "the Apply button stayed visible", "after clicking Save, the row
  appeared in the list", "no console errors fired during the flow" (only if
  you checked).
- Don't say: selectors or class names, pixel measurements, CSS internals, fix
  recommendations, or speculation about cause. Engineering observations go in
  the conversation handoff, not the comment.
- Make the environment line copy-pasteable (URL plus branch, build or
  version); "tested on staging" alone is not enough.

## Shape

Lead the Result with a one-sentence verdict (PASS, FAIL or PARTIAL) and the
headline finding; a reader who stops there knows whether to merge.

Pick **multi-scenario** when the checks need different setup to re-run
(viewports, roles, configs, browsers, flag states, independent flows);
otherwise **single-flow**, labeling related checks inline in one Result
(`**Test 1 (delete value):** ...`).

```markdown
## QA Verification — PASS ✅ / FAIL ❌ / PARTIAL ⚠️

**Tested on**: <environment URL> (<version/branch/build>)
**Date**: <YYYY-MM-DD>
**Tester**: <who or what ran the test>

### Repro steps followed:            <!-- single-flow -->
1. <what you did, naming the dashboard, chart, page, action>

### Result:
**<One-sentence verdict.>** <2–3 sentences of what you observed.>

### Scenario 1 — <self-describing label, e.g. "Read-only role">   <!-- multi-scenario: repeat per scenario -->
1. <step>

**Result:** <verdict + 1–2 sentences.>

![Scenario 1 — <label>](<hosted PNG URL>)

### Evidence:
[<descriptive-filename.webm>](<hosted media URL>) — <what the recording covers>
```

## Evidence

- One video of the full flow (login, setup, every scenario), not one per
  scenario.
- Multi-scenario reports embed one screenshot per scenario at its
  verification point; single-flow reports skip screenshots unless the video is
  too long to scrub.
- Screenshot names: `<source-id>-scenario-<N>-<label>.png`, e.g.
  `pr-NNNN-scenario-2-readonly-role.png`, with `fail` as the label for a
  failure state, so attachments describe themselves.
- Upload first, then embed the hosted URL the destination returns.
