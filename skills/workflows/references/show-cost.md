# Token Usage and Cost Summary

> **When**: You want to understand provider usage across projects and sessions.
> **Produces**: Daily, weekly, and monthly cost breakdowns with model and project attribution.

## Effect Boundary

Effect: `read_only`.

## Usage
```
show-cost              # Last 7 days (default)
show-cost today        # Today only
show-cost 30d          # Last 30 days
show-cost month        # Current calendar month
show-cost all          # All time
show-cost 2026-04-01   # Since a specific date
```

## Steps

### 1. Run the Aggregation Script

```bash
python3 <toolkit-root>/scripts/show-cost.py <period>
```

Where `<period>` is the argument from the user (default: `7d`).

### 2. Present the Output

The script handles all formatting. Present its output directly — do not reformat or summarize.

### 3. Interpret If Asked

If the user asks "why is this expensive?", look for:
- **High-cost model output tokens**: long reasoning chains, verbose subagents
- **Low cache hit rate**: context not being reused efficiently across turns
- **One project dominating**: a specific workflow is burning tokens
- **Many messages per session**: long sessions where context compresses and re-expands

## Notes
- Costs shown are **API-equivalent estimates**, not actual billing. Subscription users pay a flat rate regardless of token usage. These numbers indicate relative usage weight.
- Unknown models are shown with token/message counts but excluded from cost totals instead of being priced as a different provider/model.
- The exact provider/session source supported by this release is documented in [telemetry support](../../../docs/TELEMETRY.md). Unsupported sources are reported as unavailable.
- Promotional pricing uses each record's timezone-aware timestamp. Missing, invalid, or timezone-free timestamps are unpriced rather than charged at today's rate.
- The script skips subagent log files (they're under `/subagents/` subdirectories).
- Multi-day sessions are attributed proportionally to each active day.
