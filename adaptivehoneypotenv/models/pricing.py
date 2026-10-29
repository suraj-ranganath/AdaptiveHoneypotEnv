"""Cost estimate and provider usage parsing.

``usage.cost`` from OpenRouter is the billed amount when it is present and
non-negative. When it is absent, the price table is a ceiling, not a quote.

Published figures checked while writing this adapter (they move, and
aggregators disagreed): OpenRouter list prices for ``z-ai/glm-5.3-flash``
were well under $0.20 per million output tokens, and a Z.AI output quote was
about $0.50 per million. The table below is intentionally higher so a missing
invoice cannot under-count the cap. Successful calls replace the pre-call
reservation with the billed amount.
"""

from __future__ import annotations

import math
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal

from adaptivehoneypotenv.model_api import ChatCompletionRequest, TokenUsage

# USD per million tokens. Ceilings, not the invoice.
INPUT_USD_PER_MILLION = Decimal("1.00")
OUTPUT_USD_PER_MILLION = Decimal("5.00")
_QUANTUM = Decimal("0.000000000001")
CostSource = Literal["provider", "price_table"]


def ceil_money(amount: Decimal) -> Decimal:
    if not amount.is_finite() or amount < 0:
        raise ValueError("money must be a non-negative finite decimal")
    return amount.quantize(_QUANTUM, rounding=ROUND_CEILING)


def worst_case_cost_usd(*, max_tokens: int, prompt_tokens_estimate: int) -> Decimal:
    """Upper bound used to refuse a call that could cross the cap.

    Output is ``max_tokens`` times the output ceiling. Prompt tokens are
    estimated high and priced at the input ceiling so a large history cannot
    hide outside the check.
    """

    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    if prompt_tokens_estimate < 0:
        raise ValueError("prompt estimate cannot be negative")
    output = Decimal(max_tokens) * OUTPUT_USD_PER_MILLION / Decimal(1_000_000)
    prompt = Decimal(prompt_tokens_estimate) * INPUT_USD_PER_MILLION / Decimal(1_000_000)
    return ceil_money(output + prompt)


def price_table_cost(usage: TokenUsage) -> Decimal:
    prompt = Decimal(usage.prompt_tokens) * INPUT_USD_PER_MILLION / Decimal(1_000_000)
    generated = Decimal(usage.generated_tokens) * OUTPUT_USD_PER_MILLION / Decimal(1_000_000)
    return ceil_money(prompt + generated)


def estimate_prompt_tokens(request: ChatCompletionRequest, extra: str = "") -> int:
    """Conservative prompt-token estimate: two UTF-8 bytes per token."""

    blob = request.model_dump_json() + extra
    return max(1, (len(blob.encode("utf-8")) + 1) // 2)


def parse_cost(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            return None
        amount = Decimal(str(value))
    elif isinstance(value, str):
        try:
            amount = Decimal(value)
        except ArithmeticError:
            return None
    else:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return ceil_money(amount)


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    return value


def _reasoning_tokens(usage: dict[str, Any]) -> int:
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict):
        parsed = _nonnegative_int(details.get("reasoning_tokens"))
        if parsed is not None:
            return parsed
    parsed = _nonnegative_int(usage.get("reasoning_tokens"))
    return parsed or 0


def usage_from_payload(payload: dict[str, Any]) -> tuple[TokenUsage, bool] | None:
    """Return usage and whether the reasoning overlap reconciled.

    OpenAI-style responses include reasoning inside ``completion_tokens``
    (``total == prompt + completion``). A total that equals prompt +
    completion + reasoning means the two figures are separate and must both
    count. Any other shape is marked unavailable so the run is excluded from
    token-budget comparisons. The returned :class:`TokenUsage` still follows
    the overlap flag and does not add the same reasoning tokens twice when
    the total shows they were included.
    """

    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return None
    prompt = _nonnegative_int(raw.get("prompt_tokens"))
    completion = _nonnegative_int(raw.get("completion_tokens"))
    if prompt is None or completion is None:
        return None
    reasoning = _reasoning_tokens(raw)
    total = _nonnegative_int(raw["total_tokens"]) if "total_tokens" in raw else None
    if total is None:
        included = reasoning <= completion
        return (
            TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                reasoning_tokens=reasoning,
                reasoning_included_in_completion=included,
            ),
            included or reasoning == 0,
        )
    if total == prompt + completion:
        reconciled = reasoning <= completion
        return (
            TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                reasoning_tokens=reasoning,
                reasoning_included_in_completion=True,
            ),
            reconciled,
        )
    if reasoning > 0 and total == prompt + completion + reasoning:
        return (
            TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                reasoning_tokens=reasoning,
                reasoning_included_in_completion=False,
            ),
            True,
        )
    included = reasoning <= completion
    return (
        TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            reasoning_tokens=reasoning,
            reasoning_included_in_completion=included,
        ),
        False,
    )


def provider_cost(payload: dict[str, Any]) -> Decimal | None:
    """OpenRouter bills ``usage.cost`` in USD. Missing or negative is unknown."""

    raw = payload.get("usage")
    if not isinstance(raw, dict) or "cost" not in raw:
        return None
    return parse_cost(raw.get("cost"))
