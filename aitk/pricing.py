"""Timestamp-aware API-equivalent model pricing used by local reports.

Together with interfaces/model-routing.json, this is the only place model names
appear. Rates are per million tokens. Claude rates are from
platform.claude.com/docs/en/about-claude/pricing and OpenAI rates from
developers.openai.com/api/docs/pricing, both checked 2026-10-10.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re


PRICING = {
    # OpenAI selectors as Codex CLI names them. The usage records carry
    # Anthropic-style cache keys, so the same four fields apply; OpenAI lists
    # cache writes at 1.25x input.
    "gpt-6.1-sol": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.10,
        "cache_create": 2.50,
    },
    "gpt-6-astra": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 1.00,
        "cache_create": 12.50,
    },
    "gpt-6-luna": {
        "input": 0.10,
        "output": 0.50,
        "cache_read": 0.01,
        "cache_create": 0.125,
    },
    # Superseded by gpt-6.1-sol; kept so older session records still price.
    # Published rates, developers.openai.com/api/docs/models/gpt-6-sol (2026-09-25).
    "gpt-6-sol": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.20,
        "cache_create": 2.50,
    },
    # Superseded by gpt-6-sol; kept so older session records still price.
    # Promotional through 2026-11-21 (see SOL_STANDARD_FROM below); the standard
    # rate returns after that date.
    "gpt-5.6-sol": {
        "input": 4.00,
        "output": 20.00,
        "cache_read": 0.40,
        "cache_create": 5.00,
    },
    # Fable 5.1 cache reads bill at 0.025x input.
    "claude-fable-5-1": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 0.25,
        "cache_create": 12.50,
    },
    "claude-fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 1.00,
        "cache_create": 12.50,
    },
    # Opus 5.5 and Sonnet 5.5 cache reads bill at 0.05x input, not the usual 0.1x.
    "claude-opus-5-5": {
        "input": 4.00,
        "output": 20.00,
        "cache_read": 0.20,
        "cache_create": 5.00,
    },
    "claude-sonnet-5-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.10,
        "cache_create": 2.50,
    },
    # Haiku 5.5 rates for prompts up to 100K tokens; HAIKU_5_5_LONG_PROMPT
    # below applies above that.
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_read": 0.01,
        "cache_create": 0.125,
    },
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_create": 6.25,
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
# Anthropic announced $3/$15 for Sonnet 5 from 2026-09-01, then kept $2/$10 as
# the standard price; records on either side of that date bill the same.
SONNET_5_STANDARD_PRICING = dict(PRICING["claude-sonnet-5"])
SONNET_5_STANDARD_FROM = datetime(2026, 9, 1, tzinfo=timezone.utc)
# The Sol promotional rate (20% off input, 33% off output) was announced as
# lasting at least through 2026-11-21; records after that date bill at the
# pre-promotion standard rate. Cached input is the usual 10% of input.
SOL_STANDARD_PRICING = {
    "input": 5.00,
    "output": 30.00,
    "cache_read": 0.50,
    "cache_create": 6.25,
}
SOL_STANDARD_FROM = datetime(2026, 11, 22, tzinfo=timezone.utc)
PROMOTIONS = (
    ("claude-sonnet-5", SONNET_5_STANDARD_FROM, SONNET_5_STANDARD_PRICING),
    ("gpt-5.6-sol", SOL_STANDARD_FROM, SOL_STANDARD_PRICING),
)

# Haiku 5.5 bills a request whose prompt (input plus cache reads and writes)
# is over 100K tokens at these rates, for the whole request.
HAIKU_5_5_PROMPT_LIMIT = 100_000
HAIKU_5_5_LONG_PROMPT = {
    "input": 0.50,
    "output": 2.50,
    "cache_read": 0.05,
    "cache_create": 0.625,
}
# GPT-6 family: a prompt over 272K input tokens bills 2x input and cache and
# 1.5x output for the full request.
GPT_6_PROMPT_LIMIT = 272_000
GPT_6_LONG_INPUT_FACTOR = 2.0
GPT_6_LONG_OUTPUT_FACTOR = 1.5
_GPT_6_FAMILY = re.compile(r"gpt-6(?:\.\d+)?-")


def parse_record_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_selector(model: str, selector: str) -> bool:
    """The selector itself or its dated `-YYYYMMDD` form, never a longer name."""
    return model == selector or re.fullmatch(re.escape(selector) + r"-\d{8}", model) is not None


def _long_prompt(model: str, base: dict[str, float], prompt_tokens: int | None) -> dict[str, float]:
    if prompt_tokens is None:
        return base
    if _is_selector(model, "claude-haiku-5-5") and prompt_tokens > HAIKU_5_5_PROMPT_LIMIT:
        return dict(HAIKU_5_5_LONG_PROMPT)
    if _GPT_6_FAMILY.match(model) and prompt_tokens > GPT_6_PROMPT_LIMIT:
        return {
            "input": base["input"] * GPT_6_LONG_INPUT_FACTOR,
            "output": base["output"] * GPT_6_LONG_OUTPUT_FACTOR,
            "cache_read": base["cache_read"] * GPT_6_LONG_INPUT_FACTOR,
            "cache_create": base["cache_create"] * GPT_6_LONG_INPUT_FACTOR,
        }
    return base


def get_pricing(
    model: str,
    timestamp: object = None,
    *,
    require_timestamp: bool = False,
    prompt_tokens: int | None = None,
) -> dict[str, float] | None:
    """Return pricing; promotional models use the record's absolute time.

    A promotion applies only to its exact selector (or the dated form), so a
    newer model whose name extends an older one never inherits its schedule.
    `prompt_tokens` selects the long-prompt tier where a model has one.
    """
    for selector, standard_from, standard in PROMOTIONS:
        if _is_selector(model, selector):
            when = parse_record_time(timestamp)
            if when is None:
                if require_timestamp:
                    return None
                when = datetime.now(timezone.utc)
            if when >= standard_from:
                return dict(standard)
            return dict(PRICING[selector])
    base = PRICING.get(model)
    if base is None:
        for key in sorted(PRICING, key=len, reverse=True):
            if model.startswith(key):
                base = PRICING[key]
                break
    if base is None:
        return None
    return _long_prompt(model, dict(base), prompt_tokens)


def compute_cost(
    usage: dict[str, object],
    model: str,
    timestamp: object = None,
) -> float:
    input_tokens = int(usage.get("input_tokens", 0))
    cache_read = int(usage.get("cache_read_input_tokens", 0))
    cache_create = int(usage.get("cache_creation_input_tokens", 0))
    pricing = get_pricing(
        model,
        timestamp,
        require_timestamp=True,
        prompt_tokens=input_tokens + cache_read + cache_create,
    )
    if pricing is None:
        return 0.0
    return (
        input_tokens * pricing["input"] / 1_000_000
        + int(usage.get("output_tokens", 0)) * pricing["output"] / 1_000_000
        + cache_read * pricing["cache_read"] / 1_000_000
        + cache_create * pricing["cache_create"] / 1_000_000
    )
