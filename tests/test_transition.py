"""Reward components, termination, and the policy boundary."""

from decimal import Decimal
from typing import get_args, get_type_hints

import pytest
from adaptivehoneypotenv.contracts.actions import DeployAction, WaitAction
from adaptivehoneypotenv.contracts.observations import DefenderObservation
from adaptivehoneypotenv.contracts.transition import (
    COMPROMISE_PENALTY,
    DefenderPolicy,
    EpisodeEnd,
    PolicyBoundaryError,
    PrivilegedEvaluatorDiagnostics,
    StepResult,
    TerminationReason,
    TransitionInfo,
    TruncationReason,
    classify_stop,
    deliver_to_policy,
    detection_before_compromise,
    lead_time_rounds,
    per_call_generated_token_cap,
    reward_components,
)
from tests.support import sample_observation


def test_repeated_trigger_does_not_repeat_reward() -> None:
    first = reward_components(
        detection_before_compromise_now=True,
        genuine_compromise_now=False,
        newly_committed_decoys=1,
        detection_already_counted=False,
        compromise_already_counted=False,
    )
    second = reward_components(
        detection_before_compromise_now=True,
        genuine_compromise_now=False,
        newly_committed_decoys=0,
        detection_already_counted=True,
        compromise_already_counted=False,
    )
    assert first.detection_bonus == Decimal("1")
    assert first.decoy_cost == Decimal("0.02")
    assert first.total == Decimal("0.98")
    assert second.detection_bonus == Decimal("0")
    assert second.total == Decimal("0")
    both = reward_components(
        detection_before_compromise_now=True,
        genuine_compromise_now=True,
        newly_committed_decoys=2,
        detection_already_counted=False,
        compromise_already_counted=False,
    )
    assert both.total == Decimal("1") - COMPROMISE_PENALTY - Decimal("0.04")


def test_same_round_engagement_and_compromise_is_a_tie() -> None:
    assert detection_before_compromise(engagement_round=3, compromise_round=3) is False
    assert lead_time_rounds(engagement_round=3, compromise_round=3) == 0
    assert detection_before_compromise(engagement_round=2, compromise_round=3) is True
    assert lead_time_rounds(engagement_round=2, compromise_round=3) == 1
    assert detection_before_compromise(engagement_round=4, compromise_round=None) is True
    assert lead_time_rounds(engagement_round=4, compromise_round=None) is None
    assert detection_before_compromise(engagement_round=None, compromise_round=1) is False
    tied = reward_components(
        detection_before_compromise_now=False,
        genuine_compromise_now=True,
        newly_committed_decoys=0,
        detection_already_counted=False,
        compromise_already_counted=False,
    )
    assert tied.detection_bonus == Decimal("0")
    assert tied.compromise_penalty == Decimal("1")


def test_parallel_calls_cannot_exceed_team_token_budget() -> None:
    cap = per_call_generated_token_cap(
        per_call_cap=8_000,
        remaining_team_tokens=100,
        parallel_calls=3,
    )
    assert cap == 33
    assert cap * 3 <= 100
    tighter = per_call_generated_token_cap(
        per_call_cap=10, remaining_team_tokens=100, parallel_calls=3
    )
    assert tighter == 10
    assert tighter * 3 <= 100
    solo = per_call_generated_token_cap(per_call_cap=50, remaining_team_tokens=40, parallel_calls=1)
    assert solo == 40


def test_trigger_does_not_end_swarm() -> None:
    names = {item.value for item in TerminationReason}
    assert "verified_engagement" not in names
    assert "decoy_authenticated" not in names
    assert classify_stop().terminated is False
    assert classify_stop().truncated is False
    caught = classify_stop()
    assert caught == EpisodeEnd(terminated=False, truncated=False)


def test_task_token_exhaustion_terminates_external_cutoff_truncates() -> None:
    tokens = classify_stop(generated_tokens_exhausted=True)
    assert tokens.terminated is True
    assert tokens.truncated is False
    assert tokens.termination_reason is TerminationReason.generated_token_exhaustion
    attempts = classify_stop(attempts_exhausted=True)
    assert attempts.termination_reason is TerminationReason.attempt_exhaustion
    cutoff = classify_stop(external_cost_cutoff=True)
    assert cutoff.terminated is False
    assert cutoff.truncated is True
    assert cutoff.truncation_reason is TruncationReason.external_cost_cutoff
    wall = classify_stop(external_wall_clock=True)
    assert wall.truncation_reason is TruncationReason.external_wall_clock
    compromise = classify_stop(genuine_compromise=True, external_cost_cutoff=True)
    assert compromise.termination_reason is TerminationReason.genuine_compromise
    assert compromise.truncated is False


def test_action_mask_reaches_policy_without_privileged_info() -> None:
    observation = sample_observation()
    components = reward_components(
        detection_before_compromise_now=False,
        genuine_compromise_now=False,
        newly_committed_decoys=0,
        detection_already_counted=False,
        compromise_already_counted=False,
    )
    result = StepResult(
        observation=observation,
        reward=components.total,
        reward_components=components,
        terminated=False,
        truncated=False,
        info=TransitionInfo(action_mask=observation.safe_action_mask, valid=True),
    )
    delivered = deliver_to_policy(result)
    assert delivered.info.action_mask == observation.safe_action_mask
    assert delivered.info.action_mask[0] is True
    diagnostics = PrivilegedEvaluatorDiagnostics(
        workflow_label="release",
        genuine_account_ref="ref_genuine_account",
        registry_ref="ref_registry",
        messageboard_ref="ref_messageboard",
        protected_value_ref="ref_protected",
    )
    with pytest.raises(PolicyBoundaryError):
        deliver_to_policy(result, diagnostics=diagnostics)
    hints = get_type_hints(DefenderPolicy.act)
    assert hints["observation"] is DefenderObservation
    assert set(get_args(hints["return"])) == {DeployAction, WaitAction}
    assert "diagnostics" not in hints
    for model in (StepResult, TransitionInfo, DefenderObservation):
        assert "diagnostics" not in model.model_fields
        assert "workflow_label" not in model.model_fields
        assert "messageboard_ref" not in model.model_fields
    waited = WaitAction(kind="wait")
    assert waited.kind == "wait"
