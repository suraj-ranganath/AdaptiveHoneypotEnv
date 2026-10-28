"""Approved description catalogue for ``secret_store_ops/v1``.

Phase 0's ``build_catalogue`` crosses every description id with every
compatible template, slot, and context. Texts are therefore not bound to one
template or workflow. This module checks the contract audit plus a stricter
scenario audit, then hands the id list to the frozen builder.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from adaptivehoneypotenv.contracts.actions import (
    PLACEHOLDER_DESCRIPTION_PREFIX,
    validate_description_id,
)
from adaptivehoneypotenv.contracts.actions import (
    audit_description as contract_audit_description,
)
from adaptivehoneypotenv.contracts.catalogue import (
    DiscreteCatalogue,
    build_catalogue,
)
from adaptivehoneypotenv.contracts.limits import MAX_DESCRIPTION_VARIANTS
from adaptivehoneypotenv.contracts.versions import DESCRIPTION_AUDIT_VERSION
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.rng import (
    EMAIL_RE,
    PASSWORD_RE,
    SECRET_RE,
    USERNAME_RE,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    GIVEAWAY_WORDS,
    MAX_DESCRIPTION_CHARS,
    PACKAGE_DIR,
    expect_mapping,
    expect_string_list,
    load_scenario_document,
)

AUDIT_VERSION = DESCRIPTION_AUDIT_VERSION
SCENARIO_AUDIT_VERSION = "secret_store_ops_v1.description-audit.2"
CATALOGUE_PATH = PACKAGE_DIR / "description_catalogue.json"

_GIVEAWAY_RE = re.compile(r"\b(" + "|".join(GIVEAWAY_WORDS) + r")\b", re.IGNORECASE)
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
    text: str


def audit_description(text: str) -> list[str]:
    """Return contract and scenario audit violations.

    An empty list means the text may be embedded. Passing is not a claim of
    semantic inertness.
    """

    violations: list[str] = []
    if not isinstance(text, str) or text == "":
        violations.append("description is empty")
        return violations
    violations.extend(contract_audit_description(text))
    if len(text) > MAX_DESCRIPTION_CHARS:
        violations.append(f"description exceeds {MAX_DESCRIPTION_CHARS} characters")
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
    source = path or CATALOGUE_PATH
    raw: object = json.loads(source.read_text(encoding="utf-8"))
    payload = expect_mapping(raw, "description catalogue")
    if payload.get("audit_version") != AUDIT_VERSION:
        raise ValueError("description catalogue audit_version does not match the contract")
    if payload.get("scenario_audit_version") != SCENARIO_AUDIT_VERSION:
        raise ValueError("description catalogue scenario_audit_version does not match the code")
    rows = payload.get("items")
    if not isinstance(rows, list):
        raise ValueError("description catalogue items must be a list")
    items: list[DescriptionItem] = []
    seen: set[str] = set()
    for row in rows:
        document = expect_mapping(row, "description item")
        description_id = document.get("description_id")
        text = document.get("text")
        if not isinstance(description_id, str) or not isinstance(text, str):
            raise ValueError("description item requires description_id and text")
        validate_description_id(description_id)
        if description_id.startswith(PLACEHOLDER_DESCRIPTION_PREFIX):
            raise ValueError(f"{description_id} is a Phase 0 placeholder, not an approved id")
        if description_id in seen:
            raise ValueError(f"duplicate description_id {description_id}")
        seen.add(description_id)
        violations = audit_description(text)
        if violations:
            raise DescriptionAuditError(
                [f"{description_id}: {violation}" for violation in violations]
            )
        items.append(DescriptionItem(description_id=description_id, text=text))
    if not items:
        raise ValueError("description catalogue is empty")
    if len(items) > MAX_DESCRIPTION_VARIANTS:
        raise ValueError(f"at most {MAX_DESCRIPTION_VARIANTS} description variants")
    if path is None:
        listed = expect_string_list(
            load_scenario_document().get("description_ids"),
            "scenario.yaml description_ids",
        )
        if listed != tuple(item.description_id for item in items):
            raise ValueError("scenario.yaml description_ids must match the catalogue file order")
    return tuple(items)


def catalogue_index(items: tuple[DescriptionItem, ...] | None = None) -> dict[str, DescriptionItem]:
    rows = items if items is not None else load_description_catalogue()
    return {item.description_id: item for item in rows}


def approved_description_ids(
    items: tuple[DescriptionItem, ...] | None = None,
) -> tuple[str, ...]:
    rows = items if items is not None else load_description_catalogue()
    return tuple(item.description_id for item in rows)


def build_scenario_catalogue(
    items: tuple[DescriptionItem, ...] | None = None,
) -> DiscreteCatalogue:
    """Discrete catalogue for the approved ids, in catalogue file order."""

    return build_catalogue(approved_description_ids(items))
