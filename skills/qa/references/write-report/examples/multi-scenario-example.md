# Example — Multi-Scenario QA Report

Based on a real Preset QA verification posted as a Shortcut story comment; story, host and PR identifiers are replaced with placeholders. Use as a tone reference for reports covering several distinct viewports / roles / configs: per-scenario block with its own steps + result + inline screenshot, one full-flow video at the end.

```markdown
## QA Verification — PARTIAL ⚠️

**Tested on**: https://<ws>.us1a.app-stg.preset.io (PR #NNNN branch `fix-time-range-zoom`)
**Date**: 2026-04-28
**Tester**: Playwright automation

### Scenario 1 — small viewport (1280×720), the resolution from the ticket
1. Logged in, opened the Sales Dashboard.
2. Clicked the Time Range filter trigger in the left filter panel.

**Result:** The Apply and Cancel buttons are now mostly visible — labels readable, buttons clickable — but their bottom border still sits a few pixels below the screen edge. Clear improvement on the original report, but the buttons aren't yet fully on screen at this viewport.

![Scenario 1 — 1280×720 popover](https://media.app.shortcut.com/.../scenario-1-1280x720.png)

### Scenario 2 — normal viewport (1280×1000)
1. Resized the window taller, reopened the same filter.

**Result:** Popover fits entirely inside the viewport. Apply and Cancel fully visible. No regression on the happy path.

![Scenario 2 — 1280×1000 popover](https://media.app.shortcut.com/.../scenario-2-1280x1000.png)

### Scenario 3 — tab switching at 1280×720
1. Reopened the popover at 1280×720.
2. Switched to the **Custom** tab, then back to **Basic**.

**Result:** Footer stays pinned in place; tab content swaps cleanly. No content overflow inside the popover.

![Scenario 3 — Custom tab at 1280×720](https://media.app.shortcut.com/.../scenario-3-custom-tab-1280x720.png)

### Scenario 4 — extreme small viewport (1280×500)
1. Resized to a deliberately short viewport, reopened the filter.

**Result:** Same partial-clipping pattern as Scenario 1 — labels visible, button bottom clipped a few pixels.

![Scenario 4 — 1280×500 popover](https://media.app.shortcut.com/.../scenario-4-1280x500.png)

### Full-flow evidence:
[sc-NNNNN-time-range-popover.webm](https://media.app.shortcut.com/...) — login → dashboard → all four scenarios in one recording.
```

Why this works:
- Each viewport is a separate scenario block — a reviewer can re-run just Scenario 4 without scrolling for context.
- Per-scenario inline screenshot lands the visual evidence next to the prose that describes it.
- The verdict on each scenario is a single sentence; no DOM internals or pixel math.
- One full-flow video covers everything end-to-end — easier to scrub than four separate recordings.
- Header verdict is **PARTIAL ⚠️** because Scenarios 1 and 4 fail; Scenarios 2 and 3 pass. The header reflects the worst result.
