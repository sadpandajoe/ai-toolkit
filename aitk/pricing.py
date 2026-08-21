"""API-equivalent model pricing used by local reports."""

from __future__ import annotations


PRICING = {
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "claude-fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 1.00,
        "cache_create": 12.50,
    },
    "claude-opus-4-8": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.20,
        "cache_create": 2.50,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_create": 1.25,
    },
    "claude-opus-4-6": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
}


def get_pricing(model: str) -> dict[str, float] | None:
    if model in PRICING:
        return PRICING[model]
    for key in sorted(PRICING, key=len, reverse=True):
        if model.startswith(key):
            return PRICING[key]
    return None


def compute_cost(usage: dict[str, object], model: str) -> float:
    pricing = get_pricing(model)
    if pricing is None:
        return 0.0
    return (
        int(usage.get("input_tokens", 0)) * pricing["input"] / 1_000_000
        + int(usage.get("output_tokens", 0)) * pricing["output"] / 1_000_000
        + int(usage.get("cache_read_input_tokens", 0))
        * pricing["cache_read"]
        / 1_000_000
        + int(usage.get("cache_creation_input_tokens", 0))
        * pricing["cache_create"]
        / 1_000_000
    )
