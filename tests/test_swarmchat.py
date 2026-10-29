"""Real SwarmChat store/viewer plus gateway parity; no Docker or model calls."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from adaptivehoneypotenv.contracts.events import EpisodeStarted, compute_event_id, validate_journal
from adaptivehoneypotenv.deployment import Deployment, DeploymentError, EpisodeTarget
from adaptivehoneypotenv.env import EpisodeCore
from adaptivehoneypotenv.events import ControllerLog
from adaptivehoneypotenv.gateway.gateway import GatewayError, ToolGateway
from adaptivehoneypotenv.gateway.journal import JournalWriteError
from adaptivehoneypotenv.gateway.messageboard import Messageboard, MessageboardError
from adaptivehoneypotenv.gateway.upstream import LoopbackFixedUpstream
from adaptivehoneypotenv.integrations.swarmchat import SwarmChatMessageboard
from tests.support import envelope


@pytest.fixture
def swarm(tmp_path: Path) -> Iterator[SwarmChatMessageboard]:
    pytest.importorskip("swarmchat")
    board = SwarmChatMessageboard(tmp_path / "swarm", solo=False, episode_id="ep_swarmchat01")
    try:
        yield board
    finally:
        board.close()


def gateway(tmp_path: Path, board: Messageboard) -> ToolGateway:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return ToolGateway(
        episode_id="ep_swarmchat01",
        workspace=workspace,
        upstream=LoopbackFixedUpstream("127.0.0.1", 1),  # board calls must never dial the target
        controller_token="test-controller-token",
        messageboard=board,
        journal_dir=tmp_path / "journal",
    )


def invoke(gw: ToolGateway, actor: str, round_index: int, name: str, **args: Any) -> dict:
    result = gw.execute(actor_id=actor, round_index=round_index, tool_name=name, arguments=args)
    assert result.episode_valid
    return json.loads(result.content)


@pytest.mark.parametrize("backend", ["memory", "swarmchat"])
def test_board_gateway_round_visibility_and_private_projection(
    tmp_path: Path, backend: str
) -> None:
    if backend == "swarmchat":
        pytest.importorskip("swarmchat")
        board = SwarmChatMessageboard(tmp_path / "swarm", solo=False, episode_id="ep_swarmchat01")
    else:
        board = Messageboard(solo=False)
    gw = gateway(tmp_path, board)
    try:
        text = "Backup JWT discovered: synthetic-secret-🔒"
        posted = invoke(gw, "attacker-1", 0, "post_to_messageboard", text=text)
        assert posted["post_id"] == 1
        assert gw.actor_history("attacker-2") == ()
        assert invoke(gw, "attacker-2", 0, "read_messageboard", after_post_id=0)["posts"] == []
        read = invoke(gw, "attacker-2", 1, "read_messageboard", after_post_id=0)
        assert read["posts"][0]["text"] == text
        assert read["posts"][0]["author"] == "attacker-1"
        assert invoke(gw, "attacker-3", 1, "read_messageboard", after_post_id=1)["posts"] == []
        assert gw.attempts_used == 4
        assert gw.message_count == 1
        assert gw.defender_views() == ()
        assert gw.defender_activity() == ()
        assert text not in json.dumps([v.model_dump(mode="json") for v in gw.operator_views()])
        validate_journal(gw.events)
        assert any(text.encode() in value for value in gw.iter_payloads())
        assert (tmp_path / "journal/events.jsonl").is_file()
    finally:
        board.close()


@pytest.mark.parametrize("text", ["   \t\n", "a" * 2000, "🔒" * 2000])
def test_frozen_schema_text_is_preserved(swarm: SwarmChatMessageboard, text: str) -> None:
    post = swarm.prepare(author_actor_id="attacker-1", round_index=2, text=text)
    swarm.commit(post)
    page = swarm.read(reader_actor_id="attacker-2", round_index=3, after_post_id=0)
    assert page.posts == (post,)
    logs = list(swarm.directory.glob("chats/*/log/*.jsonl"))
    if not logs:  # upstream segments use numeric names, not an extension contract
        logs = [p for p in swarm.directory.glob("chats/*/log/*") if p.is_file()]
    events = [json.loads(line) for path in logs for line in path.read_text().splitlines()]
    assert any(e.get("text") == text and e.get("episode_round_index") == 2 for e in events)


@pytest.mark.parametrize("text,count", [("short", 25), ("🔒" * 2000, 4)])
def test_count_and_utf8_clipping_match_memory(
    swarm: SwarmChatMessageboard, text: str, count: int
) -> None:
    memory = Messageboard(solo=False)
    for index in range(count):
        post = memory.prepare(author_actor_id="attacker-1", round_index=index, text=text)
        memory.commit(post)
        swarm.commit(swarm.prepare(author_actor_id="attacker-1", round_index=index, text=text))
    for cursor in (0, 2, 20, count + 10):
        query = dict(reader_actor_id="attacker-2", round_index=count + 1, after_post_id=cursor)
        assert swarm.read(**query) == memory.read(**query)
    assert swarm.read(reader_actor_id="attacker-2", round_index=count + 1, after_post_id=0).clipped


def test_viewer_auth_readonly_and_receipts(swarm: SwarmChatMessageboard, tmp_path: Path) -> None:
    gw = gateway(tmp_path, swarm)
    invoke(gw, "attacker-1", 0, "post_to_messageboard", text="first")
    invoke(gw, "attacker-1", 0, "post_to_messageboard", text="second")
    endpoint = swarm.viewer_url.removesuffix("/view")
    token = (swarm.directory / "view.token").read_text().strip()
    headers = {"Authorization": f"Bearer {token}"}
    channel = json.loads((swarm.directory / "integration.json").read_text())["channel_id"]
    with httpx.Client(base_url=endpoint, timeout=3, trust_env=False) as client:
        assert client.get("/view").status_code == 200
        assert client.post("/v1/view_snapshot", json={}).status_code == 401
        response = client.post("/v1/view_snapshot", headers=headers, json={})
        assert response.headers["connection"] == "close"
        snapshot = response.json()
        assert {user["id"] for user in snapshot["users"]} == {
            "attacker-1",
            "attacker-2",
            "attacker-3",
        }
        for method in ("send", "read", "wait", "edit", "delete", "user_add", "send_files"):
            assert client.post(f"/v1/{method}", headers=headers, json={}).status_code == 403
        admin_token = (swarm.directory / "admin.token").read_text().strip()
        user_token = swarm._store.rotate_token("attacker-1")
        for privileged in (admin_token, user_token):
            assert (
                client.post(
                    "/v1/send",
                    headers={"Authorization": f"Bearer {privileged}"},
                    json={"chat": channel, "text": "bypass"},
                ).status_code
                == 403
            )
        view = client.post("/v1/view_messages", headers=headers, json={"chat": channel}).json()
        assert [m["text"] for m in view["messages"] if m["kind"] == "message"] == [
            "first",
            "second",
        ]
        assert swarm._store.position("attacker-2", swarm._chat) == 0
        # Reading only the second post must not claim the skipped first was seen.
        invoke(gw, "attacker-2", 1, "read_messageboard", after_post_id=1)
        assert swarm._store.position("attacker-2", swarm._chat) == 0
        invoke(gw, "attacker-2", 2, "read_messageboard", after_post_id=0)
        assert swarm._store.position("attacker-2", swarm._chat) > 0
    assert swarm.directory.stat().st_mode & 0o777 == 0o700
    assert (swarm.directory / "view.token").stat().st_mode & 0o777 == 0o600
    swarm.close()
    swarm.close()
    assert not (swarm.directory / "address").exists()
    with pytest.raises(httpx.TransportError):
        httpx.get(endpoint + "/v1/health", timeout=1, trust_env=False)


def test_backend_failure_invalidates_instead_of_falling_back(
    swarm: SwarmChatMessageboard, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gw = gateway(tmp_path, swarm)
    invoke(gw, "attacker-1", 0, "post_to_messageboard", text="stored")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("private backend diagnostic must not reach the model")

    monkeypatch.setattr(swarm._store, "message", fail)
    with pytest.raises(GatewayError, match="^messageboard_failed$"):
        invoke(gw, "attacker-2", 1, "read_messageboard", after_post_id=0)
    assert not gw.episode_valid
    assert gw.attempts_used == 2
    assert gw.defender_activity() == ()


def test_post_failure_is_not_delivered_or_retried(
    swarm: SwarmChatMessageboard, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gw = gateway(tmp_path, swarm)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("write failed")

    monkeypatch.setattr(swarm._chat, "append", fail)
    with pytest.raises(GatewayError, match="^messageboard_failed$"):
        invoke(gw, "attacker-1", 0, "post_to_messageboard", text="undelivered")
    assert not gw.episode_valid
    assert gw.message_count == 0
    assert gw.attempts_used == 1


def test_solo_and_episode_isolation(tmp_path: Path) -> None:
    pytest.importorskip("swarmchat")
    first = SwarmChatMessageboard(tmp_path / "one", solo=True, episode_id="ep_first")
    second = SwarmChatMessageboard(tmp_path / "two", solo=True, episode_id="ep_second")
    try:
        post = first.prepare(author_actor_id="attacker-1", round_index=0, text="own note")
        first.commit(post)
        assert first.read(reader_actor_id="attacker-1", round_index=1, after_post_id=0).posts == (
            post,
        )
        assert second.read(reader_actor_id="attacker-1", round_index=1, after_post_id=0).posts == ()
        with pytest.raises(MessageboardError):
            first.read(reader_actor_id="defender", round_index=1, after_post_id=0)
        with pytest.raises(FileExistsError):
            SwarmChatMessageboard(tmp_path / "one", solo=True, episode_id="ep_reuse")
    finally:
        first.close()
        second.close()


def test_journal_failure_does_not_mark_messages_read(
    swarm: SwarmChatMessageboard, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gw = gateway(tmp_path, swarm)
    invoke(gw, "attacker-1", 0, "post_to_messageboard", text="unread")
    original = gw._journal._append_line

    def fail_result(path: Path, data: bytes) -> None:
        if json.loads(data)["kind"] == "tool_completed":
            raise JournalWriteError("injected disk failure")
        original(path, data)

    monkeypatch.setattr(gw._journal, "_append_line", fail_result)
    with pytest.raises(GatewayError, match="journal_write_failed"):
        invoke(gw, "attacker-2", 1, "read_messageboard", after_post_id=0)
    assert swarm._store.position("attacker-2", swarm._chat) == 0
    assert not gw.episode_valid


@pytest.mark.parametrize("operation", ["close", "reset_failure", "setup_failure"])
def test_core_owns_backend_cleanup(
    swarm: SwarmChatMessageboard, tmp_path: Path, operation: str
) -> None:
    # The target lifecycle is mocked, not passed off as a containment check.
    # The SwarmChat server/store being closed are real.
    deployment = Mock(spec=Deployment)
    core = EpisodeCore(tmp_path / "runs", deployment=deployment, messageboard_backend="swarmchat")
    core._messageboard = swarm
    if operation == "close":
        core.close()
    elif operation == "setup_failure":
        core._fail_reset()
    else:
        deployment.create_episode_target.side_effect = DeploymentError("injected reset failure")
        with pytest.raises(RuntimeError, match="reset_failed"):
            core.reset(seed=17)
    assert core._messageboard is None
    assert not (swarm.directory / "address").exists()
    with pytest.raises(httpx.TransportError):
        httpx.get(swarm.viewer_url, timeout=1, trust_env=False)
    core.close()


def test_failed_viewer_start_releases_store_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("swarmchat")
    from swarmchat.store import Store

    def fail(*args: Any) -> None:
        raise OSError("injected bind failure")

    monkeypatch.setattr("adaptivehoneypotenv.integrations.swarmchat._viewer", fail)
    directory = tmp_path / "failed"
    with pytest.raises(MessageboardError, match="setup failed"):
        SwarmChatMessageboard(directory, solo=True, episode_id="ep_failed")
    reopened = Store(str(directory))
    reopened.close()


def test_core_reset_wires_fresh_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("swarmchat")
    deployment = Mock(spec=Deployment)
    targets = []
    for index in range(2):
        episode_id = f"ep_swarmchat0{index}"
        fields = envelope("episode_started", 0)
        fields.update(
            episode_id=episode_id, event_id=compute_event_id(episode_id, 0, "episode_started")
        )
        started = EpisodeStarted(
            kind="episode_started",
            scenario_id="secret_store_ops/v1",
            catalogue_ordering_version="secret_store_ops/v1.ordering.1",
            team="trio",
            **fields,
        )
        targets.append(
            EpisodeTarget(
                episode_id=episode_id,
                profile="malicious",
                bridge_endpoint="http://127.0.0.1:1",
                controller_token="test-controller-token",
                target_container_id="test-target",
                bridge_container_id="test-bridge",
                network_id="test-network",
                started_event=started,
            )
        )
    deployment.create_episode_target.side_effect = targets
    core = EpisodeCore(tmp_path / "runs", deployment=deployment, messageboard_backend="swarmchat")
    # Only target provisioning is replaced. Workspace creation, board, gateway,
    # journal, reset and cleanup run as normal, without claiming a Docker gate.
    monkeypatch.setattr(core, "_provision", lambda bundle: None)
    try:
        core.reset(seed=17)
        gw = core._require_gateway()
        invoke(gw, "attacker-1", 0, "post_to_messageboard", text="first episode")
        old_board = core._messageboard
        old_directory = core.messageboard_directory()
        assert old_directory is not None and old_directory.exists()
        core.reset(seed=17)
        assert core._messageboard is not old_board
        assert core.messageboard_directory() != old_directory
        assert not (old_directory / "address").exists()
        assert (
            invoke(core._require_gateway(), "attacker-2", 1, "read_messageboard", after_post_id=0)[
                "posts"
            ]
            == []
        )
        assert core.observation().activity == ()
    finally:
        core.close()
    assert deployment.destroy.call_count == 2


def test_core_returns_invalid_transition_for_backend_failure(
    swarm: SwarmChatMessageboard, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = Mock(spec=Deployment)
    core = EpisodeCore(tmp_path / "runs", deployment=deployment, messageboard_backend="swarmchat")
    core._messageboard = swarm
    core._gateway = gateway(tmp_path, swarm)
    core._episode_id = "ep_swarmchat01"
    core._log = ControllerLog(core._gateway)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("backend is unavailable")

    def window() -> None:
        invoke(
            core._require_gateway(), "attacker-1", 0, "post_to_messageboard", text="not delivered"
        )

    monkeypatch.setattr(swarm._chat, "append", fail)
    monkeypatch.setattr(core, "_attacker_window", window)
    try:
        result = core.step(None, core.mint_action_id())
        assert not result.info.valid
        assert result.info.invalid_reason == "messageboard_failed"
        assert result.observation.activity == ()
        assert result.reward == 0
    finally:
        core.close()
