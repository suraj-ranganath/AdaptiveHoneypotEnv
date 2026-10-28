"""Fixed-upstream bridge for one SecretStorage episode.

The process dials only the upstream address supplied in its environment.
Callers cannot select a destination, change the profile, or invoke
maintenance. Redirects are discarded. Role headers are not credentials.
"""

from __future__ import annotations

import hmac
import http.client
import ipaddress
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, quote, urlsplit

BODY_LIMIT = 16384
LISTEN_PORT = 8080
TOKEN_HEADER = "X-Controller-Token"

MALICIOUS = frozenset({("POST", "/login"), ("GET", "/get_secret")})
BENIGN = frozenset(MALICIOUS | {("POST", "/register"), ("POST", "/set_secret")})
SETUP = BENIGN

ROLE_HEADERS = frozenset(
    {
        "agentenv-role",
        "x-role",
        "x-actor-role",
        "x-user-role",
        "x-controller-role",
    }
)
PROXY_HEADERS = frozenset(
    {
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-prefix",
        "x-forwarded-port",
        "forwarded",
        "via",
        "proxy-authorization",
        "proxy-connection",
        "x-real-ip",
        "x-original-url",
        "x-rewrite-url",
    }
)
DESTINATION_HEADERS = frozenset({"destination", "x-upstream", "x-target-url", "x-forwarded-uri"})
CONTROL_PREFIXES = (
    "/admin",
    "/maintenance",
    "/controller",
    "/internal",
    "/backup",
    "/restore",
    "/debug",
    "/metrics",
    "/docker",
    "/v1.",
    "/openapi.json",
    "/docs",
    "/redoc",
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _load_config() -> tuple[str, int, str, frozenset[tuple[str, str]]]:
    raw_host = os.environ.get("UPSTREAM_HOST", "")
    try:
        upstream_host = str(ipaddress.IPv4Address(raw_host))
    except ipaddress.AddressValueError:
        print("UPSTREAM_HOST must be an IPv4 address", file=sys.stderr)
        raise SystemExit(1) from None
    try:
        upstream_port = int(os.environ["UPSTREAM_PORT"])
    except (KeyError, ValueError):
        print("UPSTREAM_PORT must be an integer", file=sys.stderr)
        raise SystemExit(1) from None
    if not 1 <= upstream_port <= 65535:
        print("UPSTREAM_PORT is out of range", file=sys.stderr)
        raise SystemExit(1)
    token = os.environ.get("CONTROLLER_TOKEN", "")
    if len(token) < 32:
        print("CONTROLLER_TOKEN is missing or short", file=sys.stderr)
        raise SystemExit(1)
    profile_name = os.environ.get("PROFILE", "")
    if profile_name == "malicious":
        profile = MALICIOUS
    elif profile_name == "benign":
        profile = BENIGN
    else:
        print("PROFILE must be malicious or benign", file=sys.stderr)
        raise SystemExit(1)
    return upstream_host, upstream_port, token, profile


UPSTREAM_HOST, UPSTREAM_PORT, CONTROLLER_TOKEN, ACTOR_ALLOW = _load_config()


def _token_matches(presented: str) -> bool:
    presented_bytes = presented.encode("utf-8")
    expected = CONTROLLER_TOKEN.encode("utf-8")
    if len(presented_bytes) != len(expected):
        return False
    return hmac.compare_digest(presented_bytes, expected)


def _host_is_loopback(value: str) -> bool:
    host = value.strip().lower()
    if "://" in host or host.startswith("//") or "@" in host or "\\" in host:
        return False
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    elif host.count(":") > 1:
        return False
    return host in LOOPBACK_HOSTS


def _is_control_plane(path: str) -> bool:
    lowered = path.lower()
    return any(lowered == prefix or lowered.startswith(prefix + "/") for prefix in CONTROL_PREFIXES)


class BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._reject(405, "method_rejected")

    def do_DELETE(self) -> None:  # noqa: N802
        self._reject(405, "method_rejected")

    def do_PATCH(self) -> None:  # noqa: N802
        self._reject(405, "method_rejected")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._reject(405, "method_rejected")

    def do_HEAD(self) -> None:  # noqa: N802
        self._reject(405, "method_rejected")

    def do_CONNECT(self) -> None:  # noqa: N802
        self._reject(400, "unknown_destination")

    def _handle(self, method: str) -> None:
        target = self._request_target()
        if not target or len(target) > 512 or "\r" in target or "\n" in target or "\\" in target:
            self._reject(400, "unknown_destination")
            return
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith("//"):
            self._reject(400, "unknown_destination")
            return
        path = parsed.path
        if path != path.strip() or ".." in path.split("/") or "%" in path:
            self._reject(400, "unknown_destination")
            return

        header_error = self._header_error()
        if header_error is not None:
            self._reject(400, header_error)
            return

        body = self._read_body()
        if body is None:
            return

        route, upstream_path = self._split_route(path)
        if route is None or upstream_path is None:
            if _is_control_plane(path):
                self._reject(404, "control_plane_rejected")
            else:
                self._reject(404, "not_found")
            return
        if _is_control_plane(upstream_path):
            self._reject(404, "control_plane_rejected")
            return

        query_error, query = self._query(upstream_path, parsed.query)
        if query_error is not None:
            self._reject(400, query_error)
            return

        presented = self.headers.get(TOKEN_HEADER, "")
        if not _token_matches(presented):
            self._reject(401, "controller_token_required")
            return

        operation = (method, upstream_path)
        allowed = SETUP if route == "setup" else ACTOR_ALLOW
        if operation not in allowed:
            self._reject(403, "profile_rejected")
            return

        self._forward(method, upstream_path, query, body)

    def _request_target(self) -> str:
        """Use the request line. BaseHTTP collapses '//' before do_GET."""
        words = (self.requestline or "").split()
        if len(words) >= 2:
            return words[1]
        return self.path

    def _split_route(self, path: str) -> tuple[str | None, str | None]:
        for prefix in ("/actor", "/setup"):
            marker = prefix + "/"
            if path.startswith(marker):
                return prefix[1:], path[len(prefix) :]
        return None, None

    def _header_error(self) -> str | None:
        names = [name.lower() for name in self.headers.keys()]
        if names.count(TOKEN_HEADER.lower()) > 1:
            return "malformed_headers"
        for name in names:
            if name in PROXY_HEADERS:
                return "proxy_header_rejected"
            if name in DESTINATION_HEADERS:
                return "unknown_destination"
        host = self.headers.get("Host")
        if host is None or not _host_is_loopback(host):
            return "host_header_rejected"
        if self.headers.get("Transfer-Encoding") is not None:
            return "malformed_headers"
        return None

    def _query(self, upstream_path: str, raw_query: str) -> tuple[str | None, str]:
        if "\r" in raw_query or "\n" in raw_query or "\\" in raw_query:
            return "unknown_destination", ""
        if not raw_query:
            return None, ""
        try:
            pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return "malformed_headers", ""
        if upstream_path != "/get_secret":
            return "unknown_destination", ""
        if len(pairs) != 1 or pairs[0][0] != "username":
            return "unknown_destination", ""
        username = pairs[0][1]
        if (
            "://" in username
            or username.startswith("//")
            or any(ord(char) < 32 for char in username)
        ):
            return "unknown_destination", ""
        return None, "username=" + quote(username, safe="")

    def _read_body(self) -> bytes | None:
        if self.command == "GET":
            if self.headers.get("Content-Length") not in (None, "0"):
                self._reject(400, "malformed_headers")
                return None
            return b""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._reject(400, "malformed_headers")
            return None
        try:
            length = int(raw_length)
        except ValueError:
            self._reject(400, "malformed_headers")
            return None
        if length < 0 or length > BODY_LIMIT:
            self._reject(413, "body_limit_exceeded")
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._reject(400, "malformed_headers")
            return None
        return body

    def _forward(self, method: str, upstream_path: str, query: str, body: bytes) -> None:
        request_target = upstream_path if not query else f"{upstream_path}?{query}"
        headers = {
            "Host": f"{UPSTREAM_HOST}:{UPSTREAM_PORT}",
            "Connection": "close",
            "Content-Length": str(len(body)),
        }
        authorization = self.headers.get("Authorization")
        if authorization:
            if "\r" in authorization or "\n" in authorization:
                self._reject(400, "malformed_headers")
                return
            headers["Authorization"] = authorization
        content_type = self.headers.get("Content-Type")
        if content_type and body:
            headers["Content-Type"] = content_type
        connection = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=5)
        try:
            connection.request(method, request_target, body=body, headers=headers)
            upstream = connection.getresponse()
            status = upstream.status
            if status in REDIRECT_STATUSES:
                upstream.read(BODY_LIMIT + 1)
                self._reject(502, "redirect_rejected")
                return
            payload = upstream.read(BODY_LIMIT + 1)
            if len(payload) > BODY_LIMIT:
                self._reject(502, "response_limit_exceeded")
                return
            media = upstream.headers.get("Content-Type", "application/json")
            media = media.split(";", 1)[0].strip() or "application/octet-stream"
            if any(char in media for char in "\r\n "):
                media = "application/octet-stream"
        except OSError:
            self._reject(502, "upstream_unreachable")
            return
        finally:
            connection.close()
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self._note(status, upstream_path)

    def _reject(self, status: int, code: str) -> None:
        self._note(status, code)
        payload = json.dumps({"error": code}).encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def _note(self, status: int, label: str) -> None:
        print(f"bridge status={status} label={label}", file=sys.stderr, flush=True)


class BridgeServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    server = BridgeServer(("0.0.0.0", LISTEN_PORT), BridgeHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
