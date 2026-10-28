"""Loopback-safe client for the pinned SecretStorage API.

This stays outside ``adaptivehoneypotenv`` because Phase 0 rejects network
client imports anywhere in that package. ``solve_reference_route`` depends
only on the ``SecretStorageClient`` protocol.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from typing import IO

from adaptivehoneypotenv.scenarios.secret_store_ops_v1.solver import SecretStorageClientError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise SecretStorageClientError(f"redirect rejected ({code})")


class UrllibSecretStorageClient:
    """Minimal HTTP client for the pinned SecretStorage process.

    ``base_url`` is the WS1 fixed-upstream origin. Redirects are rejected.
    Responses are capped at 16 KiB, matching the actor tool bound.
    """

    def __init__(self, base_url: str, *, timeout: float = 10.0):
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            raise ValueError("base_url must be an absolute http(s) origin")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def login(self, email: str, password: str) -> str:
        payload = json.dumps({"email": email, "password": password}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/login",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        token = _json_object(self._read(request)).get("token")
        if not isinstance(token, str) or token == "":
            raise SecretStorageClientError("login response did not include a token")
        return token

    def get_secret(self, token: str, username: str) -> str:
        query = urllib.parse.urlencode({"username": username})
        request = urllib.request.Request(
            f"{self.base_url}/get_secret?{query}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            method="GET",
        )
        secret = _json_object(self._read(request)).get("secret")
        if not isinstance(secret, str):
            raise SecretStorageClientError("get_secret response did not include a secret")
        return secret

    def _read(self, request: urllib.request.Request) -> str:
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=self.timeout) as response:
                body = response.read(16 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            raise SecretStorageClientError(f"HTTP {exc.code}") from exc
        if not isinstance(body, (bytes, bytearray)):
            raise SecretStorageClientError("response body was not bytes")
        raw = bytes(body)
        if len(raw) > 16 * 1024:
            raise SecretStorageClientError("response exceeded 16 KiB")
        return raw.decode("utf-8")


def _json_object(text: str) -> dict[str, object]:
    raw: object = json.loads(text)
    if not isinstance(raw, dict):
        raise SecretStorageClientError("response was not a JSON object")
    parsed: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise SecretStorageClientError("response keys were not strings")
        parsed[key] = value
    return parsed
