# Blocked-Owner Comment

When a release-candidate story's cherry did not land (`Skipped` with a
judgment call, `Blocked`, `Rejected`), the call to leave it off, force it or
adapt it belongs to whoever put it on the release radar. Post one Shortcut
comment that carries the reason, the unblock path and a recommendation.

**Don't notify** when there is nothing to decide: the merge SHA is already on
the branch, the story has no merged PR in `cherry_pick.upstream_repo`, or the
bug is not live on the target. An audit that drops 20 not-affected candidates
must not become 20 pings.

## Who to mention

The person who added the `release-candidate` label, not the story owner or the
PR author. From the story history (MCP `stories-get-history`, or REST `GET
/stories/{id}/history` through the `shortcut` skill's `sc.sh`): take the most
recent entry whose `actions[].changes.label_ids.adds` contains
`cherry_pick.release_candidate_label_id`. Its `member_id` is the decider and
`actor_name` the display name; there is no `actor_id`. When no label-add actor
resolves (label set at creation), mention the story owner and say why.

Plain `@name` text does **not** notify. Use the member link, with the
`mention_name` from MCP `users-list` or REST `GET /members`:

```
[@<mention_name>](shortcutapp://members/<member-id>)
```

## The comment

Five elements, in this order: the mention; the concrete blocker; the unblock
path with its measured cost per link (`#<a> — 89 files, +15.5k, includes a DB
migration`) and its difficulty verbatim, since a bare PR list reads as "two
quick cherries"; our recommendation, driven by that difficulty (a heavy or
risky chain on a release branch leans away unless customer impact justifies
it); and their options. We recommend; the labeler decides. Never force or adapt
on our own recommendation.

Post with MCP `stories-create-comment` or REST `POST /stories/{id}/comments`.
Keep the bold headers; trim options that don't apply.

```markdown
**Cherry-pick to `<target-branch>` — <#PR or "this"> <skipped|blocked>, owner decision needed** [@<handle>](shortcutapp://members/<member-id>)

**Why it's blocked**
<missing files / architecture / divergence on the release branch>

**The unblock path<, if you want it,> is <a single PR | a chain> — <easy | heavy | risky>**
#<a> → #<b> → … → #<this>
- #<a> — <N files, +A/-D, migration: yes/no>. <what it provides>
<one honest line on total effort, or "no clean path exists">

**Recommendation: <don't force it | backport the chain | targeted adapt>.**
<why, tied to customer impact and risk>

**Owner's call:**
1. **<Leave it off>** (recommended) — <consequence>.
2. **<Force the full backport>** — <cost / risk>.
3. **<Targeted adapt>** — <scope, if viable>.

Let me know which way you want to go and I'll action it.
```

Afterwards, record the comment link on the row. Don't resolve the story or
remove the label; that is the owner's action.
