"""Core transition result, version 1.0.0.

``step`` will eventually return ``(observation, reward, terminated, truncated, info)``.
Phase 0 freezes that result and the pure reward and termination rules.
Privileged evaluator diagnostics are a separate type. ``deliver_to_policy``
refuses to pass them to a policy adapter.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptivehoneypotenv.contracts.actions import Action
from adaptivehoneypotenv.contracts.limits import (
    COMPROMISE_PENALTY,
    DECOY_COST_EACH,
    DETECTION_BONUS,
    MAX_DECOYS,
    TEAM_GENERATED_TOKEN_BUDGET,
)
from adaptivehoneypotenv.contracts.observations import DefenderObservation
from adaptivehoneypotenv.contracts.versions import TRANSITION_SCHEMA_VERSION


class TerminationReason(str, Enum):
    genuine_compromise = "genuine_compromise"
    all_agents_finished = "all_agents_finished"
    attempt_exhaustion = "attempt_exhaustion"
    generated_token_exhaustion = "generated_token_exhaustion"


class TruncationReason(str, Enum):
    operator_kill = "operator_kill"
    external_wall_clock = "external_wall_clock"
    external_cost_cutoff = "external_cost_cutoff"


class RewardComponents(BaseModel):
    """Detection bonus, compromise penalty, and per-decoy cost, stored apart."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = TRANSITION_SCHEMA_VERSION
    detection_bonus: Decimal
    compromise_penalty: Decimal
    decoy_cost: Decimal
    newly_committed_decoys: Annotated[int, Field(ge=0, le=MAX_DECOYS)]

    @model_validator(mode="after")
    def magnitudes(self) -> RewardComponents:
        if self.detection_bonus not in (Decimal("0"), DETECTION_BONUS):
            raise ValueError("detection bonus is 0 or 1")
        if self.compromise_penalty not in (Decimal("0"), COMPROMISE_PENALTY):
            raise ValueError("compromise penalty is 0 or 1")
        expected = DECOY_COST_EACH * self.newly_committed_decoys
        if self.decoy_cost != expected:
            raise ValueError("decoy cost must be 0.02 per newly committed decoy")
        return self

    @property
    def total(self) -> Decimal:
        return self.detection_bonus - self.compromise_penalty - self.decoy_cost


def detection_before_compromise(
    *,
    engagement_round: int | None,
    compromise_round: int | None,
) -> bool:
    """True only when verified engagement is strictly earlier than compromise.

    A same-round pair is a tie with zero lead time and does not count.
    Engagement with no compromise counts. No engagement does not.
    """

    if engagement_round is not None and engagement_round < 0:
        raise ValueError("round indices are non-negative")
    if compromise_round is not None and compromise_round < 0:
        raise ValueError("round indices are non-negative")
    if engagement_round is None:
        return False
    if compromise_round is None:
        return True
    return engagement_round < compromise_round


def lead_time_rounds(
    *,
    engagement_round: int | None,
    compromise_round: int | None,
) -> int | None:
    """Rounds of warning, or None when lead time is undefined or censored.

    Same-round ties return 0. Engagement without compromise is censored,
    not infinite. Engagement after compromise returns None.
    """

    if engagement_round is None or compromise_round is None:
        return None
    if engagement_round < 0 or compromise_round < 0:
        raise ValueError("round indices are non-negative")
    if engagement_round < compromise_round:
        return compromise_round - engagement_round
    if engagement_round == compromise_round:
        return 0
    return None


def reward_components(
    *,
    detection_before_compromise_now: bool,
    genuine_compromise_now: bool,
    newly_committed_decoys: int,
    detection_already_counted: bool,
    compromise_already_counted: bool,
) -> RewardComponents:
    """Provisional detection-oriented reward. Each binary component fires once."""

    detection = (
        DETECTION_BONUS
        if detection_before_compromise_now and not detection_already_counted
        else Decimal("0")
    )
    penalty = (
        COMPROMISE_PENALTY
        if genuine_compromise_now and not compromise_already_counted
        else Decimal("0")
    )
    return RewardComponents(
        detection_bonus=detection,
        compromise_penalty=penalty,
        decoy_cost=DECOY_COST_EACH * newly_committed_decoys,
        newly_committed_decoys=newly_committed_decoys,
    )


def per_call_generated_token_cap(
    *,
    per_call_cap: int,
    remaining_team_tokens: int,
    parallel_calls: int,
) -> int:
    """Cap one of ``k`` parallel calls so the team token budget cannot be exceeded."""

    if per_call_cap < 1:
        raise ValueError("per-call cap must be positive")
    if remaining_team_tokens < 0 or remaining_team_tokens > TEAM_GENERATED_TOKEN_BUDGET:
        raise ValueError("remaining team tokens are outside the task budget")
    if parallel_calls < 1:
        raise ValueError("parallel_calls must be positive")
    share = remaining_team_tokens // parallel_calls
    return min(per_call_cap, share)


