"""Persistent per-run spend ledger.

Reservations are written before the HTTP call and replaced by the billed
amount afterward. A crash during the call leaves the reservation in place,
so a restart cannot forget an in-flight worst case. Defender token totals
are stored and are not added to the attacker team budget.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, TypeVar

from adaptivehoneypotenv.model_api import TokenUsage
from adaptivehoneypotenv.models.errors import CostCapExceeded, LedgerError
from adaptivehoneypotenv.models.pricing import ceil_money
from adaptivehoneypotenv.models.redact import redact_text

T = TypeVar("T")

LEDGER_SCHEMA_VERSION = "1.0.0"
RoleName = Literal["attacker", "defender", "unscoped"]
CostSourceName = Literal["provider", "price_table", "none"]


@dataclass(frozen=True)
class LedgerSummary:
    spent_usd: Decimal
    attacker_generated_tokens: int
    defender_generated_tokens: int
    token_accounting_available: bool


class SpendLedger:
    """File-backed ledger. Concurrent reserves cannot oversubscribe the cap."""

    def __init__(self, path: Path, *, cap_usd: Decimal, team_token_budget: int) -> None:
        if not isinstance(cap_usd, Decimal):
            raise TypeError("cap_usd must be Decimal")
        self._path = path
        self._lock_path = path.with_suffix(path.suffix + ".lock")
        self._cap = ceil_money(cap_usd)
        self._team_budget = team_token_budget
        self._thread = threading.Lock()
        if not path.parent.is_dir():
            raise LedgerError("ledger directory does not exist")
        self._update(lambda document: document)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def cap_usd(self) -> Decimal:
        return self._cap

    def summary(self) -> LedgerSummary:
        return self._update(lambda document: _summarize(document))

    def spent(self) -> Decimal:
        return self.summary().spent_usd

    def attacker_generated_tokens(self) -> int:
        return self.summary().attacker_generated_tokens

    def token_accounting_available(self) -> bool:
        return self.summary().token_accounting_available

    def reserve(self, *, role: RoleName, reserved_usd: Decimal) -> str:
        amount = ceil_money(reserved_usd)
        if amount <= 0:
            raise LedgerError("reservation must be positive")

        def mutate(document: dict[str, Any]) -> str:
            summary = _summarize(document)
            if summary.spent_usd + amount > self._cap:
                raise CostCapExceeded(
                    spent_usd=summary.spent_usd,
                    cap_usd=self._cap,
                    estimated_usd=amount,
                )
            entry_id = uuid.uuid4().hex
            entries = document["entries"]
            if not isinstance(entries, list):
                raise LedgerError("ledger entries are corrupt")
            entries.append(
                {
                    "entry_id": entry_id,
                    "state": "reserved",
                    "role": role,
                    "reserved_usd": format(amount, "f"),
                    "settled_usd": None,
                    "cost_source": "none",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "reasoning_tokens": 0,
                    "reasoning_included_in_completion": True,
                    "generated_tokens": 0,
                    "reconciled": True,
                }
            )
            return entry_id

        return self._update(mutate)

    def settle(
        self,
        entry_id: str,
        *,
        cost_usd: Decimal,
        source: Literal["provider", "price_table"],
        usage: TokenUsage,
        reconciled: bool,
    ) -> None:
        amount = ceil_money(cost_usd)

        def mutate(document: dict[str, Any]) -> None:
            entry = _require_reserved(document, entry_id)
            entry["state"] = "settled"
            entry["settled_usd"] = format(amount, "f")
            entry["cost_source"] = source
            entry["prompt_tokens"] = usage.prompt_tokens
            entry["completion_tokens"] = usage.completion_tokens
            entry["reasoning_tokens"] = usage.reasoning_tokens
            entry["reasoning_included_in_completion"] = usage.reasoning_included_in_completion
            entry["generated_tokens"] = usage.generated_tokens
            entry["reconciled"] = reconciled

        self._update(mutate)

    def release(self, entry_id: str) -> None:
        def mutate(document: dict[str, Any]) -> None:
            entry = _require_reserved(document, entry_id)
            entry["state"] = "released"
            entry["settled_usd"] = "0"
            entry["cost_source"] = "none"

        self._update(mutate)

    def _update(self, mutate: Callable[[dict[str, Any]], T]) -> T:
        with self._thread:
            self._lock_path.touch(exist_ok=True)
            with self._lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    document = self._load()
                    result = mutate(document)
                    self._save(document)
                    return result
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "cap_usd": format(self._cap, "f"),
                "team_generated_token_budget": self._team_budget,
                "entries": [],
            }
        try:
            loaded: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise LedgerError("spend ledger is unreadable") from None
        if not isinstance(loaded, dict):
            raise LedgerError("spend ledger is corrupt")
        if loaded.get("schema_version") != LEDGER_SCHEMA_VERSION:
            raise LedgerError("spend ledger schema is not supported")
        try:
            stored_cap = ceil_money(Decimal(str(loaded.get("cap_usd"))))
        except (ArithmeticError, ValueError, TypeError):
            raise LedgerError("spend ledger cap is corrupt") from None
        if stored_cap != self._cap:
            raise LedgerError("spend ledger cap does not match this run")
        if loaded.get("team_generated_token_budget") != self._team_budget:
            raise LedgerError("spend ledger token budget does not match this run")
        if not isinstance(loaded.get("entries"), list):
            raise LedgerError("spend ledger entries are corrupt")
        return loaded

    def _save(self, document: dict[str, Any]) -> None:
        summary = _summarize(document)
        document["spent_usd"] = format(summary.spent_usd, "f")
        document["attacker_generated_tokens"] = summary.attacker_generated_tokens
        document["defender_generated_tokens"] = summary.defender_generated_tokens
        document["token_accounting_available"] = summary.token_accounting_available
        text = json.dumps(document, indent=2, sort_keys=True)
        scrubbed = redact_text(text)
        if scrubbed != text:
            raise LedgerError("refusing to persist credential material")
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)


def _money(value: object) -> Decimal:
    try:
        return ceil_money(Decimal(str(value)))
    except (ArithmeticError, ValueError, TypeError):
        raise LedgerError("ledger money is corrupt") from None


def _require_reserved(document: dict[str, Any], entry_id: str) -> dict[str, Any]:
    entries = document["entries"]
    if not isinstance(entries, list):
        raise LedgerError("ledger entries are corrupt")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("entry_id") == entry_id:
            if entry.get("state") != "reserved":
                raise LedgerError("ledger entry is not an open reservation")
            return entry
    raise LedgerError("ledger entry was not found")


def _summarize(document: dict[str, Any]) -> LedgerSummary:
    spent = Decimal("0")
    attacker = 0
    defender = 0
    available = True
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise LedgerError("ledger entries are corrupt")
    for entry in entries:
        if not isinstance(entry, dict):
            raise LedgerError("ledger entry is corrupt")
        state = entry.get("state")
        if state == "reserved":
            spent += _money(entry.get("reserved_usd"))
        elif state == "settled":
            spent += _money(entry.get("settled_usd"))
            generated = entry.get("generated_tokens")
            if not isinstance(generated, int) or generated < 0:
                raise LedgerError("ledger token count is corrupt")
            role = entry.get("role")
            if role == "attacker":
                attacker += generated
                if entry.get("reconciled") is not True:
                    available = False
            elif role == "defender":
                defender += generated
        elif state == "released":
            continue
        else:
            raise LedgerError("ledger entry state is corrupt")
    return LedgerSummary(
        spent_usd=ceil_money(spent),
        attacker_generated_tokens=attacker,
        defender_generated_tokens=defender,
        token_accounting_available=available,
    )
