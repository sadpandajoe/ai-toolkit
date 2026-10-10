# Backend Review

The backend checklist the independent reviewer applies to the backend files in
a diff. It adds what to check; how to grade and report comes from the reviewer
contract.

Read before grading: `rules/severity.md`

- **Migrations.** Compatible with the code that runs while the deploy rolls
  out, reversible or with a stated rollback, and shipped together with the code
  that uses them.
- **Endpoints and authorization.** Every new or changed path checks
  authorization on the server. When a client change works around unsafe server
  behavior (no page-size cap, a missing required filter, an unbounded batch),
  check whether the endpoint should enforce the limit too; when the endpoint is
  outside the diff, that goes under Remaining.
- **Queries.** New queries inside loops, unbounded result sets, and filters on
  columns with no index.
- **Failure behavior.** Error responses match the neighboring endpoints, and new
  calls to external services have a timeout and a handled failure path.
- **Consistency.** API naming, versioning, and data modeling follow the
  existing backend patterns; find them in the repo rather than assuming.
