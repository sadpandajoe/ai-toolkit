# `routed_subagent` mechanics and integrity caveat

Background for the `routed_subagent` capability binding in
`config/providers/claude.md`/`codex.md`. The enforcement rules themselves
(one exact selector and effort, no fallback, fail on CLI/contract rejection,
never substitute a generic worker on `MODEL_ROUTE_UNAVAILABLE`) stay inline in
those binding docs — this file only carries the descriptive mechanics behind
them.

## Contract-closure derivation

The runner derives and inlines the boundary's validated transitive contract
closure because safe mode disables ambient skill loading — a routed worker
can't rely on skills being available in its environment, so the full closure
is computed and passed in explicitly.

Codex's transport additionally launches from a sanitized temporary project
root, exposes the target only as a scoped `--add-dir`, and disables user
config, hooks, MCP servers, exec-policy rules, and project-document
discovery — narrowing the worker's ambient environment to exactly the
inlined closure, nothing picked up implicitly from the host project.

## Integrity and provenance caveat

Per-file SHA-256 labels attached to the transmitted content are diagnostic
content identifiers, not an independently trusted integrity gate — they let
you confirm what was sent, not attest what the provider actually ran.

Neither Claude's success envelope nor Codex's JSONL output attests the
provider's internal serving-model identity. Backend substitution (the
provider silently serving a different model than the one selected) remains
outside the toolkit's evidence boundary in both cases.
