"""Fresh process, database, and APP_SECRET on every episode."""

from __future__ import annotations

from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget


def test_reset_has_fresh_database_and_runtime_state(deployment: Deployment) -> None:
    first = deployment.create_episode_target()
    try:
        assert deployment.secret_is_strong(first)
        fingerprint = deployment.secret_fingerprint(first)
        setup = deployment.setup_client(first)
        created = setup.register("reset-a@example.com", "reset_a", "reset-password-a")
        assert created.status_code == 201, created.body
        assert deployment.user_count(first) == 1
        first_id = first.target_container_id
        first_endpoint = first.bridge_endpoint
        first_token = first.controller_token
        _assert_runtime_is_contained(deployment, first)
    finally:
        deployment.destroy(first)

    second = deployment.create_episode_target()
    try:
        assert second.target_container_id != first_id
        assert second.bridge_endpoint != first_endpoint
        assert second.controller_token != first_token
        assert deployment.secret_is_strong(second)
        assert deployment.secret_fingerprint(second) != fingerprint
        assert deployment.user_count(second) == 0
        stale = deployment.setup_client(second).login("reset-a@example.com", "reset-password-a")
        assert stale.status_code == 401
        again = deployment.setup_client(second).register(
            "reset-a@example.com", "reset_a", "reset-password-a"
        )
        assert again.status_code == 201, again.body
        _assert_runtime_is_contained(deployment, second)
    finally:
        deployment.destroy(second)


def _assert_runtime_is_contained(deployment: Deployment, episode: EpisodeTarget) -> None:
    facts = deployment.containment_facts(episode)
    assert facts["network_internal"] is True
    assert facts["relay_host"] == "127.0.0.1"
    for role in ("target", "bridge"):
        item = facts[role]
        assert item["privileged"] is False
        assert item["readonly_rootfs"] is True
        assert "ALL" in item["cap_drop"]
        assert any("no-new-privileges" in value for value in item["security_opt"])
        assert item["port_bindings"] in (None, {})
        assert not item["binds"]
        assert item["network_mode"] != "host"
        assert item["pids_limit"] == 64
        blob = " ".join(item["mount_sources"] + item["binds"] + item["env_names"])
        assert "docker.sock" not in blob
    assert "APP_SECRET" in facts["target"]["env_names"]
    assert "CONTROLLER_TOKEN" not in facts["target"]["env_names"]
    assert "APP_SECRET" not in facts["bridge"]["env_names"]
    assert "CONTROLLER_TOKEN" in facts["bridge"]["env_names"]
    forbidden = {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    assert forbidden.isdisjoint(facts["target"]["env_names"])
    assert forbidden.isdisjoint(facts["bridge"]["env_names"])
    readonly = deployment.admin_exec(
        episode,
        [
            "python",
            "-c",
            "p='/opt/secretstorage/app.py'\n"
            "try:\n"
            "    open(p, 'a').close()\n"
            "    print('writable')\n"
            "except OSError:\n"
            "    print('readonly')\n",
        ],
    )
    assert readonly.exit_code == 0
    assert readonly.stdout.decode().strip() == "readonly"
