"""Team attempt counter and generated-token accounting.

Reasoning tokens are not added again when the provider included them in the
completion total. A duplicate request id does not charge twice. A total that
does not match ``TokenUsage.generated_tokens`` marks accounting unavailable
and charges nothing further.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from adaptivehoneypotenv.contracts.limits import (
    TEAM_ATTEMPT_BUDGET,
    TEAM_GENERATED_TOKEN_BUDGET,
)
from adaptivehoneypotenv.contracts.transition import per_call_generated_token_cap
from adaptivehoneypotenv.model_api import TokenUsage


class TokenCharge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    charged: int
    remaining: int
    exhausted: bool
    accounting_available: bool
    duplicate: bool = False


class AttemptLedger:
    def __init__(self) -> None:
        self.used = 0

    @property
    def budget(self) -> int:
        return TEAM_ATTEMPT_BUDGET

    @property
    def remaining(self) -> int:
        return TEAM_ATTEMPT_BUDGET - self.used

    def try_consume(self) -> int | None:
        """Consume one attempt. Return its 1-based index, or None if none remain."""

        if self.used >= TEAM_ATTEMPT_BUDGET:
            return None
        self.used += 1
        return self.used


class TokenLedger:
    def __init__(self) -> None:
        self.used = 0
        self.available = True
        self._charges: dict[str, TokenCharge] = {}

    @property
    def budget(self) -> int:
        return TEAM_GENERATED_TOKEN_BUDGET

    @property
    def remaining(self) -> int:
        if self.used >= TEAM_GENERATED_TOKEN_BUDGET:
            return 0
        return TEAM_GENERATED_TOKEN_BUDGET - self.used

    @property
    def exhausted(self) -> bool:
        return self.used >= TEAM_GENERATED_TOKEN_BUDGET

    def account(
        self,
        usage: TokenUsage,
        *,
        request_id: str,
        reported_generated: int | None = None,
    ) -> TokenCharge:
        previous = self._charges.get(request_id)
        if previous is not None:
            return previous.model_copy(update={"duplicate": True})
        computed = usage.generated_tokens
        if not self.available or (
            reported_generated is not None and reported_generated != computed
        ):
            self.available = False
            charge = self._charge(
                request_id=request_id,
                charged=0,
                available=False,
            )
            self._charges[request_id] = charge
            return charge
        self.used += computed
        charge = self._charge(request_id=request_id, charged=computed, available=True)
        self._charges[request_id] = charge
        return charge

    def per_call_cap(self, *, per_call_cap: int, parallel_calls: int) -> int:
        return per_call_generated_token_cap(
            per_call_cap=per_call_cap,
            remaining_team_tokens=self.remaining,
            parallel_calls=parallel_calls,
        )

    def _charge(self, *, request_id: str, charged: int, available: bool) -> TokenCharge:
        return TokenCharge(
            request_id=request_id,
            charged=charged,
            remaining=self.remaining,
            exhausted=self.exhausted,
            accounting_available=available,
            duplicate=False,
        )