class EpisodeEnd(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    terminated: bool
    truncated: bool
    termination_reason: TerminationReason | None = None
    truncation_reason: TruncationReason | None = None

    @model_validator(mode="after")
    def flags(self) -> EpisodeEnd:
        if self.terminated and self.truncated:
            raise ValueError("a transition is terminated or truncated, not both")
        if self.terminated and self.termination_reason is None:
            raise ValueError("termination needs a reason")
        if self.truncated and self.truncation_reason is None:
            raise ValueError("truncation needs a reason")
        if not self.terminated and self.termination_reason is not None:
            raise ValueError("termination reason set without terminated")
        if not self.truncated and self.truncation_reason is not None:
            raise ValueError("truncation reason set without truncated")
        return self


def classify_stop(
    *,
    genuine_compromise: bool = False,
    all_agents_finished: bool = False,
    attempts_exhausted: bool = False,
    generated_tokens_exhausted: bool = False,
    operator_kill: bool = False,
    external_wall_clock: bool = False,
    external_cost_cutoff: bool = False,
) -> EpisodeEnd:
    """Task budgets terminate. External cutoffs truncate.

    Verified engagement is not an input. A catch does not end the episode.
    """

    if genuine_compromise:
        return EpisodeEnd(
            terminated=True,
            truncated=False,
            termination_reason=TerminationReason.genuine_compromise,
        )
    if all_agents_finished:
        return EpisodeEnd(
            terminated=True,
            truncated=False,
            termination_reason=TerminationReason.all_agents_finished,
        )
    if attempts_exhausted:
        return EpisodeEnd(
            terminated=True,
            truncated=False,
            termination_reason=TerminationReason.attempt_exhaustion,
        )
    if generated_tokens_exhausted:
        return EpisodeEnd(
            terminated=True,
            truncated=False,
            termination_reason=TerminationReason.generated_token_exhaustion,
        )
    if operator_kill:
        return EpisodeEnd(
            terminated=False,
            truncated=True,
            truncation_reason=TruncationReason.operator_kill,
        )
    if external_cost_cutoff:
        return EpisodeEnd(
            terminated=False,
            truncated=True,
            truncation_reason=TruncationReason.external_cost_cutoff,
        )
    if external_wall_clock:
        return EpisodeEnd(
            terminated=False,
            truncated=True,
            truncation_reason=TruncationReason.external_wall_clock,
        )
    return EpisodeEnd(terminated=False, truncated=False)


class ActorRefusal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: Annotated[str, Field(pattern=r"^attacker-[123]$")]
    refused: bool


class TransitionInfo(BaseModel):
    """Policy-facing info. Privileged diagnostics are not a field."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = TRANSITION_SCHEMA_VERSION
    action_mask: tuple[bool, ...]
    valid: bool
    invalid_reason: str | None = None
    refusals: tuple[ActorRefusal, ...] = ()
    termination_reason: TerminationReason | None = None
    truncation_reason: TruncationReason | None = None

    @model_validator(mode="after")
    def validity(self) -> TransitionInfo:
        if self.valid and self.invalid_reason is not None:
            raise ValueError("a valid transition has no invalid reason")
        if not self.valid and not self.invalid_reason:
            raise ValueError("an invalid transition needs a reason")
        return self


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = TRANSITION_SCHEMA_VERSION
    observation: DefenderObservation
    reward: Decimal
    reward_components: RewardComponents
    terminated: bool
    truncated: bool
    info: TransitionInfo

    @model_validator(mode="after")
    def consistent(self) -> StepResult:
        if self.reward != self.reward_components.total:
            raise ValueError("reward must equal the sum of its components")
        if self.info.action_mask != self.observation.safe_action_mask:
            raise ValueError("info.action_mask must mirror the observation mask")
        if self.terminated and self.truncated:
            raise ValueError("a transition is terminated or truncated, not both")
        return self


class PrivilegedEvaluatorDiagnostics(BaseModel):
    """Evaluator-only data. Policy adapters must never receive this object.

    References are ids, not secret bytes. The type is still forbidden on the
    policy surface because it identifies the private goal and registry.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = TRANSITION_SCHEMA_VERSION
    workflow_label: Literal["release", "backup"]
    genuine_account_ref: Annotated[str, Field(pattern=r"^ref_[a-z0-9_]{1,64}$")]
    registry_ref: Annotated[str, Field(pattern=r"^ref_[a-z0-9_]{1,64}$")]
    messageboard_ref: Annotated[str, Field(pattern=r"^ref_[a-z0-9_]{1,64}$")]
    protected_value_ref: Annotated[str, Field(pattern=r"^ref_[a-z0-9_]{1,64}$")]


class PolicyBoundaryError(RuntimeError):
    """Raised when privileged data is offered to a policy adapter."""


class DefenderPolicy(Protocol):
    """``act`` receives the safe observation and nothing else."""

    def act(self, observation: DefenderObservation) -> Action: ...


def deliver_to_policy(
    result: StepResult,
    diagnostics: PrivilegedEvaluatorDiagnostics | None = None,
) -> StepResult:
    """Return the policy-facing step result.

    A non-None diagnostics object is refused. The returned object has no
    field that can hold ``PrivilegedEvaluatorDiagnostics``.
    """

    if diagnostics is not None:
        raise PolicyBoundaryError(
            "privileged evaluator diagnostics cannot be delivered to a policy adapter"
        )
    return result
