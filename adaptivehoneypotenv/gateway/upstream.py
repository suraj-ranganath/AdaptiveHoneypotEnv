"""Fixed-upstream HTTP client.

The gateway dials one loopback bridge and never follows redirects. Model
headers cannot supply the controller token or replace the bound actor id.
This module imports the stdlib HTTP client and sends the request target
unchanged. It does not add a query string. The trusted launcher opens its
own loopback relay; every other package module may not import this client.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import client as http_client
from typing import Protocol

_MAX_RAW_BYTES = 1_048_576
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


@dataclass(frozen=True)
class UpstreamResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    body_truncated: bool


class UpstreamExchangeError(Exception):
    """Transport failure. ``uncertain`` is true when a POST may have landed."""

    def __init__(self, reason: str, *, uncertain: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.uncertain = uncertain


class FixedUpstream(Protocol):
    """Bridge port. Implementations must not follow redirects or choose a URL."""

    def exchange(
        self,
        *,
        method: str,
        path: str,
        headers: tuple[tuple[str, str], ...],
        body: bytes,
        actor_id: str,
        controller_token: str,
    ) -> UpstreamResponse:
        """Forward one already-approved request to the fixed upstream."""


class LoopbackFixedUpstream:
    """Stdlib HTTP connection. Redirects are never followed."""

    def __init__(self, host: str, port: int, *, timeout_seconds: float = 10.0) -> None:
        if host not in _LOOPBACK_HOSTS:
            raise ValueError("fixed upstream host must be loopback")
        if port < 1 or port > 65535:
            raise ValueError("fixed upstream port is invalid")
        if timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        self._host = host
        self._port = port
        self._timeout = timeout_seconds

    def exchange(
        self,
        *,
        method: str,
        path: str,
        headers: tuple[tuple[str, str], ...],
        body: bytes,
        actor_id: str,
        controller_token: str,
    ) -> UpstreamResponse:
        if method not in {"GET", "POST"}:
            raise UpstreamExchangeError("invalid_method", uncertain=False)
        if "://" in path or path.startswith("//") or not path.startswith("/") or "#" in path:
            raise UpstreamExchangeError("invalid_path", uncertain=False)
        outbound = _bound_headers(
            headers,
            actor_id=actor_id,
            controller_token=controller_token,
        )
        connection = http_client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            try:
                connection.request(method, path, body=body, headers=outbound)
            except ConnectionRefusedError as exc:
                raise UpstreamExchangeError("transport_error", uncertain=False) from exc
            except (OSError, http_client.HTTPException) as exc:
                raise UpstreamExchangeError("transport_error", uncertain=method == "POST") from exc
            try:
                response = connection.getresponse()
                raw = response.read(_MAX_RAW_BYTES + 1)
                status = response.status
                response_headers = tuple((key, value) for key, value in response.getheaders())
            except (OSError, http_client.HTTPException) as exc:
                raise UpstreamExchangeError("transport_error", uncertain=method == "POST") from exc
        finally:
            connection.close()
        truncated = len(raw) > _MAX_RAW_BYTES
        return UpstreamResponse(
            status_code=status,
            headers=response_headers,
            body=raw[:_MAX_RAW_BYTES],
            body_truncated=truncated,
        )


def _bound_headers(
    headers: tuple[tuple[str, str], ...],
    *,
    actor_id: str,
    controller_token: str,
) -> dict[str, str]:
    """Controller identity wins. Caller tokens and role headers are dropped."""

    blocked = {
        "x-controller-token",
        "x-actor-id",
        "agentenv-role",
        "host",
        "proxy-authorization",
        "proxy-connection",
        "forwarded",
    }
    outbound: dict[str, str] = {}
    for name, value in headers:
        if name.lower() in blocked or name.lower().startswith("x-forwarded-"):
            continue
        outbound[name] = value
    outbound["X-Controller-Token"] = controller_token
    outbound["X-Actor-Id"] = actor_id
    return outbound
