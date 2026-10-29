"""AgentEnv protocol adapter.

This calls the shared episode core. It has no second loop, scheduler, or scorer,
and it does not expose the deployment or privileged diagnostics.
"""

from __future__ import annotations

from adaptivehoneypotenv.contracts.actions import Action
from adaptivehoneypotenv.contracts.observations import DefenderObservation
from adaptivehoneypotenv.contracts.transition import StepResult, TransitionInfo, deliver_to_policy
from adaptivehoneypotenv.env import EpisodeCore
from adaptivehoneypotenv.model_api import ModelAdapter
from adaptivehoneypotenv.models.adapter import OpenAICompatibleAdapter


class SecretStoreOpsEnvironment:
    """Thin reset/step wrapper around one ``EpisodeCore``."""

    def __init__(self, core: EpisodeCore) -> None:
        self._core = core

    def reset(self, seed: int) -> tuple[DefenderObservation, TransitionInfo]:
        return self._core.reset(seed)

    def step(self, action: Action | None, action_id: str) -> StepResult:
        return deliver_to_policy(self._core.step(action, action_id))

    def step_defender(
        self,
        adapter: ModelAdapter | OpenAICompatibleAdapter,
        action_id: str,
    ) -> StepResult:
        return deliver_to_policy(self._core.step_defender(adapter, action_id))

    def close(self) -> None:
        self._core.close()
