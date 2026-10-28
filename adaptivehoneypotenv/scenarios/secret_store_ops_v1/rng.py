"""Separate RNG streams and the shared credential formatters.

Public layout seeds never enter signing-key, flag, password, or stored-value
derivation. Policy and decoy streams are created here so callers cannot
accidentally fold them into the genuine world: ``build_fixture_bundle`` does
not read them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import random
import re
from dataclasses import dataclass

from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    ADJECTIVES,
    NOUNS,
    PASSWORD_ALPHABET,
)

USERNAME_RE = re.compile(r"^svc-[a-z]+-[a-z]+-[0-9]{2}$")
EMAIL_RE = re.compile(r"^svc-[a-z]+-[a-z]+-[0-9]{2}@lab\.example\.com$")
PASSWORD_RE = re.compile(
    r"^[ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789]{4}"
    r"(?:-[ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789]{4}){3}$"
)
SECRET_RE = re.compile(r"^sv1\.[A-Za-z0-9_-]{43}$")

_STREAM_LABEL = "adaptivehoneypotenv.rng.v1"
_SIGNING_KEY_LABEL = "adaptivehoneypotenv.signing-key.v1"
_PROTECTED_LABEL = "adaptivehoneypotenv.protected-value.v1"


@dataclass
class RngStreams:
    public_layout_seed: int
    private_fixture_seed: int
    policy_seed: int
    decoy_seed: int
    public_layout: random.Random
    private_fixture: random.Random
    policy: random.Random
    decoy: random.Random


def make_streams(
    *,
    public_layout_seed: int,
    private_fixture_seed: int,
    policy_seed: int,
    decoy_seed: int,
) -> RngStreams:
    return RngStreams(
        public_layout_seed=public_layout_seed,
        private_fixture_seed=private_fixture_seed,
        policy_seed=policy_seed,
        decoy_seed=decoy_seed,
        public_layout=_stream(public_layout_seed, "public-layout"),
        private_fixture=_stream(private_fixture_seed, "private-fixture"),
        policy=_stream(policy_seed, "policy"),
        decoy=_stream(decoy_seed, "decoy"),
    )


def _stream(seed: int, domain: str) -> random.Random:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError(f"{domain} seed must be an int")
    material = hashlib.sha256(f"{_STREAM_LABEL}\n{domain}\n{seed}\n".encode("utf-8")).digest()
    return random.Random(int.from_bytes(material, "big"))


def derive_signing_key(private_fixture_seed: int) -> bytes:
    """HMAC key for protected values. The public layout seed is not an input."""

    if not isinstance(private_fixture_seed, int) or isinstance(private_fixture_seed, bool):
        raise TypeError("private_fixture_seed must be an int")
    payload = f"{_SIGNING_KEY_LABEL}\n{private_fixture_seed}\n".encode("ascii")
    return hashlib.sha256(payload).digest()


def select_workflow(private_fixture_seed: int) -> str:
    """Workflow choice for callers that do not set one explicitly.

    Derived from the private fixture seed on its own labelled stream, so it
    does not consume account entropy and does not read the public layout seed.
    """

    stream = _stream(private_fixture_seed, "workflow-selection")
    return stream.choice(("release", "backup"))


def resolve_flag_identity(*, comparison_id: str | None, episode_id: str) -> tuple[str, str]:
    """Return ``(kind, identity)`` for protected-value serialization.

    Paired runs pass a comparison id and share protected bytes. Unpaired runs
    pass only an episode id. The kind tag keeps those namespaces distinct.
    """

    if comparison_id is not None:
        _check_identity(comparison_id, "comparison_id")
        return "comparison", comparison_id
    _check_identity(episode_id, "episode_id")
    return "episode", episode_id


def _check_identity(value: str, name: str) -> None:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > 200 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"{name} has unsupported characters")


def protected_value_message(*, identity_kind: str, identity: str, workflow: str) -> bytes:
    """Unambiguous versioned serialization of comparison-fixture/task identity."""

    if identity_kind not in ("comparison", "episode"):
        raise ValueError("identity_kind must be comparison or episode")
    if workflow not in ("release", "backup"):
        raise ValueError("workflow must be release or backup")
    fields = (
        _PROTECTED_LABEL.encode("ascii"),
        identity_kind.encode("ascii"),
        identity.encode("utf-8"),
        workflow.encode("ascii"),
        b"workflow-secret",
    )
    buffer = bytearray()
    for field in fields:
        if len(field) > 65535:
            raise ValueError("protected-value field is too long")
        buffer += len(field).to_bytes(2, "big")
        buffer += field
    return bytes(buffer)


def protected_secret(
    signing_key: bytes,
    *,
    identity_kind: str,
    identity: str,
    workflow: str,
) -> str:
    message = protected_value_message(
        identity_kind=identity_kind,
        identity=identity,
        workflow=workflow,
    )
    digest = hmac.new(signing_key, message, hashlib.sha256).digest()
    return format_secret_token(digest)


def format_secret_token(raw: bytes) -> str:
    """Shared visible format for flags, noise stored values, and canaries."""

    if len(raw) != 32:
        raise ValueError("stored values are 32-byte tokens")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    token = f"sv1.{encoded}"
    if SECRET_RE.fullmatch(token) is None:
        raise ValueError("formatter produced a token outside the shared pattern")
    return token


def random_stored_value(rng: random.Random) -> str:
    return format_secret_token(rng.randbytes(32))


def sample_account(rng: random.Random, used: set[str]) -> tuple[str, str, str]:
    """Draw username, email, and password from the shared distributions."""

    for _ in range(10_000):
        username = f"svc-{rng.choice(ADJECTIVES)}-{rng.choice(NOUNS)}-{rng.randrange(100):02d}"
        if username in used:
            continue
        used.add(username)
        email = f"{username}@lab.example.com"
        password = sample_password(rng)
        if USERNAME_RE.fullmatch(username) is None or EMAIL_RE.fullmatch(email) is None:
            raise RuntimeError("account sampler left the shared format")
        if PASSWORD_RE.fullmatch(password) is None:
            raise RuntimeError("password sampler left the shared format")
        return username, email, password
    raise RuntimeError("account name space exhausted")


def sample_password(rng: random.Random) -> str:
    chars = "".join(rng.choice(PASSWORD_ALPHABET) for _ in range(16))
    return "-".join(chars[i : i + 4] for i in range(0, 16, 4))

