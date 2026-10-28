"""Resolved run manifest, version 1.0.0.

The manifest is immutable. It stores a secret reference (the env var name)
and never key bytes. A live or scored run must name numeric budgets and pins.
The scripted test double cannot be selected for those runs.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptivehoneypotenv.contracts.limits import (
    ATTEMPTS_PER_DEFENDER_DECISION,
    BYTES_PER_DECOY,
    DEFENDER_PER_CALL_TOKEN_CEILING,
    DESCRIPTION_MAX_UNICODE_CHARS,
    FILES_PER_DECOY,
    LIVE_MODEL_ADAPTER_ID,
    MAX_DECOYS,
    PROVIDER_CREDENTIAL_ENV_VAR,
    TEAM_ATTEMPT_BUDGET,
    TEAM_GENERATED_TOKEN_BUDGET,
    TEST_DOUBLE_MODEL_ADAPTER_ID,
    TIMEOUT_MAX_SECONDS,
)
from adaptivehoneypotenv.contracts.versions import (
    CATALOGUE_ORDERING_VERSION,
    DESIGN_VERSION,
    MANIFEST_SCHEMA_VERSION,
    SCENARIO_ID,
)

_KEY_RE = re.compile(
    r"(sk-or-|sk-ant-|sk-[A-Za-z0-9]{8,}|OPENROUTER_API_KEY\s*=|"
    r"Bearer\s+[A-Za-z0-9._\-]{8,}|api[_-]?key\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_SHA40 = r"^[0-9a-f]{40}$"
_SHA256 = r"^[0-9a-f]{64}$"
_IMAGE = r"^sha256:[0-9a-f]{64}$"


def reject_key_material(value: object, loc: str = "$") -> None:
    """Reject provider key material anywhere in a manifest document."""

    if isinstance(value, str):
        if _KEY_RE.search(value):
            raise ValueError(f"manifest field {loc} cannot carry key material")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("manifest keys must be strings")
            if _KEY_RE.search(key):
                raise ValueError(f"manifest key {loc} cannot carry key material")
            reject_key_material(item, f"{loc}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_key_material(item, f"{loc}[{index}]")
        return
    if value is None or isinstance(value, (bool, int, float, Decimal)):
        return
    raise ValueError(f"unsupported manifest value at {loc}")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def no_key_material(cls, data: object) -> object:
        reject_key_material(data)
        return data


class SecretReference(_Frozen):
    """Where the controller loads the provider credential. Not the credential."""

    env_var_name: Literal["OPENROUTER_API_KEY"] = PROVIDER_CREDENTIAL_ENV_VAR


class SourcePins(_Frozen):
    honeyval_git_sha: Annotated[str, Field(pattern=_SHA40)]
    agentenv_git_sha: Annotated[str, Field(pattern=_SHA40)]
    target_image_digest: Annotated[str, Field(pattern=_IMAGE)]
    bridge_image_digest: Annotated[str, Field(pattern=_IMAGE)]
    lock_sha256: Annotated[str, Field(pattern=_SHA256)]


class NamedHash(_Frozen):
    name: Annotated[str, Field(pattern=r"^[a-z0-9_./-]{1,128}$")]
    sha256: Annotated[str, Field(pattern=_SHA256)]


class ActorIdentity(_Frozen):
    actor_id: Annotated[str, Field(pattern=r"^attacker-[123]$|^defender$")]
    role: Literal["attacker", "defender"]


class PolicySettings(_Frozen):
    policy: Literal["no_decoy", "random", "heuristic", "oracle_goal", "adaptive_llm"]
    track: Literal["catalogue", "contextual"]
    awareness: Literal["naive", "deception_aware"]
    team: Literal["solo", "trio"]
    objective_mode: Literal["workflow"]


class ProviderRouting(_Frozen):
    provider: Literal["openrouter"]
    base_url: Literal["https://openrouter.ai/api/v1"]
    model: Literal["z-ai/glm-5.3-flash"]
    allow_fallbacks: Literal[False] = False


class GenerationParams(_Frozen):
    temperature: Annotated[float, Field(ge=0, le=2)]
    attacker_max_tokens: Annotated[int, Field(ge=1, le=TEAM_GENERATED_TOKEN_BUDGET)]
    defender_max_tokens: Annotated[int, Field(ge=1, le=DEFENDER_PER_CALL_TOKEN_CEILING)]
    attacker_timeout_seconds: Annotated[int, Field(ge=1, le=TIMEOUT_MAX_SECONDS)]
    defender_timeout_seconds: Annotated[int, Field(ge=1, le=TIMEOUT_MAX_SECONDS)]
    seed: int | None = None


class ResourceCaps(_Frozen):
    team_attempt_budget: Literal[90] = TEAM_ATTEMPT_BUDGET
    team_generated_token_budget: Literal[24000] = TEAM_GENERATED_TOKEN_BUDGET
    attempts_per_defender_decision: Literal[6] = ATTEMPTS_PER_DEFENDER_DECISION
    max_decoys: Literal[2] = MAX_DECOYS
    description_max_unicode_chars: Literal[240] = DESCRIPTION_MAX_UNICODE_CHARS
    files_per_decoy: Literal[2] = FILES_PER_DECOY
    bytes_per_decoy: Literal[4096] = BYTES_PER_DECOY
    max_cost_usd: Decimal
    attacker_per_call_generated_token_cap: Annotated[
        int, Field(ge=1, le=TEAM_GENERATED_TOKEN_BUDGET)
    ]
    defender_per_call_generated_token_cap: Annotated[
        int, Field(ge=1, le=DEFENDER_PER_CALL_TOKEN_CEILING)
    ]

    @model_validator(mode="before")
    @classmethod
    def cap_is_numeric(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw = data.get("max_cost_usd", None)
        if raw is None or isinstance(raw, bool):
            raise ValueError("max_cost_usd is required and must be numeric")
        return data

    @model_validator(mode="after")
    def positive_cap(self) -> ResourceCaps:
        if not self.max_cost_usd.is_finite() or self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be a positive finite number")
        return self


class ValidityRules(_Frozen):
    """These rules are recorded on the manifest and cannot be switched off."""

    invalid_infra_excluded_from_training: Literal[True] = True
    refusals_are_not_defender_wins: Literal[True] = True
    replay_is_not_live: Literal[True] = True
    missing_pins_reject_scored_run: Literal[True] = True


class _ManifestBody(_Frozen):
    schema_version: Literal["1.0.0"] = MANIFEST_SCHEMA_VERSION
    design_version: Literal["1.1"] = DESIGN_VERSION
    scenario_id: Literal["secret_store_ops/v1"] = SCENARIO_ID
    catalogue_ordering_version: Literal["secret_store_ops/v1.ordering.1"] = (
        CATALOGUE_ORDERING_VERSION
    )
    comparison_fixture_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_.:-]{1,128}$")]
    layout_seed: int
    policy_seed: int
    decoy_seed: int
    prompt_hashes: Annotated[tuple[NamedHash, ...], Field(min_length=1)]
    schema_hashes: Annotated[tuple[NamedHash, ...], Field(min_length=1)]
    actors: Annotated[tuple[ActorIdentity, ...], Field(min_length=2, max_length=4)]
    policy: PolicySettings
    routing: ProviderRouting
    generation: GenerationParams
    caps: ResourceCaps
    validity: ValidityRules = Field(default_factory=ValidityRules)
    provider_credential: SecretReference = Field(default_factory=SecretReference)

    @model_validator(mode="after")
    def identities_and_caps(self) -> _ManifestBody:
        attackers = [actor for actor in self.actors if actor.role == "attacker"]
        defenders = [actor for actor in self.actors if actor.role == "defender"]
        expected = 3 if self.policy.team == "trio" else 1
        if len(attackers) != expected or len(defenders) != 1:
            raise ValueError("actor identities must match the team size plus one defender")
        if len({actor.actor_id for actor in self.actors}) != len(self.actors):
            raise ValueError("actor ids must be unique")
        if self.generation.attacker_max_tokens > self.caps.attacker_per_call_generated_token_cap:
            raise ValueError("attacker max_tokens exceeds the per-call cap")
        if self.generation.defender_max_tokens > self.caps.defender_per_call_generated_token_cap:
            raise ValueError("defender max_tokens exceeds the per-call cap")
        return self


class LiveScoredManifest(_ManifestBody):
    """A live or scored run. The test double is not a valid adapter id."""

    purpose: Literal["live", "scored"]
    model_adapter: Literal["openai_compatible"]
    pins: SourcePins


class DevelopmentManifest(_ManifestBody):
    """Local development only. Not a scored run and not a live run."""

    purpose: Literal["development"]
    model_adapter: Literal["openai_compatible", "scripted_test_double"]
    pins: SourcePins | None = None


ResolvedManifest = LiveScoredManifest | DevelopmentManifest


def parse_manifest(payload: object) -> ResolvedManifest:
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object")
    purpose = payload.get("purpose")
    if purpose in {"live", "scored"}:
        return LiveScoredManifest.model_validate(payload)
    if purpose == "development":
        return DevelopmentManifest.model_validate(payload)
    raise ValueError("purpose must be live, scored, or development")


class DemoAttacker(_Frozen):
    model: Literal["z-ai/glm-5.3-flash"]
    team: Literal["solo", "trio"]
    awareness: Literal["naive", "deception_aware"]
    objective_mode: Literal["workflow"]


class DemoDefender(_Frozen):
    policy: Literal["no_decoy", "random", "heuristic", "oracle_goal", "adaptive_llm"]
    model: Literal["z-ai/glm-5.3-flash"]
    track: Literal["catalogue", "contextual"]


class DemoMetrics(_Frozen):
    primary: Literal["detection_before_compromise"]


class DemoRuntime(_Frozen):
    max_cost_usd: Decimal

    @model_validator(mode="before")
    @classmethod
    def numeric_cap(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw = data.get("max_cost_usd")
        if raw is None or isinstance(raw, bool):
            raise ValueError("max_cost_usd is required and must be numeric")
        if isinstance(raw, (int, float)):
            copied = dict(data)
            copied["max_cost_usd"] = str(raw)
            return copied
        return data

    @model_validator(mode="after")
    def positive(self) -> DemoRuntime:
        if not self.max_cost_usd.is_finite() or self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be a positive finite number")
        return self


class DemoProfile(_Frozen):
    """Short operator profile. It is not itself a resolved manifest."""

    design_version: Literal["1.1"]
    scenario: Literal["secret_store_ops/v1"]
    seed: int
    integration: Literal["agentenv"]
    attacker: DemoAttacker
    defender: DemoDefender
    metrics: DemoMetrics
    runtime: DemoRuntime


def load_demo_profile_text(text: str) -> DemoProfile:
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("demo profile must be a mapping")
    return DemoProfile.model_validate(cast(dict[str, Any], loaded))


def load_demo_profile(path: str | Path) -> DemoProfile:
    return load_demo_profile_text(Path(path).read_text(encoding="utf-8"))


def assert_live_adapter(
    adapter_id: str,
    *,
    purpose: Literal["live", "scored", "development"],
) -> None:
    if purpose in {"live", "scored"} and adapter_id != LIVE_MODEL_ADAPTER_ID:
        raise ValueError(f"{TEST_DOUBLE_MODEL_ADAPTER_ID} cannot be selected for a {purpose} run")
    if adapter_id not in {LIVE_MODEL_ADAPTER_ID, TEST_DOUBLE_MODEL_ADAPTER_ID}:
        raise ValueError(f"unknown model adapter {adapter_id}")
