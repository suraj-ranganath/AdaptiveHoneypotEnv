"""SQLite restore keeps the process and the in-memory salt.

This target only has database state. Restore replaces that database and
leaves the process running.
"""

from __future__ import annotations

from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget


def test_rollback_restores_database_without_restart(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    client = deployment.setup_client(episode)
    assert client.register("keep-a@example.com", "keep_a", "password-keep-a").status_code == 201
    assert client.register("keep-b@example.com", "keep_b", "password-keep-b").status_code == 201
    token_a = client.login("keep-a@example.com", "password-keep-a").json()["token"]
    assert client.set_secret("keep_a", "alpha-secret", token_a).status_code == 200
    assert client.login("keep-b@example.com", "password-keep-b").status_code == 200

    pid = deployment.app_pid(episode)
    container_id = episode.target_container_id
    deployment.backup(episode)

    created = client.register("later-c@example.com", "later_c", "password-later-c")
    assert created.status_code == 201, created.body
    assert client.login("later-c@example.com", "password-later-c").status_code == 200
    assert deployment.user_count(episode) == 3

    deployment.restore(episode)

    assert deployment.app_pid(episode) == pid
    assert episode.target_container_id == container_id
    assert deployment.user_count(episode) == 2
    assert client.login("later-c@example.com", "password-later-c").status_code == 401

    restored = client.login("keep-a@example.com", "password-keep-a")
    assert restored.status_code == 200, restored.body
    assert client.get_secret("keep_a", restored.json()["token"]).json()["secret"] == "alpha-secret"
    assert client.login("keep-b@example.com", "password-keep-b").status_code == 200

    assert client.register("later-c@example.com", "later_c", "password-later-c").status_code == 201
