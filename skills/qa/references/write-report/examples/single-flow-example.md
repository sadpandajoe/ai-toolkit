# Example — Single-Flow QA Report

Based on a real Preset QA verification posted as a Shortcut story comment; story and host identifiers are replaced with placeholders. Use as a tone reference: narrative prose, verdict-first, two related checks labeled inline within one Result block, single video link.

```markdown
## QA Verification — PASS ✅

**Tested on**: https://<ws>.us1a.app-stg.preset.io (staging 6.0.0.6rc1)
**Date**: 2026-02-20
**Tester**: Playwright automation (staging bot account)

### Repro steps followed:
1. Opened "World Bank's Data" dashboard → Explore view for "World's Pop Growth" chart
2. Opened the ad-hoc filter popover and clicked "Time Range"
3. Clicked "Start date" to open the time range picker modal
4. Navigated to the "Custom" tab → "Relative Date/Time" option
5. Selected all text in the numeric spinbutton (value "7") and pressed Backspace
6. Typed "365" character by character with delays between each keystroke

### Result:
**Bug appears fixed.**
- **Test 1 (delete value):** After selecting all and pressing Backspace, the field cleared to empty — it does NOT snap back to "1" as reported in the bug.
- **Test 2 (type 365):** After typing "3", the field shows "3". After typing "6", it shows "36". After typing "5", it shows "365". All digits appear correctly without disappearing/reappearing.

### Evidence:
[sc-NNNNN-relative-date-input-fix.webm](https://media.app.shortcut.com/...)
```

Why this works:
- The repro is one continuous user flow that exercises both bug variants.
- Verdict ("Bug appears fixed") lands in the first line of Result; details follow as labeled bullets.
- No DOM jargon, no pixel measurements, no fix proposals.
- One video covers the whole flow — no per-bullet screenshots needed.
