"""Setup checks do not mutate accounts, and destroy removes the target."""

from __future__ import annotations

import urllib.parse
from http.client import HTTPConnection

import pytest
from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget
from docker.errors import NotFound


def test_setup_checks_leave_no_extra_accounts_or_mutations(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    client = deployment.setup_client(episode)
    assert deployment.user_count(episode) == 0
    assert client.login("nobody@example.com", "not-a-password").status_code == 401
    missing = client.get_secret("nobody", "not-a-token")
    assert missing.status_code == 401
    assert deployment.user_count(episode) == 0

    created = client.register("setup@example.com", "setup_user", "setup-password")
    assert created.status_code == 201, created.body
    logged_in = client.login("setup@example.com", "setup-password")
    assert logged_in.status_code == 200, logged_in.body
    token = logged_in.json()["token"]
    assert client.set_secret("setup_user", "setup-secret", token).status_code == 200
    duplicate = client.register("setup@example.com", "setup_user", "setup-password")
    assert duplicate.status_code == 400
    assert client.login("setup@example.com", "wrong-password").status_code == 401
    assert deployment.user_count(episode) == 1
    assert client.get_secret("setup_user", token).json()["secret"] == "setup-secret"


def test_kill_stops_dispatch_and_destroys_target(deployment: Deployment) -> None:
    episode = deployment.create_episode_target()
    endpoint = urllib.parse.urlsplit(episode.bridge_endpoint)
    target_id = episode.target_container_id
    bridge_id = episode.bridge_container_id
    network_id = episode.network_id
    deployment.destroy(episode)

    with pytest.raises(NotFound):
        deployment._client.containers.get(target_id)
    with pytest.raises(NotFound):
        deployment._client.containers.get(bridge_id)
    with pytest.raises(NotFound):
        deployment._client.networks.get(network_id)

    try:
        connection = HTTPConnection(endpoint.hostname, endpoint.port, timeout=2)
        connection.request("GET", "/actor/login")
        connection.getresponse()
        reachable = True
    except OSError:
        reachable = False
    finally:
        try:
            connection.close()
        except Exception:
            pass
    assert reachable is False
