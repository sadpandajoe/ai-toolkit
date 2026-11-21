# Monthly Velocity

The pipeline in `$PGM_DIR` is the authority for how metrics are collected and
computed; never reimplement a metric by hand.

- The pipeline reads `config.json` directly: if `--month` differs from the
  config's `month`, have the user update `config.json` first.
- Follow `$PGM_DIR/run.md`. When `raw_*.json` files already exist for the
  month, re-run only the processing steps.
- `--summary-only` skips collection: read `data/{month}/metrics.json` and write
  an executive summary per [comms.md](comms.md).

Output is `data/{month}/report.md` and `metrics.json`. Before presenting the
report, flag data-quality problems:

- a team with 0 completed stories (collection probably failed);
- negative cycle times (timestamp problems);
- per-person PR counts implausible for the team size;
- many unlinked stories or PRs (Shortcut ↔ GitHub linkage gaps).

Live state belongs to the status report.
