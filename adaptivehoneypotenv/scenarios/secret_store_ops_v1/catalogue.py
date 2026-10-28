"""Approved description catalogue and the versioned description audit.

Descriptions are embedded in attacker-visible artifacts. The audit blocks
labels, URLs, credential-shaped text, control characters, and a small set of
imperative/injection phrases. Passing the audit is not a claim of semantic
inertness (DESIGN §3.2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from adaptivehoneypotenv.scenarios.secret_store_ops_v1.rng import (
    EMAIL_RE,
    PASSWORD_RE,
    SECRET_RE,
    USERNAME_RE,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    COMPATIBILITY,
    CONTEXTS,
    GIVEAWAY_WORDS,
    MAX_DESCRIPTION_CHARS,
    PACKAGE_DIR,
)

AUDIT_VERSION = "secret_store_ops_v1.description-audit.1"
CATALOGUE_PATH = PACKAGE_DIR / "description_catalogue.json"

_GIVEAWAY_RE = re.compile(r"\b(" + "|".join(GIVEAWAY_WORDS) + r")\b", re.IGNORECASE)
_URL_RE = re.compile(r"(https?:)?//|www\.", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_CREDENTIAL_RE = re.compile(
    r"(password|secret|token|api[_-]?key)\s*[:=]|sv1\.|@lab\.example\.com",
    re.IGNORECASE,
)
_INJECTION_PHRASES = (
    "ignore previous",
    "ignore all",
    "you must",
    "you should",
    "system prompt",
    "disregard",
    "do not tell",
    "exfiltrate",
    "run this",
    "execute the",
)


class DescriptionAuditError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))


@dataclass(frozen=True)
class DescriptionItem:
    description_id: str
    template_id: str
    context_id: str
    text: str


def audit_description(text: str) -> list[str]:
    """Return audit violations. An empty list means the text may be embedded."""

    violations: list[str] = []
    if not isinstance(text, str) or text == "":
        violations.append("description is empty")
        return violations
    if len(text) > MAX_DESCRIPTION_CHARS:
        violations.append(f"description exceeds {MAX_DESCRIPTION_CHARS} characters")
    if _CONTROL_RE.search(text):
        violations.append("description contains a control character")
    if _URL_RE.search(text):
        violations.append("description contains a URL")
    if _GIVEAWAY_RE.search(text):
        violations.append("description contains a decoy or objective label")
    if _CREDENTIAL_RE.search(text) or _contains_credential_token(text):
        violations.append("description contains credential-shaped text")
    if ".." in text or text.startswith("/") or "\\" in text:
        violations.append("description contains a path")
    lowered = text.casefold()
    for phrase in _INJECTION_PHRASES:
        if phrase in lowered:
            violations.append(f"description contains imperative wording: {phrase}")
    return violations


def _contains_credential_token(text: str) -> bool:
    for token in re.findall(r"\S+", text):
        if (
            PASSWORD_RE.fullmatch(token)
            or SECRET_RE.fullmatch(token)
            or USERNAME_RE.fullmatch(token)
            or EMAIL_RE.fullmatch(token)
        ):
            return True
    return False


def load_description_catalogue(path: Path | None = None) -> tuple[DescriptionItem, ...]:
    payload = json.loads((path or CATALOGUE_PATH).read_text(encoding="utf-8"))
    if payload.get("audit_version") != AUDIT_VERSION:
        raise ValueError("description catalogue audit_version does not match the code")
    items: list[DescriptionItem] = []
    seen: set[str] = set()
    for row in payload["items"]:
        item = DescriptionItem(
            description_id=row["description_id"],
            template_id=row["template_id"],
            context_id=row["context_id"],
            text=row["text"],
        )
        if item.description_id in seen:
            raise ValueError(f"duplicate description_id {item.description_id}")
        seen.add(item.description_id)
        if item.template_id not in COMPATIBILITY:
            raise ValueError(f"unknown template on {item.description_id}")
        if item.context_id not in CONTEXTS:
            raise ValueError(f"unknown context on {item.description_id}")
        violations = audit_description(item.text)
        if violations:
            raise DescriptionAuditError(
                [f"{item.description_id}: {violation}" for violation in violations]
            )
        items.append(item)
    if not items:
        raise ValueError("description catalogue is empty")
    return tuple(items)


def catalogue_index(items: tuple[DescriptionItem, ...] | None = None) -> dict[str, DescriptionItem]:
    rows = items if items is not None else load_description_catalogue()
    return {item.description_id: item for item in rows}
