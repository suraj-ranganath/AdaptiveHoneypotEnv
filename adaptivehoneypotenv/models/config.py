"""Run configuration for the live adapter. The provider key is not a field."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from adaptivehoneypotenv.contracts.limits import (
    DEFAULT_MODEL,
    DEFENDER_PER_CALL_TOKEN_CEILING,
    OPENROUTER_BASE_URL,
    TEAM_GENERATED_TOKEN_BUDGET,
    TIMEOUT_MAX_SECONDS,
)
from adaptivehoneypotenv.contracts.manifest import ResolvedManifest
from adaptivehoneypotenv.models.pricing import ceil_money

MAX_PROVIDER_ATTEMPTS = 3


@dataclass(frozen=True)
class AdapterConfig:
    """Caps copied from a resolved manifest, plus the local test base URL.

    ``from_manifest`` always uses the manifest base URL. Tests pass an
    explicit local URL; a scored manifest cannot retarget the provider.
    """

    cap_usd: Decimal
    ledger_path: Path
    model: str = DEFAULT_MODEL
    base_url: str = OPENROUTER_BASE_URL
    attacker_max_tokens: int = 256
    defender_max_tokens: int = 256
    attacker_timeout_seconds: float = 30
    defender_timeout_seconds: float = 30
    attacker_per_call_cap: int = 256
    defender_per_call_cap: int = 256
    team_token_budget: int = TEAM_GENERATED_TOKEN_BUDGET
    temperature: float | None = None
    seed: int | None = None
    max_attempts: int = MAX_PROVIDER_ATTEMPTS

    def __post_init__(self) -> None:
        if isinstance(self.cap_usd, float):
            raise TypeError("cap_usd must be Decimal, not float")
        cap = self.cap_usd if isinstance(self.cap_usd, Decimal) else Decimal(str(self.cap_usd))
        if not cap.is_finite() or cap <= 0:
            raise ValueError("cap_usd must be a positive finite number")
        object.__setattr__(self, "cap_usd", ceil_money(cap))
        if self.model != DEFAULT_MODEL:
            raise ValueError("pinned model is z-ai/glm-5.3-flash")
        _validate_base_url(self.base_url)
        _validate_timeout(self.attacker_timeout_seconds)
        _validate_timeout(self.defender_timeout_seconds)
        _validate_cap(self.attacker_per_call_cap, TEAM_GENERATED_TOKEN_BUDGET, "attacker")
        _validate_cap(
            self.defender_per_call_cap,
            DEFENDER_PER_CALL_TOKEN_CEILING,
            "defender",
        )
        if self.attacker_max_tokens < 1 or self.attacker_max_tokens > self.attacker_per_call_cap:
            raise ValueError("attacker max_tokens exceeds the per-call cap")
        if self.defender_max_tokens < 1 or self.defender_max_tokens > self.defender_per_call_cap:
            raise ValueError("defender max_tokens exceeds the per-call cap")
        if self.team_token_budget != TEAM_GENERATED_TOKEN_BUDGET:
            raise ValueError("team generated-token budget is 24000")
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("temperature is outside 0..2")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("provider attempts must be from 1 to 5")
        if not isinstance(self.ledger_path, Path):
            raise TypeError("ledger_path must be a Path")

    @classmethod
    def from_manifest(cls, manifest: ResolvedManifest, *, ledger_path: Path) -> AdapterConfig:
        """Copy caps from the manifest. The base URL is not overridable here."""

        return cls(
            cap_usd=manifest.caps.max_cost_usd,
            ledger_path=ledger_path,
            model=manifest.routing.model,
            base_url=manifest.routing.base_url,
            attacker_max_tokens=manifest.generation.attacker_max_tokens,
            defender_max_tokens=manifest.generation.defender_max_tokens,
            attacker_timeout_seconds=manifest.generation.attacker_timeout_seconds,
            defender_timeout_seconds=manifest.generation.defender_timeout_seconds,
            attacker_per_call_cap=manifest.caps.attacker_per_call_generated_token_cap,
            defender_per_call_cap=manifest.caps.defender_per_call_generated_token_cap,
            team_token_budget=manifest.caps.team_generated_token_budget,
            temperature=manifest.generation.temperature,
            seed=manifest.generation.seed,
            max_attempts=MAX_PROVIDER_ATTEMPTS,
        )


def _validate_base_url(base_url: str) -> None:
    if "://" not in base_url:
        raise ValueError("base_url must be an http(s) URL")
    scheme, rest = base_url.split("://", 1)
    host = rest.split("/", 1)[0]
    if scheme not in {"http", "https"} or not host or host.startswith("."):
        raise ValueError("base_url must be an http(s) URL")
    if "@" in host:
        raise ValueError("base_url must not embed credentials")


def _validate_timeout(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout must be numeric")
    if not 0 < value <= TIMEOUT_MAX_SECONDS:
        raise ValueError("timeout is outside the allowed range")


def _validate_cap(value: int, ceiling: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} cap must be an int")
    if not 1 <= value <= ceiling:
        raise ValueError(f"{label} per-call cap is outside the allowed range")
