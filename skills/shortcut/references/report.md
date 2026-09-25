---
tier: Standard
---

# Shortcut Report

Post structured reports (QA results, fix summaries, test findings) to Shortcut stories with evidence and metadata updates.

## When to Use

- After QA validation, test execution, or bug triage produces results that belong on a Shortcut story
- When a fix has been verified and the story needs a closing summary
- When evidence (screenshots, videos, logs) needs to be attached and referenced in a comment

## Prerequisites

- `$SHORTCUT_API_TOKEN` must be set
- Story ID must be known (numeric ID or `sc-NNNNN` format)
- Follow [fetch.md](fetch.md) patterns for API access and retry logic

Read `rules/shortcut-api.md` for the global Shortcut routing constraints.

## Core Steps

1. **Resolve the story**

   Extract the numeric ID from `sc-NNNNN`, URL, or raw number.
   Fetch the story to confirm it exists and get current state:
   ```bash
   shortcut_call curl -s "https://api.app.shortcut.com/api/v3/stories/<id>" -H "Shortcut-Token: $SHORTCUT_API_TOKEN"
   ```

2. **Upload evidence** (if any)

   Upload files before posting the comment so the comment can reference the hosted URLs.
   Use the `/files` endpoint (not `/stories/<id>/files`).

   **For inline images in the comment body** (screenshots embedded via markdown), upload *without* `story_id`. The returned `url` is workspace-scoped and renders in markdown, but the file does not appear in the story's Files sidebar — keeps the story clean when the image is only meaningful in context of the comment:
   ```bash
   shortcut_call curl -s -X POST "https://api.app.shortcut.com/api/v3/files" \
     -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
     -F "file0=@<path>"
   ```

   **For evidence that should be attached to the story** (videos, logs, anything reviewers should find via the Files panel), include `story_id`:
   ```bash
   shortcut_call curl -s -X POST "https://api.app.shortcut.com/api/v3/files" \
     -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
     -F "file0=@<path>" \
     -F "story_id=<id>"
   ```

   Do not pass `description` as a form field — it causes a validation error.
   Capture the returned `url` for embedding in the comment (`![alt](<url>)` for images).
   Name video files descriptively: `sc-<id>-<what-was-tested>.webm`.

3. **Post the report comment**

   Use the appropriate template from the Report Templates section below.
   ```bash
   shortcut_call curl -s -X POST "https://api.app.shortcut.com/api/v3/stories/<id>/comments" \
     -H "Content-Type: application/json" \
     -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
     -d "{\"text\": \"<markdown body>\"}"
   ```
   Escape the markdown body for JSON. For long reports, build the JSON with Python to handle newlines safely.

4. **Link PR** (if applicable)

   ```bash
   shortcut_call curl -s -X PUT "https://api.app.shortcut.com/api/v3/stories/<id>" \
     -H "Content-Type: application/json" \
     -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
     -d "{\"external_links\": [\"<github-pr-url>\"]}"
   ```
   Note: this replaces all external links. Fetch existing links first and merge.

5. **Update story metadata** (if needed)

   Update state, labels, custom fields, or estimate:
   ```bash
   shortcut_call curl -s -X PUT "https://api.app.shortcut.com/api/v3/stories/<id>" \
     -H "Content-Type: application/json" \
     -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
     -d "{\"workflow_state_id\": <state_id>}"
   ```
   Fetch workflow states from `/workflows` to map names to IDs. Cache per session.

## Report Body — see `qa/references/write-report.md`

The body of the comment (shape, tone, repro/result/evidence structure, narrative-not-technical rules, single-flow vs multi-scenario templates, worked examples) is canonical and destination-agnostic — it lives in [skills/qa/references/write-report.md](../../qa/references/write-report.md). Read that for content rules and load the per-shape template/example from `qa/references/write-report/` when actually drafting.

This file owns only the **Shortcut-specific mechanics** above (file upload via `/files`, comment POST, PR linking, state updates) and the **output confirmation** below.

## Output

After posting, confirm what was done:

```markdown
## Shortcut Report Posted

- Story: sc-<id> (<story name>)
- Comment: posted (<comment link or confirmation>)
- Evidence: <N files uploaded / none>
- PR linked: <yes / no>
- State updated: <new state / unchanged>
```

## Notes

- Always fetch the story first to confirm it exists and get current state
- Upload evidence before posting comments so URLs are available for embedding
- Use Python for JSON body construction when the report contains newlines or special characters
- When updating `external_links`, merge with existing links — don't replace
- Prefer video evidence over screenshots for complex UI flows
- Keep reports factual — no speculation about cause or impact beyond what evidence shows
