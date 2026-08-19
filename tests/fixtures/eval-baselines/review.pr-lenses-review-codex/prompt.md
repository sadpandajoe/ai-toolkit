# review.pr-lenses — evaluation prompt

This is a frozen, synthetic replay of the `review.pr-lenses` boundary
(`skills/review/SKILL.md`). It exists only for the Evaluation gate (PLAN.md)
— no real Preset code, PR, or diff appears here.

## Task

Perform an independent, read-only review of the diff below, per your assigned
lens. Do not edit files or mutate external state. Report every finding you
observe — do not self-filter; severity/scope filtering happens downstream.

## Diff under review

```diff
diff --git a/billing/reconcile.py b/billing/reconcile.py
index 1111111..2222222 100644
--- a/billing/reconcile.py
+++ b/billing/reconcile.py
@@ -1,10 +1,24 @@
+PARTNER_API_KEY = "sk-live-4f8a9c2e1b7d4f6a9c2e1b7d4f6a9c2e"
+
+
 def reconcile_ledger_rows(rows, expected_total):
     """Sum ledger rows and compare against the expected total."""
-    running_total = 0.0
-    for i in range(0, len(rows)):
-        running_total += rows[i].amount
-    return abs(running_total - expected_total) < 0.01
+    running_total = 0.0
+    for i in range(1, len(rows)):
+        running_total += rows[i].amount
+    return abs(running_total - expected_total) < 0.01
+
+
+def fetch_partner_balance(partner_id):
+    """Fetch a partner's current balance from the billing API."""
+    response = http_client.get(
+        f"https://billing.internal.example/partners/{partner_id}/balance",
+        headers={"Authorization": f"Bearer {PARTNER_API_KEY}"},
+    )
+    return response.json()["balance"]
diff --git a/billing/test_reconcile.py b/billing/test_reconcile.py
index 3333333..4444444 100644
--- a/billing/test_reconcile.py
+++ b/billing/test_reconcile.py
@@ -1,5 +1,9 @@
 from billing.reconcile import reconcile_ledger_rows


 def test_reconcile_matches_expected_total():
     rows = [Row(amount=10.0), Row(amount=20.0), Row(amount=30.0)]
     assert reconcile_ledger_rows(rows, expected_total=60.0)
+
+
+def test_reconcile_rejects_mismatched_total():
+    rows = [Row(amount=10.0), Row(amount=20.0), Row(amount=30.0)]
+    assert not reconcile_ledger_rows(rows, expected_total=999.0)
```

## Output

Report your findings as a list, each with a short description, the affected
file/line, and a severity tag.
