# Review-PR Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `review-pr`, add the phase
and PR identifier below it:

**Single-PR mode**:

```markdown
- Phase: gather / complexity-gate / understand-problem / detect-team / launch-review / pattern-analysis / scoring / gate / post / summarize
- PR: <number> — <title>
```

**Batch mode**:

```markdown
- Mode: batch
- Phase: gather-list / dispatch-reviews / collect-results / batch-summary
```

Reviewer team, scores, recommendation, and post status (single-PR), or per-PR completion counts (batch) belong in `## Current Status`.
