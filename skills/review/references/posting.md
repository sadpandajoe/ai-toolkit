# Posting a PR Review

GitHub gets clean finding descriptions only. Severity tags (`[major]`,
`[minor]`, `[nitpick]`), confidence, scores and model provenance stay in the
local summary. Never put them in inline comments, top-level comments or review
bodies unless the user asks for labeled comments.

A posted comment is read by a tired engineer:

- **Ask, don't rule.** The default register is a question: "I see X here; the
  sibling does Y. Why the difference?" Keep declarative phrasing for blockers.
- **Scale the ask to severity.** A question for nitpicks ("Did we mean to
  update this?"), "we should" or "can we" for should-fix items, plain
  statements for blockers. Speak to the code, never the author ("you forgot"
  becomes "this misses").
- **Short enough to read at a glance.** State the issue and the ask, then
  stop. A finding that needs a paragraph is usually two findings or a
  conversation. Name the sibling, helper or prior pattern. The inline anchor
  already carries the file and line, so don't restate them.
- **No code blocks by default.** Add a `suggestion` block only when the fix is
  non-obvious and the finding is should-fix or worse. For a missing test,
  point at the technique in one sentence; paste a full test only when the
  setup is genuinely non-obvious.
- **Match the house voice.** Before posting, look at the author's or the
  repository's recent review comments and mirror their length and register.
- **Cut the machine tells:** scaffolding labels ("Result:", "Worth noting:"),
  walking the author through their own code, restating the PR description,
  over-hedging, double negatives, and nitpicks stacked to pad the review. A
  review with only nitpicks is an approval; say "approve" instead.
