# Frontend Review

The frontend checklist the independent reviewer applies to the frontend files
in a diff. It adds what to check; how to grade and report comes from the
reviewer contract.

Read before grading: `rules/severity.md`

- **States.** New asynchronous UI shows loading, error, and empty states.
- **Accessibility.** New interactive elements work from the keyboard and carry
  a label a screen reader can announce.
- **State ownership.** Each piece of state has one owner, derived values are
  computed rather than copied into state, and effects and subscriptions are
  cleaned up.
- **Cost.** A new dependency, or new work in a render path or a long list,
  earns what it adds to bundle size and render time.
- **Consistency.** New components reuse the existing component library and
  follow the patterns of their neighbors; find them in the repo rather than
  assuming.
