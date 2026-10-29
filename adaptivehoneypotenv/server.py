"""Loopback operator API and SSE.

The stream emits ``project_operator`` views only. Payload bytes, the workflow
goal, canaries, and the decoy registry are not fields of that view and are
not added here. Rendering stays on the client; a slow reader cannot advance
the episode.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from adaptivehoneypotenv.contracts.events import Event, OperatorEventView, project_operator
from adaptivehoneypotenv.env import EpisodeCore

_OPERATOR_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "episode_id",
        "sequence",
        "round_index",
        "attempt_index",
        "world_version",
        "actor_id",
        "actor_role",
        "status",
        "monotonic_duration_ns",
        "wall_time_unix_ns",
        "request_id",
        "payload_refs",
        "tool_name",
        "post_id",
        "char_count",
        "after_post_id",
        "returned_count",
        "clipped",
        "reward_components",
        "source_sequences",
        "deterministic_id",
    }
)
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class OperatorServer:
    """Serves one core. Bind address is loopback."""

    def __init__(self, core: EpisodeCore, host: str = "127.0.0.1", port: int = 8787) -> None:
        if host not in _LOOPBACK:
            raise ValueError("operator API binds to loopback")
        self._core = core
        handler = _handler_factory(core)
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        bound = self._httpd.server_address[1]
        if not isinstance(bound, int):
            raise RuntimeError("operator port is unavailable")
        return bound

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="ahe-operator",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def close(self) -> None:
        self._httpd.server_close()


def _handler_factory(core: EpisodeCore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(204, b"", "text/plain")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/events":
                self._events()
                return
            if path == "/diagnostics":
                body = json.dumps(
                    {"ok": True, "stream": "live", "development_data": False}
                ).encode()
                self._send(200, body, "application/json")
                return
            self._send(404, b'{"ok":false,"message":"not found"}', "application/json")

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            parts = [part for part in path.split("/") if part]
            if len(parts) == 3 and parts[0] == "episodes" and parts[2] in {"kill", "reset"}:
                if parts[1] != core.episode_id:
                    self._send(404, b'{"ok":false,"message":"unknown episode"}', "application/json")
                    return
                if parts[2] == "kill":
                    core.kill()
                    self._send(200, b'{"ok":true,"message":"kill"}', "application/json")
                    return
                if core.episode_id == "":
                    self._send(409, b'{"ok":false,"message":"busy"}', "application/json")
                    return
                try:
                    core.reset(core.seed)
                except RuntimeError:
                    self._send(409, b'{"ok":false,"message":"busy"}', "application/json")
                    return
                self._send(200, b'{"ok":true,"message":"reset"}', "application/json")
                return
            self._send(404, b'{"ok":false,"message":"not found"}', "application/json")

        def _events(self) -> None:
            updates: queue.Queue[Event | None] = queue.Queue()

            def listener(event: Event) -> None:
                updates.put(event)

            snapshot = core.subscribe_operator(listener)
            try:
                last = _resume_after(self.headers.get("Last-Event-ID"), core.episode_id)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self._cors()
                self.end_headers()
                sent: set[int] = set()
                for event in snapshot:
                    if event.episode_id != core.episode_id or event.sequence <= last:
                        continue
                    self._write_event(event)
                    sent.add(event.sequence)
                while True:
                    try:
                        incoming = updates.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    if incoming is None or incoming.sequence in sent:
                        continue
                    if incoming.episode_id != core.episode_id:
                        continue
                    self._write_event(incoming)
                    sent.add(incoming.sequence)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                return
            finally:
                core.unsubscribe_operator(listener)

        def _write_event(self, event: Event) -> None:
            view = project_operator(event)
            payload = _operator_payload(view)
            frame = (
                f"id: {view.episode_id}:{view.sequence}\n"
                f"event: {view.kind}\n"
                f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
            )
            self.wfile.write(frame.encode("utf-8"))
            self.wfile.flush()

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _cors(self) -> None:
            origin = _loopback_origin(self.headers.get("Origin"))
            if origin is None:
                return
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type, Last-Event-ID")
            self.send_header("Vary", "Origin")

    return Handler


def _operator_payload(view: OperatorEventView) -> dict[str, Any]:
    payload = view.model_dump(mode="json")
    extra = set(payload) - _OPERATOR_KEYS
    if extra:
        raise RuntimeError("operator projection gained a field")
    return payload


def _resume_after(header: str | None, episode_id: str) -> int:
    if not header or ":" not in header:
        return -1
    identity, _, raw = header.rpartition(":")
    if identity != episode_id:
        return -1
    try:
        return int(raw)
    except ValueError:
        return -1


def _loopback_origin(origin: str | None) -> str | None:
    if origin is None:
        return None
    prefixes = ("http://127.0.0.1", "http://localhost", "http://[::1]")
    if origin.startswith(prefixes) or origin in {"http://127.0.0.1", "http://localhost"}:
        return origin
    return None
