"""Adapter failures. None of these are a defender win.

Cost cutoff truncates the episode. Team generated-token exhaustion terminates
it as a task budget. Provider and credential failures invalidate the run.
Messages are safe to log: they never include the provider key.
"""

from __future__ import annotations

from decimal import Decimal

from adaptivehoneypotenv.contracts.transition import EpisodeEnd, classify_stop


class ModelAdapterError(Exception):
    """Base error for the live model adapter."""

    counts_as_defender_win: bool = False
    invalidates_run: bool = False


class CostCapExceeded(ModelAdapterError):
    """The next call could spend past ``max_cost_usd``.

    The core treats this as ``external_cost_cutoff`` truncation. It is a clean
    stop, not a defender win and not an attacker failure.
    """

    def __init__(
        self,
        *,
        spent_usd: Decimal,
        cap_usd: Decimal,
        estimated_usd: Decimal,
    ) -> None:
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd
        self.estimated_usd = estimated_usd
        super().__init__(
            "cost cap exceeded: "
            f"spent_usd={spent_usd} estimated_usd={estimated_usd} cap_usd={cap_usd}"
        )

    def as_episode_end(self) -> EpisodeEnd:
        return classify_stop(external_cost_cutoff=True)


class TeamGeneratedTokenBudgetExhausted(ModelAdapterError):
    """The attacker team cannot fund another generated-token call.

    Defender calls do not raise this. The core terminates for task
    generated-token exhaustion. That is not a defender win.
    """

    def __init__(self, *, spent_tokens: int, budget: int) -> None:
        self.spent_tokens = spent_tokens
        self.budget = budget
        super().__init__(
            f"team generated-token budget exhausted: spent={spent_tokens} budget={budget}"
        )

    def as_episode_end(self) -> EpisodeEnd:
        return classify_stop(generated_tokens_exhausted=True)


class MissingProviderCredential(ModelAdapterError):
    """The provider credential is missing or unusable. The value is not echoed."""

    invalidates_run = True


class ScriptedAdapterRejected(ModelAdapterError):
    """This package does not construct the scripted test double."""

    invalidates_run = True

    def __init__(self, purpose: str) -> None:
        super().__init__(
            "scripted_test_double is rejected "
            f"(purpose={purpose}); live and scored manifests require openai_compatible"
        )


class ProviderRequestError(ModelAdapterError):
    """A non-retryable provider response. Invalidates the run."""

    invalidates_run = True

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ProviderTransportExhausted(ModelAdapterError):
    """Bounded 429/5xx/timeout retries were used up. Invalidates the run."""

    invalidates_run = True

    def __init__(self, message: str, *, attempts: int) -> None:
        self.attempts = attempts
        super().__init__(message)


class LedgerError(ModelAdapterError):
    """The spend ledger cannot be read or safely updated."""

    invalidates_run = True
