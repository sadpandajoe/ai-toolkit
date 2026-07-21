---
name: pgm
description: Create program health and velocity reports from configured delivery data. Use for current status reports, historical velocity reports, or audience-specific program communication. Do NOT use for product implementation, code review, or reports without the required PGM configuration.
---

# Program Management Reports

This opt-in public router reads workflow identity and routing data only from
[the PGM manifest](../../interfaces/workflows.json).

1. Match an explicit workflow name or the highest-specificity trigger in the
   manifest. Refuse PGM routing when the extension was not enabled.
2. Confirm the owner is `pgm`, join `reference_root` with
   `<workflow.name>.md`, and reject absolute paths or traversal.
3. Load exactly that workflow reference, its declared rules, and only the
   logical dependencies it names. Resolve dependencies through the toolkit
   skill manifest/package root rather than an installed symlink.
4. Read `interfaces/providers.json` and load the current provider's declared
   binding document before using any orchestration capability.
5. Run `bin/aitk pgm-preflight --workflow <name>` (with connector capability
   flags only when available) before collecting data. A nonzero result stops
   the workflow before collection with zero report effects.
   Executable Python collectors must enter through
   `aitk.pgm.run_after_preflight`; do not invoke a collector callback outside
   that guard. For provider-driven collection, rerun the CLI preflight
   immediately before each collection batch.
   Preserve the workflow's authorization, checkpoint, verification, and
   reporting contract.

This skill and its natural-language triggers are the public PGM interface.
