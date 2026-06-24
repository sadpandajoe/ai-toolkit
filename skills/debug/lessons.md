# Debug Lessons

Narrative heuristics for diagnostic work — patterns learned from real failures. Distinct from `gotchas.md` (sharp, specific traps) and the `references/` (workflow shapes): a lesson is a judgment call about *where to look next*.

## Stop hardening tests when retries collectively fail — escalate to infra

When successive *independent* test-layer hardenings (warm-up gate, request-level retry, post-write polling, click-level retry, …) collectively still fail on the **same flake family** across multiple CI builds, the next fix is **infra, not another test patch**.

- After **two or more** independent test-layer hardenings miss the same flake family, move the hypothesis space to **infra / workspace / pod-level**: OOMKill signatures, upstream connectivity, resource requests/limits, deployment config.
- The tell you've crossed the line: *"warm-up succeeded but the workspace degrades during the run."* Test code cannot fix a workspace that goes offline mid-run.
- Confirm with evidence — OOMKill logs, restart counts, host-daemon contention — not by adding one more retry and watching whether it flakes less.

**Example.** A PR stacked four independent retry layers (workspace warm-up consecutive-200 gate, a 4-attempt API budget, a 502 write-retry, a 3-attempt click retry) against a sandbox pod that was OOMKilled ~15s every ~2min. None worked. The real fix was a one-line helm memory bump (1200Mi→3Gi); the soak went 5/5 green immediately. Every test-layer patch was correct in isolation and useless against the actual cause.

Related: slow-CI symptoms can also stem from host-daemon contention (buildx running outside pod cgroups), which masquerades as test flakiness — check infra contention before hardening tests.
