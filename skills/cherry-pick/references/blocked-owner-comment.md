# Blocked-Owner Notification Comment

When a release-candidate cherry-pick cannot be applied — `Skipped`, `Blocked`, or `Rejected` — the decision to leave it off, force it, or adapt it is **not ours to make silently**. It belongs to the person who put the change on the release radar. This reference defines how to notify that person on the Shortcut story and hand them a clean decision.

This runs alongside [unblock-discovery.md](unblock-discovery.md): unblock-discovery finds *what would unstick it*; this comment *tells the owner and asks them to decide*. Post one comment that carries both.

## When to Run

Run for any release-candidate story whose PR(s) we did **not** land this pass:
- `Blocked` / `Rejected` — architecture missing on target, modify/delete, dependency chain, structural divergence.
- `Skipped` — we judged it shouldn't be backported (e.g. fixes a master-only regression that can't occur on the release branch).

**Skip** only when there is genuinely nothing for an owner to decide — e.g. the PR's merge SHA is already on the branch (already backported), the story has no merged apache/superset PR at all, or the gate returned high-confidence `NOT_AFFECTED` (target not affected — the bug's trigger never reached the branch). A high-confidence not-affected skip is a no-decision skip like already-backported: don't fire an owner comment for it, or a release audit that drops 20 not-affected candidates becomes a notification cannon. Downgrade to an FYI at most. Reserve the owner comment for skips that carry a real judgment call (blocked, force-vs-leave-off, adapt).

## The Five Required Elements

Every notification comment must contain all five, in this order:

1. **Mention the person who added the `release-candidate` label** — they own the decision (see "Finding the Decider" below). Not the story owner, not the PR author — the *labeler*, because adding the label is the act that asked for the backport.
2. **Why it's blocked** — the concrete reason this change does not apply cleanly to the release branch. Name the missing files/architecture/divergence; don't hand-wave.
3. **How to unblock it** — the path to making it land, **with its true cost**. Often a dependency chain of upstream PRs, not a single PR. Pull this from the unblock-discovery output, and carry its measured facts per link: `#36368 — 89 files, +15.5k, includes a DB migration`. Carry the discovery `Difficulty` verbatim. A bare PR list (`#36368 → #38395 → this`) reads as "two quick cherries and we're in" — that is the exact failure this element exists to prevent. If a link carries a migration or is a large feature PR, the decider must see that before they reply. If there's no path, say so.
4. **Recommendation** — our actual call (leave it off / force it / adapt it), with the reason. Don't stay neutral; we did the investigation, so we owe a recommendation. **Let the difficulty drive it:** if the unblock chain is `easy`, recommending it is reasonable; if it is `heavy` or `risky` (a DB migration on a release branch, or a large feature PR pulled in to land a small fix), lean *away* from "pull in the chain" unless there is active customer impact that justifies the surface — and name that trade-off. Never soft-recommend a migration-bearing chain as if it were a clean backport.
5. **Let them decide** — present the options as *their* call and close by asking which way to go. We recommend; the labeler decides. Do not action a force-backport or adaptation off our own recommendation without their reply.

## Finding the Decider (who added the label)

Use the story's history to find who added `release-candidate` (label id **78270**):

1. `stories-get-history` for the story id.
2. Scan entries for an action whose `changes.label_ids.adds` array contains `78270`.
3. That entry's `actor_id` / `member_id` is the decider; its `actor_name` is the display name.

If multiple entries add/remove the label, use the **most recent add** — that's who currently wants it on the release.

If history shows no explicit label-add actor (e.g. label set at creation, or actor unresolved), fall back to the story owner/requester and say in the comment that you're mentioning them as the owner because the labeler couldn't be resolved.

## Mention Syntax (must actually notify)

Plain `@name` text does **not** create a Shortcut notification. Use the member-link form so the mention registers and the person is pinged:

```
[@mention_name](shortcutapp://members/<member-id>)
```

- `mention_name` is the member's `mention_name` (the @handle), e.g. `eschutho`.
- `<member-id>` is the member UUID — the same `actor_id` you pulled from history (e.g. `5f6d24bc-d083-4560-855f-365aa41428cd`).

Resolve the handle from the id with `users-list` (or `users-get-current` for self). A comment that uses plain `@eschutho` looks right in the text but sends no notification — the owner never sees it. Always use the link form.

## Comment Template

Fill and post with `stories-create-comment`. The bracketed parts are per-cherry; keep the bold section headers.

```markdown
**Cherry-pick to `<target-branch>` — <#PR or "this"> <skipped|blocked>, owner decision needed** [@<handle>](shortcutapp://members/<member-id>)

**Why it's blocked**
<Concrete reason. Name the missing files / architecture / divergence on the release branch.
Example: "6.0 still runs the older `e2e_mt` test harness; the PR touches files that don't exist on
6.0 and the merge conflicts are modify/delete, not content.">

**The unblock path<, if you want it,> is <a single PR | a chain> — <easy | heavy | risky>**
<From unblock-discovery. If a chain, list it in apply order with each link's cost:>
#<a> → #<b> → #<c> → … → #<this>
- #<a> — <N files, +A/-D, migration: yes/no>. <what it provides>
- #<b> — <N files, +A/-D, migration: yes/no>. <what it provides>
<Then one honest line on total effort: e.g. "Net: pulling a 90-file feature PR with a new DB migration onto the release branch to land a 9-file fix." Or a one-line "no clean path exists" if there isn't one. Do not present the chain as a bare list of PR numbers.>

**Recommendation: <don't force it | backport the chain | targeted adapt>.**
<Why. Tie it to customer impact and risk. Example: "This is CI/test-infra only — no
customer-facing code. The backport chain is large and the regression it fixes can't occur on
6.0's harness, so the risk of forcing it outweighs the benefit.">

**Owner's call:**
1. **<Leave it off>** (recommended) — <consequence>.
2. **<Force the full backport>** — <what that costs / risks>.
3. **<Targeted adapt>** — <scope, if viable>.

Let me know which way you want to go and I'll action it.
```

Trim options to the ones that actually apply. If there's no viable unblock path, drop options 2–3 and say so plainly — the decision is then just "confirm we leave it off."

## After Posting

- Record in the execution table / `CHERRY_PICK.md`: `Owner-notified: <story-id> @<handle> (comment <id>)`.
- Do **not** mark the story resolved or remove the `release-candidate` label — that's the owner's action after they decide.
- The cherry's terminal result stays `Skipped`/`Blocked`/`Rejected`; the comment is the handoff, not a state change.
- If the owner replies with a decision, re-enter the relevant flow (apply the chain, adapt, or close out) — that's a new authorized action, not part of this pass.
