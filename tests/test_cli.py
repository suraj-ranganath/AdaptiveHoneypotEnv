"""Live episode orchestration with stubbed core/provider; no billable calls."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from adaptivehoneypotenv import cli
from adaptivehoneypotenv.contracts.transition import (
    StepResult,
    TerminationReason,
    TransitionInfo,
    TruncationReason,
    reward_components,
)
from adaptivehoneypotenv.env import EpisodeCore
from tests.support import sample_observation

LIVE_ARGS = [
    "run",
    "--defender",
    "live",
    "--attacker-max-tokens",
    "512",
    "--defender-max-tokens",
    "256",
    "--max-cost-usd",
    "5",
]


def transition(
    reason: TerminationReason | TruncationReason | None = None,
    *,
    invalid_reason: str | None = None,
    detected: bool = False,
) -> StepResult:
    observation = sample_observation()
    components = reward_components(
        detection_before_compromise_now=detected,
        genuine_compromise_now=reason is TerminationReason.genuine_compromise,
        newly_committed_decoys=0,
        detection_already_counted=False,
        compromise_already_counted=False,
    )
    termination = reason if isinstance(reason, TerminationReason) else None
    truncation = reason if isinstance(reason, TruncationReason) else None
    return StepResult(
        observation=observation,
        reward=components.total,
        reward_components=components,
        terminated=termination is not None,
        truncated=truncation is not None,
        info=TransitionInfo(
            action_mask=observation.safe_action_mask,
            valid=invalid_reason is None,
            invalid_reason=invalid_reason,
            termination_reason=termination,
            truncation_reason=truncation,
        ),
    )


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock, Mock]:
    core = Mock(spec=EpisodeCore)
    core.episode_id = "ep_cli_test"
    core.journal_directory.return_value = tmp_path / "journal"
    core.messageboard_directory.return_value = None
    core.mint_action_id.side_effect = [f"act_{index:08d}" for index in range(10)]
    factory = Mock(return_value=core)
    adapters = Mock(side_effect=[object(), object()])
    monkeypatch.setattr(cli, "EpisodeCore", factory)
    monkeypatch.setattr(cli, "_RUNS", tmp_path)
    monkeypatch.setattr("adaptivehoneypotenv.models.adapter.OpenAICompatibleAdapter", adapters)
    return core, factory, adapters


@pytest.mark.parametrize("reason", [*TerminationReason, *TruncationReason])
def test_live_repeats_until_episode_end(
    runtime: tuple[Mock, Mock, Mock],
    reason: TerminationReason | TruncationReason,
    capsys: pytest.CaptureFixture[str],
) -> None:
    core, factory, adapters = runtime
    # A detection is useful but must not end the team or reset its state.
    core.step_defender.side_effect = [transition(), transition(detected=True), transition(reason)]
    assert cli.main([*LIVE_ARGS, "--seed", "23", "--messageboard", "swarmchat"]) == 0
    core.reset.assert_called_once_with(23)
    core.close.assert_called_once()
    core.kill.assert_not_called()
    assert factory.call_count == 1
    assert factory.call_args.kwargs["messageboard_backend"] == "swarmchat"
    assert adapters.call_count == 2
    assert adapters.call_args_list[0].args[0] is adapters.call_args_list[1].args[0]
    calls = core.step_defender.call_args_list
    assert len(calls) == 3
    assert calls[0].args[0] is calls[1].args[0] is calls[2].args[0]
    assert len({call.args[1] for call in calls}) == 3
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary["defender_transitions"] == 3
    assert summary["valid"] is True
    assert summary["terminated"] is isinstance(reason, TerminationReason)
    assert summary["truncated"] is isinstance(reason, TruncationReason)
    assert (summary["termination_reason"] or summary["truncation_reason"]) == reason.value


@pytest.mark.parametrize("completed_before_failure", [0, 2])
def test_invalid_run_stops_even_without_end_flags(
    runtime: tuple[Mock, Mock, Mock],
    completed_before_failure: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    core, _, _ = runtime
    core.step_defender.side_effect = [transition()] * completed_before_failure + [
        transition(invalid_reason="attacker_provider_error")
    ]
    assert cli.main(LIVE_ARGS) == 1
    assert core.step_defender.call_count == completed_before_failure + 1
    core.close.assert_called_once()
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary["valid"] is False
    assert summary["terminated"] is summary["truncated"] is False
    assert summary["invalid_reason"] == "attacker_provider_error"


def test_ctrl_c_records_kill_and_closes(runtime: tuple[Mock, Mock, Mock]) -> None:
    core, _, _ = runtime
    core.step_defender.side_effect = [transition(), KeyboardInterrupt()]
    lifecycle = Mock()
    lifecycle.attach_mock(core.kill, "kill")
    lifecycle.attach_mock(core.close, "close")
    assert cli.main(LIVE_ARGS) == 130
    assert [call[0] for call in lifecycle.mock_calls] == ["kill", "close"]
    assert core.step_defender.call_count == 2


def test_reset_failure_closes_without_model_step(runtime: tuple[Mock, Mock, Mock]) -> None:
    core, _, _ = runtime
    core.reset.side_effect = RuntimeError("setup failed")
    assert cli.main(LIVE_ARGS) == 1
    core.step_defender.assert_not_called()
    core.close.assert_called_once()


def test_unexpected_error_still_closes(runtime: tuple[Mock, Mock, Mock]) -> None:
    core, _, _ = runtime
    core.step_defender.side_effect = [transition(), RuntimeError("journal unavailable")]
    with pytest.raises(RuntimeError, match="journal unavailable"):
        cli.main(LIVE_ARGS)
    core.close.assert_called_once()


def test_scripted_smoke_stays_bounded(runtime: tuple[Mock, Mock, Mock]) -> None:
    core, _, adapters = runtime
    core.step_defender.return_value = transition()
    assert cli.main(["run", "--defender", "scripted"]) == 0
    core.step_defender.assert_called_once()
    core.close.assert_called_once()
    adapters.assert_not_called()


def test_missing_caps_prevent_start(runtime: tuple[Mock, Mock, Mock]) -> None:
    core, factory, adapters = runtime
    assert cli.main(["run", "--defender", "live"]) == 2
    factory.assert_not_called()
    adapters.assert_not_called()
    core.reset.assert_not_called()
