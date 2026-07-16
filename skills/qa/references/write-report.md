---
tier: Standard
---

# Write QA Report

Canonical rules for QA verification reports posted to **any** shared destination — Shortcut comments, GitHub PR/issue comments, Slack threads, email summaries. Destination-specific mechanics (file upload API, comment endpoint, attachments rail) live in the destination's own reference; this file owns the body content rules.

## When to Use

After running QA validation, fix verification, or PR smoke tests, when results need to land on a ticket, PR, or shared channel that *other people* will read.

Use *instead of* terminal-only output formats (e.g. `test-pr` Step 7 grid, `validate-fix.md` bullet block) when the destination is external.

## Pick the Shape

**Single-flow report** — one bug, one repro path, even with 2–3 related checks within that flow. Use when the whole verification is one continuous user journey.

**Multi-scenario report** — distinct viewports, roles, configs, browsers, feature-flag states, or independent flows. Per-scenario blocks each carry their own steps + result + inline screenshot.

When in doubt, ask: *if a reviewer wanted to re-run just one of these checks, would they need different setup?* If yes → multi-scenario.

Skeletons (load only when drafting):
- [templates/single-flow.md](write-report/templates/single-flow.md)
- [templates/multi-scenario.md](write-report/templates/multi-scenario.md)

Worked examples (load for tone match):
- [examples/single-flow-sc97462.md](write-report/examples/single-flow-sc97462.md) — bug fix verification on one flow
- [examples/multi-scenario-sc101082.md](write-report/examples/multi-scenario-sc101082.md) — viewport-bug verification across four sizes

## Tone — Narrative, Not Technical

Write like a non-engineer QA reviewer. They care whether the thing looks and works right, not how. The reader should be able to confirm the verdict from the narrative alone, without opening the video.

**Do say:**
- "the Apply button stayed visible"
- "the dropdown fit on screen with no overlap"
- "after clicking Save, the row appeared in the list"
- "the chart rendered the same labels as before the change"
- "no console errors fired during the flow" *(only if you actually checked)*

**Don't say:**
- DOM class names or selectors: `ant-picker-dropdown`, `.MuiButton-root`, `data-test="..."`
- Pixel-precise measurements: `bottom=722.66 px`, `top=158`
- CSS property names or computed-style internals
- Fix recommendations: "the height clamp should also bound the outer wrapper" — that's an engineering note, not a QA observation. File it separately.
- Speculation about cause or impact beyond what evidence shows

If you noticed something engineering-relevant during testing, leave it out of the comment and surface it in the in-conversation handoff or a separate engineering note.

## Verdict First, Then Details

Lead the **Result** with a one-sentence verdict (PASS / FAIL / PARTIAL) and the headline finding. Follow-up sentences expand: what worked, what didn't, what you checked. A reviewer should be able to stop reading after the first sentence and still know whether to merge.

## Evidence

- **Video** — record the *full* flow (login → setup → all scenarios). One recording covering everything is more useful than one per scenario.
- **Screenshots** — one per scenario in multi-scenario reports, embedded inline at the verification point. Skip in single-flow reports unless the video is too long to scrub.
- **Naming** — use `<destination-id>-<short-label>.<ext>`, e.g. `sc-101082-1280x720-popover.png`, `pr-3903-readonly-role.png`. Makes attachments self-describing in the destination's file rail.
- **Upload mechanism** — see the destination's reporting reference (e.g. `skills/shortcut/references/report.md` for Shortcut's `/files` endpoint). Capture the returned hosted URL and embed inline.

## Anti-Patterns

- Pasting a tabular pass/fail grid (the `test-pr` Step 7 format) as a Shortcut/GitHub comment — that grid is for terminal output only.
- One mashed-up repro list covering four different viewports, with all evidence dumped at the bottom — use multi-scenario shape instead.
- Engineering postmortem prose ("the issue is that `calculatePopupAlign` doesn't clamp the dropdown wrapper") — keep cause analysis out of the comment; file it separately.
- "Tested on staging" with no URL/build/branch — make the environment line copy-pasteable so a reader can re-run.
