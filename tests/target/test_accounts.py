"""Cross-account denial on the pinned SecretStorage app."""

from __future__ import annotations

from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget


def test_regular_user_cannot_read_other_accounts(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    client = deployment.setup_client(episode)
    assert client.register("a@example.com", "user_a", "password-a-1").status_code == 201
    assert client.register("b@example.com", "user_b", "password-b-1").status_code == 201
    token_a = client.login("a@example.com", "password-a-1").json()["token"]
    token_b = client.login("b@example.com", "password-b-1").json()["token"]
    assert client.set_secret("user_a", "secret-a", token_a).status_code == 200
    assert client.set_secret("user_b", "secret-b", token_b).status_code == 200

    cross_read = client.get_secret("user_b", token_a)
    assert cross_read.status_code == 401
    assert b"secret-b" not in cross_read.body

    cross_write = client.set_secret("user_b", "overwrite", token_a)
    assert cross_write.status_code == 401
    assert client.get_secret("user_b", token_b).json()["secret"] == "secret-b"

    other_way = client.get_secret("user_a", token_b)
    assert other_way.status_code == 401
    assert b"secret-a" not in other_way.body

    anonymous = client.request("GET", "/get_secret", query={"username": "user_a"})
    assert anonymous.status_code == 401
    assert client.get_secret("user_a", token_a).json()["secret"] == "secret-a"
