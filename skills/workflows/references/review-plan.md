# One-Off Plan Validation

> **When**: A `PLAN.md` or `PROJECT.md`-embedded plan needs independent validation without the full `create-feature` workflow.
> **Produces**: A validated plan with `APPROVE`, or the findings that block it, recorded in `PLAN.md` and `PROJECT.md`.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

`review-plan` in `interfaces/contracts.json`; transitions and effects go through
`bin/aitk checkpoint`.

## Usage

```
review-plan            # validate the active plan
review-plan --pm       # include the feature brief in the validator's input
```

## Steps

1. **Read the plan.** `PROJECT.md` points to the active plan; read `PLAN.md`,
   or the embedded plan when there is none. Stop when no plan content exists.
   Ensure a routing snapshot exists: `bin/aitk project-state init --workflow
   review-plan --complexity <the plan's recorded complexity, COMPLEX when
   absent> --size <the plan's size>`; it is a no-op when the owning workflow
   already wrote one.
2. **Choose the mode.** A decomposition (phases, boundaries, invariants) is
   validated in `decomposition` mode; a slice plan or single phase in
   `phase-plan` mode; a bug-fix plan with an RCA in `fix-plan` mode.
3. **Validate** with
   [skills/planning/references/validate-plan.md](../../planning/references/validate-plan.md):
   one independent validator, preferably on the other provider. `--pm` adds
   the brief to its input so scope and acceptance criteria are checked with the
   plan.
4. **Consume the verdict** as `validate-plan.md` (Consume the verdict)
   defines it: one informed revision, never a third round of the same
   validator.
5. **Record.** Append `## Validation: <unit>` with the verdict and blocking
   findings to `PLAN.md`; record the gate with
   `bin/aitk project-state gate --gate plan --status <...> --format block`
   (`--editorial` for a wording-only revision) and paste the block it prints;
   write `## Plan Validated` to `PROJECT.md`.

## Summary

```markdown
## Review-Plan Complete
Verdict: APPROVE | CHANGES_REQUIRED | REPLAN (rounds: <1|2>)
Validator: <provider/family>
Blocking findings: <count, or none>
Key revisions: <what changed, or none>
Next: <implement via create-feature | revise | user decision>
```
