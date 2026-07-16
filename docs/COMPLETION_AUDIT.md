# 10/10 Completion Audit

This rubric defines “10/10” as a maintainable product contract, not a claim that no future improvement is possible. Every criterion must have an implementation surface, an automated check, and a repeatable verification command.

| # | Criterion | Implementation evidence | Automated evidence |
|---|---|---|---|
| 1 | One canonical workflow source | Skill references plus total core/PGM manifests; aliases generated only | Exact adapter tests, ownership scan, untracked-adapter CI negative fixture |
| 2 | Small, stable public interface | `$workflows`, optional `$pgm`, public-direct classifications, and additive CLI JSON | Total skill classification, owner-aware routing, list-detail and JSON-schema tests |
| 3 | Provider-portable core | Shared capability vocabulary and provider bindings | Provider primitive negative fixtures, frontmatter validation, package self-containment |
| 4 | Provider parity without duplication | Capability-preserving Claude/Codex adapters around one skill/reference graph | Provider binding validation, exact aliases, plugin hooks/metadata tests |
| 5 | Safe defaults | Machine authorization/effect policies plus protected state and secret-safe diagnostics | Semantic negative fixtures, RBAC dry-run, hook suite, no-eval and no-secret-output checks |
| 6 | Non-destructive lifecycle | Mode-0600 ledger, exact inventory, atomic install/uninstall/rollback | Idempotency, conflict, legacy, hostile-ledger, corrupt-backup, moved-root, and every fault-boundary fixture |
| 7 | Deterministic health | Source and installed PASS/DRIFT/FAIL diagnostics | Strict doctor, installed matrix, stale/untracked build and malformed-ledger tests |
| 8 | Durable recovery | One checkpoint parser/serializer/state machine for all durable workflows | Every phase fresh-process round trip, illegal generation/edge negatives, four effect crash windows |
| 9 | Behavioral conformance | v2 contracts bind effects, gates, phases, reconciliation, verification, and reporting | Structural plus semantic negative fixtures, PGM zero-effect preflight, timestamp boundary tests |
| 10 | Versioned release proof | Shared SemVer, support matrix, pinned CI, installable wheel/plugin, SHA-bound audit | Version/package tests, OS/Python matrix, isolated wheel smoke, clean detached-worktree rehearsal |

## Required release gate

```bash
bin/aitk build --with-pgm
git status --porcelain --untracked-files=all -- commands extensions/pgm/commands
bin/aitk doctor --strict
bin/aitk check
git diff --check
```

The final proof is run again from the committed SHA in a detached temporary
worktree, including an isolated wheel install/entrypoint smoke and clean-room
install/reinstall/uninstall/rollback. The SHA is release-ready only when that
worktree remains clean after every gate. Provider support may grow, but new
adapters must preserve these contracts and cannot become a second workflow
source.
