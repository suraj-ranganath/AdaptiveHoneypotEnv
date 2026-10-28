"""Episode start consumes the frozen event envelope and source pins."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from adaptivehoneypotenv.contracts.events import (
    EpisodeStarted,
    compute_event_id,
    project_defender,
    project_operator,
)
from adaptivehoneypotenv.deployment import (
    AGENTENV_GIT_SHA,
    BRIDGE_IMAGE,
    HONEYVAL_GIT_SHA,
    TARGET_IMAGE,
    Deployment,
    EpisodeTarget,
)

ROOT = Path(__file__).resolve().parents[2]
_EPISODE_ID = re.compile(r"^ep_[A-Za-z0-9_-]{8,64}$")


def test_create_emits_episode_started_and_source_pins(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    assert _EPISODE_ID.fullmatch(episode.episode_id)
    event = episode.started_event
    assert isinstance(event, EpisodeStarted)
    assert event.kind == "episode_started"
    assert event.episode_id == episode.episode_id
    assert event.sequence == 0
    assert event.team == "trio"
    assert event.scenario_id == "secret_store_ops/v1"
    assert event.event_id == compute_event_id(event.episode_id, 0, "episode_started")
    assert event.actor.role == "controller"
    assert event.actor.actor_id == "controller"
    rendered = event.model_dump_json()
    assert episode.controller_token not in rendered
    assert "APP_SECRET" not in rendered

    operator = project_operator(event)
    assert operator.kind == "episode_started"
    assert operator.actor_role == "controller"
    defender = project_defender(event)
    assert defender is not None
    assert defender.kind == "episode_started"

    pins = deployment.source_pins()
    assert pins.honeyval_git_sha == HONEYVAL_GIT_SHA
    assert pins.agentenv_git_sha == AGENTENV_GIT_SHA
    assert pins.target_image_digest == deployment._client.images.get(TARGET_IMAGE).id
    assert pins.bridge_image_digest == deployment._client.images.get(BRIDGE_IMAGE).id
    lock_hash = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    assert pins.lock_sha256 == lock_hash
    assert episode.controller_token not in pins.model_dump_json()
