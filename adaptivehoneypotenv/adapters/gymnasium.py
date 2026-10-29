"""Gymnasium-style reset and step over the shared core.

This module does not import Gymnasium and does not score or schedule.
Index 0 is wait. An out-of-range index is a no-op that still advances.
"""

from __future__ import annotations

from typing import Any

from adaptivehoneypotenv.contracts.actions import Action, DeployAction, WaitAction
from adaptivehoneypotenv.contracts.catalogue import DiscreteCatalogue
from adaptivehoneypotenv.contracts.transition import deliver_to_policy
from adaptivehoneypotenv.env import EpisodeCore


def action_from_index(catalogue: DiscreteCatalogue, index: int) -> Action | None:
    if index < 0 or index >= len(catalogue.plans):
        return None
    plan = catalogue.plans[index]
    if plan.kind == "wait":
        return WaitAction(kind="wait")
    return DeployAction(kind="deploy", decoys=plan.specs)


class GymnasiumAdapter:
    """Maps core results to ``(observation, reward, terminated, truncated, info)``."""

    def __init__(self, core: EpisodeCore) -> None:
        self._core = core

    def reset(self, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
        observation, info = self._core.reset(seed)
        return observation.model_dump(mode="json"), info.model_dump(mode="json")

    def step(
        self, action: Action | int | None
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        chosen = (
            action_from_index(self._core.catalogue, action) if isinstance(action, int) else action
        )
        result = deliver_to_policy(self._core.step(chosen, self._core.mint_action_id()))
        return (
            result.observation.model_dump(mode="json"),
            float(result.reward),
            result.terminated,
            result.truncated,
            result.info.model_dump(mode="json"),
        )

    def close(self) -> None:
        self._core.close()
