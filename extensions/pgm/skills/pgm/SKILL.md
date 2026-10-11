---
name: pgm
description: Create program health and velocity reports from configured delivery data. Use for current status reports, historical velocity reports, or audience-specific program communication. Do NOT use for product implementation, code review, or reports without the required PGM configuration.
---

# Program Management Reports

Run `bin/aitk list --with-pgm --details --json`, pick the PGM workflow the user
asked for from its summary, and load the reference and rules it returns. Then
run `bin/aitk pgm-preflight` as that reference says; a nonzero result stops
the workflow before any collection. Refuse PGM work when the extension is not
installed.
