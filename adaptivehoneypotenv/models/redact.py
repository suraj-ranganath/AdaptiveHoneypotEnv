"""Redact provider credentials before they reach logs, errors, or ledgers.

The env var name is not a secret. The value is. Exact values registered for
the current call are removed, then common key shapes are removed so a leaked
Authorization header cannot survive an httpx log line.
"""

from __future__ import annotations

import contextvars
import logging
import re

_SK_OR_RE = re.compile(r"sk-or-[A-Za-z0-9_\-]{6,}", re.IGNORECASE)
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_secrets: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "adaptivehoneypotenv_provider_secrets",
    default=(),
)


def push_secret(secret: str) -> contextvars.Token[tuple[str, ...]]:
    current = _secrets.get()
    if secret and secret not in current:
        return _secrets.set(current + (secret,))
    return _secrets.set(current)


def reset_secret(token: contextvars.Token[tuple[str, ...]]) -> None:
    _secrets.reset(token)


def redact_provider_key(text: str, secrets: tuple[str, ...] | list[str] = ()) -> str:
    """Remove the provider key without stripping lab JWTs from model output.

    Exact secret values are removed first. ``sk-or-`` shapes are removed
    second. Bearer tokens are left intact so an attacker tool call can still
    present a credential it discovered in the lab.
    """

    cleaned = text
    seen: list[str] = []
    for secret in tuple(secrets) + _secrets.get():
        if secret and secret not in seen:
            seen.append(secret)
    for secret in sorted(seen, key=len, reverse=True):
        cleaned = cleaned.replace(secret, "[REDACTED]")
    return _SK_OR_RE.sub("[REDACTED]", cleaned)


def redact_text(text: str, secrets: tuple[str, ...] | list[str] = ()) -> str:
    """Redact provider keys and Authorization headers in logs and errors."""

    return _BEARER_RE.sub("Bearer [REDACTED]", redact_provider_key(text, secrets))


class RedactingFilter(logging.Filter):
    """Apply :func:`redact_text` to a log record before handlers see it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = ()
        return True


def install_redacting_filters() -> None:
    filt = RedactingFilter()
    for name in ("httpx", "httpcore", "adaptivehoneypotenv.models"):
        logger = logging.getLogger(name)
        if not any(isinstance(existing, RedactingFilter) for existing in logger.filters):
            logger.addFilter(filt)
