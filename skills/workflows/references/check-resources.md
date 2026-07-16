# Local Environment Capacity Check

> **When**: You want to know what Docker containers are running, which look stale, and whether you have headroom to start another stack.
> **Produces**: A capacity report — host vs Docker daemon ceilings, current usage, stale-container list, and a go/no-go recommendation.

## Effect Boundary

Effect: `local_mutation`.

## Usage
```
check-resources         # Full report
check-resources stale   # Only show stale containers
```

## Steps

### 1. Gather Capacity Signals

Run these in parallel:

```bash
docker info | grep -E "CPUs|Total Memory|Server Version"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.RunningFor}}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
sysctl -n hw.memsize hw.ncpu
top -l 1 -n 0 | grep -E "Load Avg|PhysMem"
```

If `docker info` errors (daemon not running), report that and stop — there's nothing more to check.

### 2. Identify Stale Containers

A container is **stale** if any of these are true:
- `STATUS` shows `Up` for **more than 24 hours**
- Name contains a feature/branch prefix (`fix-*`, `feat-*`, `bug-*`, etc.) that doesn't match the current git branch in any tracked working directory
- Image was built > 7 days ago for an ephemeral local stack (best-effort; skip if unclear)

Do **not** stop containers automatically. List them with their age and ask the user which to stop.

### 3. Compute Headroom

- **Docker memory headroom** = `Total Memory` (from `docker info`) − sum of `MemUsage` across containers (from `docker stats`).
- **Host memory headroom** = host RAM − `PhysMem used` (from `top`).
- **Go/no-go for another Superset-class stack** (~5 GB):
  - Docker headroom > 6 GB **and** host PhysMem unused > 4 GB → `GO`
  - Docker headroom 3–6 GB → `MARGINAL — consider stopping a stale stack first`
  - Docker headroom < 3 GB → `NO-GO — raise Docker Desktop cap or stop a stack`

### 4. Render Report

Format:

```
=== Resources ===
Host:   <chip>, <cores> cores, <GB> RAM   load avg <n>   PhysMem unused <GB>
Docker: cap <GiB>, <N> containers running, aggregate <GB> (<%> of cap)

Running:
  <name>  <status>  <mem>  <cpu>
  ...

Stale (> 24h or off-branch):
  <name>  up <duration>  <reason>
  ...
  → Stop any of these? (user confirms before action)

Headroom: <GB> Docker / <GB> host
Verdict:  GO | MARGINAL | NO-GO  for another Superset-class stack
```

If `stale` argument was passed, render only the Stale section.

### 5. Offer Next Actions

Based on verdict:
- `GO` — name the next stack the user is likely starting and proceed only if they confirm.
- `MARGINAL` — list the stale containers as candidates to stop, with the exact `docker stop <names>` command.
- `NO-GO` — recommend either stopping containers or raising the Docker Desktop memory cap (Settings → Resources → Memory). Do not change Docker Desktop settings programmatically.

## Notes

- This command is read-only by default. The only mutation it may perform is `docker stop` on user-confirmed names.
- The "stale" heuristic is conservative — false positives are fine (the user can say "keep that one"), false negatives waste capacity.
- Run this before `create-feature`, `fix-bug`, or any workflow that will spin up a stack, when you suspect things are crowded.
- Always-on guardrails in `rules/resource-management.md` cover the lightweight version of this check; this command is the on-demand deep dive.
