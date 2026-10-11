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
- Make every call with `<skill-dir>/scripts/sc.sh` ([fetch.md](fetch.md)); it handles auth, the retry and parsing

Read `rules/shortcut-api.md` for the global Shortcut routing constraints.

## Core Steps

1. **Resolve the story**

   Extract the numeric ID from `sc-NNNNN`, URL, or raw number.
   Fetch the story to confirm it exists and get current state:
   ```bash
   <skill-dir>/scripts/sc.sh get /stories/<id>
   ```

2. **Upload evidence** (if any)

   Upload files before posting the comment so the comment can reference the hosted URLs.
   Use the `/files` endpoint (not `/stories/<id>/files`).

   **For inline images in the comment body** (screenshots embedded via markdown), upload *without* `story_id`. The returned `url` is workspace-scoped and renders in markdown, but the file does not appear in the story's Files sidebar — keeps the story clean when the image is only meaningful in context of the comment:
   ```bash
   <skill-dir>/scripts/sc.sh upload <path>
   ```

   **For evidence that should be attached to the story** (videos, logs, anything reviewers should find via the Files panel), include `story_id`:
   ```bash
   <skill-dir>/scripts/sc.sh upload --story <id> <path>...
   ```

   `sc.sh upload` sends the parts as `file0`, `file1`, ... (and `story_id` with `--story`). Do not add a `description` form field: it causes a validation error.
   Capture the returned `url` for embedding in the comment (`![alt](<url>)` for images).
   Name video files descriptively: `sc-<id>-<what-was-tested>.webm`.

3. **Post the report comment**

   Use the appropriate template from the Report Templates section below.
   ```bash
   python3 -c 'import json, sys; print(json.dumps({"text": sys.stdin.read()}))' <report.md >comment.json
   <skill-dir>/scripts/sc.sh post /stories/<id>/comments @comment.json
   ```
   Build the JSON body with Python (as above) so newlines and quotes in the markdown are escaped.

4. **Link PR** (if applicable)

   ```bash
   <skill-dir>/scripts/sc.sh put /stories/<id> '{"external_links": ["<existing links>", "<github-pr-url>"]}'
   ```
   Note: this replaces all external links. Fetch existing links first and merge.

5. **Update story metadata** (if needed)

   Update state, labels, custom fields, or estimate:
   ```bash
   <skill-dir>/scripts/sc.sh put /stories/<id> '{"workflow_state_id": <state_id>}'
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
