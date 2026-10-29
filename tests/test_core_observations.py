"""Multi-transition observation delivery through the real core and gateway."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from adaptivehoneypotenv.cli import _wait_result
from adaptivehoneypotenv.contracts.actions import WaitAction
from adaptivehoneypotenv.contracts.observations import DefenderObservation
from adaptivehoneypotenv.deployment import Deployment
from adaptivehoneypotenv.env import EpisodeCore, _Window
from adaptivehoneypotenv.events import ControllerLog
from adaptivehoneypotenv.gateway.gateway import ToolGateway
from adaptivehoneypotenv.gateway.upstream import LoopbackFixedUpstream
from adaptivehoneypotenv.policies import ScriptedDefender


@pytest.mark.parametrize("first_step_api", ["step", "step_defender"])
def test_previous_window_reaches_next_defender_without_old_activity_or_board_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first_step_api: str
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "source").mkdir(parents=True)
    for name in ("first", "second"):
        (workspace / "source" / f"{name}.txt").write_text(f"synthetic {name} content\n")
    gateway = ToolGateway(
        episode_id="ep_observations",
        workspace=workspace,
        upstream=LoopbackFixedUpstream("127.0.0.1", 1),
        controller_token="test-controller-token",
        journal_dir=tmp_path / "journal",
    )
    core = EpisodeCore(tmp_path / "runs", deployment=Mock(spec=Deployment))
    core._gateway = gateway
    core._log = ControllerLog(gateway)
    core._episode_id = "ep_observations"
    windows = iter(("first", "second"))

    def attacker_window() -> _Window:
        name = next(windows)
        for tool, arguments in (
            ("read_file", {"path": f"source/{name}.txt", "start_line": 1, "max_lines": 5}),
            ("post_to_messageboard", {"text": f"private {name} conversation"}),
        ):
            result = gateway.execute(
                actor_id="attacker-1",
                round_index=core._round,
                tool_name=tool,
                arguments=arguments,
            )
            assert result.episode_valid
        core._round += 1
        return _Window(
            attempts=2, refusals=(), cost_cutoff=False, token_cutoff=False, provider_error=False
        )

    monkeypatch.setattr(core, "_attacker_window", attacker_window)
    defender = ScriptedDefender([_wait_result(), _wait_result()])
    first_id = core.mint_action_id()
    try:
        assert core.observation().activity == ()
        if first_step_api == "step":
            first = core.step(WaitAction(kind="wait"), first_id)
        else:
            first = core.step_defender(defender, first_id)
        assert len(first.observation.activity) == 1
        assert first.observation.activity[0].normalized_path == "source/first.txt"
        assert first.observation.remaining_team_attempts == 88
        assert core.observation() == first.observation
        # An idempotent retry must neither consume observation nor rerun attackers.
        assert core.step_defender(defender, first_id) is first
        assert core.observation() == first.observation
        second = core.step_defender(defender, core.mint_action_id())
        seen = DefenderObservation.model_validate_json(
            core.defender_request_text().split("\n", 1)[1]
        )
        assert seen == first.observation
        assert "private first conversation" not in core.defender_request_text()
        assert len(second.observation.activity) == 1
        assert second.observation.activity[0].normalized_path == "source/second.txt"
        assert second.observation.remaining_team_attempts == 86
        assert core.observation() == second.observation
    finally:
        core.close()
