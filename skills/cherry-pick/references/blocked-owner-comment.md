# Blocked-Owner Notification Comment

When a release-candidate cherry-pick does not land (`Skipped`, `Blocked` or
`Rejected`), the decision to leave it off, force it or adapt it belongs to the
person who put the change on the release radar. Notify that person on the
Shortcut story with a clean decision. [unblock-discovery.md](unblock-discovery.md)
finds what would unstick the row; this comment tells the owner and asks them to
decide. Post one comment that carries both.

## When to Run

Any release-candidate story whose PR(s) did not land this pass: `Blocked` /
`Rejected` (missing architecture, modify/delete, a dependency chain,
divergence) or a `Skipped` that carries a judgment call.

**Do not notify** when there is nothing to decide: the merge SHA is already on
the branch, the story has no merged PR in `cherry_pick.upstream_repo`, or the
gate returned `NOT_AFFECTED` (the bug's trigger never reached the branch). An
audit that drops 20 not-affected candidates must not become 20 pings; an FYI
at most.

## The Five Required Elements

In this order:

1. **Mention the labeler**, the person who added `release-candidate` (not the
   story owner, not the PR author): adding the label asked for the backport.
2. **Why it's blocked:** the concrete reason, naming the missing files,
   architecture or divergence.
3. **How to unblock it, with its true cost:** from the unblock-discovery
   output, carrying the measured facts per link (`#<a> — 89 files, +15.5k,
   includes a DB migration`) and its `Difficulty` verbatim. A bare PR list
   reads as "two quick cherries and we're in", which is the failure this
   element prevents. If there is no path, say so.
4. **Recommendation:** our call (leave it off / force it / adapt it) and why.
   Let the difficulty drive it: an `easy` chain is reasonable to recommend; a
   `heavy` or `risky` one (a migration on a release branch, a large feature PR
   to land a small fix) leans away unless customer impact justifies it, and
   the trade-off is named.
5. **Let them decide:** the options are their call. We recommend; the labeler
   decides. Never force-backport or adapt on our own recommendation without
   their reply.

## Org Data

`cherry_pick.release_candidate_label_id` (the label's Shortcut id) and
`cherry_pick.upstream_repo` (`owner/name`) live in the target repo's
`.ai-toolkit/config.json`, kept out of commits. When a key is missing, ask once,
write it there, and reuse it.

## Finding the Decider

1. Story history: MCP `stories-get-history`, or REST
   `GET /stories/{id}/history` through `sc.sh`.
2. Find the entry with an action in `actions[]` whose
   `changes.label_ids.adds` contains the label id; use the **most recent**
   add.
3. Its `member_id` is the decider and `actor_name` the display name; there is
   no `actor_id`.

When no label-add actor is resolvable (label set at creation, actor unknown),
mention the story owner and say why.

## Mention Syntax

Plain `@name` text does **not** notify. Use the member link:

```
[@<mention_name>](shortcutapp://members/<member-id>)
```

`<member-id>` is the `member_id` from history; resolve the `mention_name` with
MCP `users-list` or REST `GET /members`.

## Comment Template

Post with MCP `stories-create-comment` or REST `POST /stories/{id}/comments`
([skills/shortcut/references/report.md](../../shortcut/references/report.md)).
Keep the bold headers; trim options that do not apply (with no viable path,
the decision is just "confirm we leave it off").

```markdown
**Cherry-pick to `<target-branch>` — <#PR or "this"> <skipped|blocked>, owner decision needed** [@<handle>](shortcutapp://members/<member-id>)

**Why it's blocked**
<Concrete reason: the missing files / architecture / divergence on the release branch.>

**The unblock path<, if you want it,> is <a single PR | a chain> — <easy | heavy | risky>**
#<a> → #<b> → … → #<this>
- #<a> — <N files, +A/-D, migration: yes/no>. <what it provides>
<One honest line on total effort, e.g. "Net: a 90-file feature PR with a new DB migration to land a 9-file fix.", or "no clean path exists".>

**Recommendation: <don't force it | backport the chain | targeted adapt>.**
<Why, tied to customer impact and risk.>

**Owner's call:**
1. **<Leave it off>** (recommended) — <consequence>.
2. **<Force the full backport>** — <what that costs / risks>.
3. **<Targeted adapt>** — <scope, if viable>.

Let me know which way you want to go and I'll action it.
```

## After Posting

- Set the row's `Owner-notified` cell to the comment link.
- Do not resolve the story or remove the label; that is the owner's action.
- The row's result stays `Skipped` / `Blocked` / `Rejected`; the comment is
  the handoff. An owner's decision starts a new, separately authorized action.
