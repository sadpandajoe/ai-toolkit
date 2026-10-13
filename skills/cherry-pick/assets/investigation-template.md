# Investigation Output Template

The rules for filling it are in
[../references/investigate.md](../references/investigate.md).

```markdown
## Investigation: <sha-short> (<summary>)

### Source Analysis
Change type: functional / structural / dependency / mixed
Key files: [list of most significant files]
Sub-fixes: [if bundled PR, list them; otherwise "N/A"]

### Target Compatibility
Compatible files: [N of total]
Modify/delete risk: [list of files or "none"]
API differences: [list or "none detected"]
Import/module mismatches: [list or "none detected"]
Dependency changes: [list or "none"]

### Prerequisites
Required prior commits: [list or "none identified"]
Existing fix status: [output from debug/references/check-existing-fix.md or "not a bug fix"]
Ordering constraints: [list or "none"]

### Target-Affected
Verdict: AFFECTED / NOT_AFFECTED / UNCLEAR
Evidence: [buggy pre-fix code present on target, OR named introducing commit + is-ancestor result, OR why unclear]

### Raw Signals for Gate
New dependencies: YES / NO
Lockfile changes: YES / NO
Target APIs compatible: YES / NO / PARTIALLY
Conflicts expected: YES / NO / LIKELY
Prerequisite needed: YES / NO
Target-affected: AFFECTED / NOT_AFFECTED / UNCLEAR
```
