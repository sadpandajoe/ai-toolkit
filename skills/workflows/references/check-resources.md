# Local Environment Capacity Check

> **When**: You want to know what Docker containers are running, which look stale, and whether you have headroom to start another stack.
> **Produces**: A capacity report — host vs Docker daemon ceilings, current usage, stale-container list, and a go/no-go recommendation.

## Effect Boundary

Effect: `local_mutation`.

## Usage

```
check-resources         # Full report
check-resources stale   # Only the stale containers
```

## Docker Facts

This file is the one home of these facts.

- Docker Desktop's memory cap (`Total Memory` in `docker info`) bounds all
  containers together, independent of host RAM.
- Warn at 70% of the cap: running out is an OOM kill, not a slowdown.
- A container is stale when it has been up over 24 hours or is named for
  another branch (`fix-*`, `feat-*`, `bug-*`).
- A Superset-class stack takes about 5 GB.

## Steps

1. Gather in parallel: `docker info`, `docker ps`, `docker stats --no-stream`,
   and host memory (`sysctl -n hw.memsize` on macOS, `/proc/meminfo` on
   Linux). If `docker info` fails, report the daemon down and stop.
2. Docker headroom is the cap minus the containers' summed memory. Over 6 GB
   with over 4 GB host memory free is `GO`; 3–6 GB is `MARGINAL — consider
   stopping a stale stack first`; under 3 GB is `NO-GO — raise Docker Desktop
   cap or stop a stack`.
3. Report host, cap, usage as a share of the cap, running and stale containers
   with age and reason, headroom, and the verdict; `stale` renders only the
   stale list.
4. Stop only the containers the user confirms, with the exact `docker stop
   <names>`. Never change Docker Desktop settings programmatically; suggest
   Settings → Resources → Memory.
