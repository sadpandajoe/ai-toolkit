# Shortcut Report

Post a report (QA results, a fix summary, test findings) to a Shortcut story
with its evidence and metadata. The comment body's shape and tone come from
[skills/qa/references/write-report.md](../../qa/references/write-report.md);
this file owns only the Shortcut mechanics. Make every call with
`<skill-dir>/scripts/sc.sh` ([fetch.md](fetch.md)).

1. **Resolve the story** and confirm it exists:
   `<skill-dir>/scripts/sc.sh get /stories/<id>`.
2. **Upload evidence** before the comment, so the comment can embed the hosted
   URLs. Use the `/files` endpoint, not `/stories/<id>/files`:
   - inline images for the comment body: upload *without* `story_id`
     (`sc.sh upload <path>`); the URL renders in markdown but the file stays
     out of the story's Files panel;
   - evidence reviewers should find in the Files panel (videos, logs): upload
     with `story_id` (`sc.sh upload --story <id> <path>...`).

   `sc.sh upload` sends the parts as `file0`, `file1`, ... (plus `story_id`
   with `--story`). Do not pass a `description` form field: it causes a
   validation error. Capture each returned `url` (`![alt](<url>)` for images).
   Videos keep the recorder's name (`<source-id>-<short-name>-<UTC-timestamp>.webm`).
3. **Post the comment**, building the JSON with Python so newlines and quotes
   are escaped:

   ```bash
   python3 -c 'import json, sys; print(json.dumps({"text": sys.stdin.read()}))' <report.md >comment.json
   <skill-dir>/scripts/sc.sh post /stories/<id>/comments @comment.json
   ```
4. **Link a PR**: the PUT replaces `external_links`, so fetch the existing links
   and merge them first:
   `sc.sh put /stories/<id> '{"external_links": ["<existing links>", "<github-pr-url>"]}'`.
5. **Update metadata** when asked:
   `sc.sh put /stories/<id> '{"workflow_state_id": <state_id>}'`, mapping state
   names through `/workflows`.

## Output

```markdown
## Shortcut Report Posted

- Story: sc-<id> (<story name>)
- Comment: posted (<comment link or confirmation>)
- Evidence: <N files uploaded / none>
- PR linked: <yes / no>
- State updated: <new state / unchanged>
```
