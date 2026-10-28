"""Shared fixtures for gate A target and containment tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def deployment() -> Iterator[Deployment]:
    launcher = Deployment(repo_root=REPO_ROOT)
    launcher.ensure_images()
    try:
        yield launcher
    finally:
        launcher.close()


@pytest.fixture
def episode(deployment: Deployment) -> Iterator[EpisodeTarget]:
    created = deployment.create_episode_target()
    try:
        yield created
    finally:
        deployment.destroy(created)
