"""SwarmChat storage and a read-only native viewer for an episode's board.

Only the trusted gateway calls this adapter. Model tools, visibility, budgets,
and scoring stay in AdaptiveHoneypotEnv. No SwarmChat user tokens reach actors.
The upstream store is embedded so HTTP exposes only its observer operations.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from adaptivehoneypotenv.contracts.limits import MESSAGEBOARD_POST_MAX_CHARS
from adaptivehoneypotenv.gateway.messageboard import (
    BoardPage,
    Messageboard,
    MessageboardError,
    PostedMessage,
)

SWARMCHAT_REVISION = "fb5aa6a05b40fba70f749cd3017aeb3219ab6ac1"
SWARMCHAT_VERSION = "0.1.0"


def require_swarmchat() -> None:
    """Fail before creating a target or spending money if the extra is absent."""
    try:
        from swarmchat import __version__
    except ImportError:
        raise MessageboardError("Install SwarmChat with: uv sync --extra swarmchat") from None
    if __version__ != SWARMCHAT_VERSION:
        raise MessageboardError(
            "SwarmChat version mismatch; run uv sync --frozen --extra swarmchat"
        )


def _private_json(path: Path, value: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")


def _viewer(store: Any) -> ThreadingHTTPServer:
    from swarmchat.server import VIEW, Handler, Server
    from swarmchat.store import Error

    def caller(handler: Any, name: str, token: str) -> None:
        # Even a valid user/admin token cannot mutate or read the agent API
        # through this listener. Native viewer requests still authenticate.
        if name not in VIEW:
            raise Error(403, "Episode viewer is read-only; use the controller's board tools.")
        Handler.caller(handler, name, token)

    def parse_request(handler: Any) -> bool:
        parsed: bool = Handler.parse_request(handler)
        # A persistent browser connection must not keep serving an old episode
        # after reset closes the listening socket. Each request ends its socket.
        handler.close_connection = True
        return parsed

    handler = type(
        "EpisodeViewerHandler",
        (Handler,),
        {
            "store": store,
            "caller": caller,
            "parse_request": parse_request,
            "verbose": False,
            "timeout": 2.0,
        },
    )
    server: ThreadingHTTPServer = Server(("127.0.0.1", 0), handler, max_connections=32)
    # Drain bounded viewer requests before closing the store they may be reading.
    server.daemon_threads = False
    return server


class SwarmChatMessageboard(Messageboard):
    """One private SwarmChat store/channel per episode, never a shared global board.

    The in-memory post catalogue selects round-visible IDs and clips the page;
    text is fetched from SwarmChat's real log on every read. That log is not a
    substitute for the authoritative episode journal or evidence of delivery.
    """

    def __init__(self, directory: Path, *, solo: bool, episode_id: str) -> None:
        require_swarmchat()
        from swarmchat.store import Store

        super().__init__(solo=solo)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(self.directory, 0o700)
        self._actors = ("attacker-1",) if solo else ("attacker-1", "attacker-2", "attacker-3")
        self._ids: dict[int, str] = {}
        self._closed = False
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._store: Any = Store(
            str(self.directory),
            {
                "fsync": True,
                "default_notify": "none",
                "max_text": MESSAGEBOARD_POST_MAX_CHARS,
                "max_wait": 1.0,
                "max_body": 16 * 1024,
            },
        )
        try:
            for actor in self._actors:
                self._store.add_user(actor, actor.replace("-", " ").title())
            self._chat = self._store.create_channel(
                self._actors[0],
                "attackers",
                others=self._actors[1:],
                description="Episode attacker board. Hidden from the defender. Reads are explicit.",
            )
            _private_json(
                self.directory / "integration.json",
                {
                    "backend": "swarmchat",
                    "upstream_revision": SWARMCHAT_REVISION,
                    "upstream_version": SWARMCHAT_VERSION,
                    "episode_id": episode_id,
                    "channel_id": self._chat.id,
                    "visibility": "earlier_rounds_only",
                    "live_resume_supported": False,
                },
            )
            self._server = _viewer(self._store)
            port = self._server.server_address[1]
            self.viewer_url = f"http://127.0.0.1:{port}/view"
            # The upstream `swarmchat view --data DIR` uses these to open the
            # authenticated native viewer without printing credentials here.
            address = self.directory / "address"
            address.write_text(f"http://127.0.0.1:{port}\n", encoding="utf-8")
            os.chmod(address, 0o600)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name=f"swarmchat-{episode_id}",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            self.close()
            raise MessageboardError("SwarmChat setup failed") from None

    def _require_actor(self, actor_id: str) -> None:
        if self._closed or actor_id not in self._actors:
            raise MessageboardError("SwarmChat board unavailable for this actor")

    def commit(self, post: PostedMessage) -> None:
        self._require_actor(post.author_actor_id)
        if post.post_id in self._ids:
            raise MessageboardError("Duplicate SwarmChat post")
        try:
            from swarmchat.store import now

            # Use the pinned store's append primitive. Its public send API
            # rejects whitespace-only text that our frozen tool schema accepts.
            # Gateway validation supplies identity and the exact bounded text;
            # the extra fields persist our round/ID mapping without changing it.
            with self._chat.lock:
                event = self._chat.append(
                    {
                        "kind": "message",
                        "from": post.author_actor_id,
                        "text": post.text,
                        "at": max(now(), self._chat.last["at"] if self._chat.last else ""),
                        "episode_post_id": post.post_id,
                        "episode_round_index": post.round_index,
                    },
                    fsync=True,
                )
            self._ids[post.post_id] = f"{self._chat.id}:{event['seq']}"
            super().commit(post)
        except Exception:
            raise MessageboardError("SwarmChat post failed") from None

    def read(self, *, reader_actor_id: str, round_index: int, after_post_id: int) -> BoardPage:
        self._require_actor(reader_actor_id)
        page = super().read(
            reader_actor_id=reader_actor_id,
            round_index=round_index,
            after_post_id=after_post_id,
        )
        posts: list[PostedMessage] = []
        try:
            for expected in page.posts:
                _, event = self._store.message(reader_actor_id, self._ids[expected.post_id])
                actual = PostedMessage(
                    post_id=event["episode_post_id"],
                    author_actor_id=event["from"],
                    round_index=event["episode_round_index"],
                    text=event["text"],
                )
                if actual != expected:
                    raise MessageboardError("SwarmChat message differs from the committed post")
                posts.append(actual)
        except Exception:
            raise MessageboardError("SwarmChat read failed") from None
        return BoardPage(posts=tuple(posts), clipped=page.clipped)

    def acknowledge_read(self, *, reader_actor_id: str, page: BoardPage) -> None:
        self._require_actor(reader_actor_id)
        try:
            shown = {int(self._ids[post.post_id].rsplit(":", 1)[1]) for post in page.posts}
            # A read with a cursor may skip older posts. Do not falsely mark
            # skipped messages as read in SwarmChat's cumulative receipts.
            with self._store.lock:
                upto = self._store.shown_upto(reader_actor_id, self._chat, shown)
                if upto:
                    self._store.mark_read(reader_actor_id, self._chat, upto)
        except Exception:
            raise MessageboardError("SwarmChat read receipt failed") from None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._server is not None:
                if self._thread is not None and self._thread.is_alive():
                    self._server.shutdown()
                    self._thread.join(timeout=3)
                self._server.server_close()
        finally:
            try:
                self._store.close()
            finally:
                (self.directory / "address").unlink(missing_ok=True)
