"""Resolved manifest: pins, numeric cap, and no key material."""

from decimal import Decimal
from pathlib import Path

import pytest
from adaptivehoneypotenv.contracts.limits import (
    DEMO_MAX_COST_USD,
    LIVE_MODEL_ADAPTER_ID,
    TEST_DOUBLE_MODEL_ADAPTER_ID,
)
from adaptivehoneypotenv.contracts.manifest import (
    DemoProfile,
    DevelopmentManifest,
    LiveScoredManifest,
    SecretReference,
    load_demo_profile,
    parse_manifest,
)
from pydantic import ValidationError


def _sha(byte: str) -> str:
    return byte * 32


def live_payload() -> dict[str, object]:
    return {
        "purpose": "live",
        "model_adapter": LIVE_MODEL_ADAPTER_ID,
        "comparison_fixture_id": "block-1",
        "layout_seed": 17,
        "policy_seed": 2,
        "decoy_seed": 3,
        "prompt_hashes": [{"name": "attacker", "sha256": _sha("ab")}],
        "schema_hashes": [{"name": "action", "sha256": _sha("cd")}],
        "actors": [
            {"actor_id": "attacker-1", "role": "attacker"},
            {"actor_id": "attacker-2", "role": "attacker"},
            {"actor_id": "attacker-3", "role": "attacker"},
            {"actor_id": "defender", "role": "defender"},
        ],
        "policy": {
            "policy": "adaptive_llm",
            "track": "contextual",
            "awareness": "naive",
            "team": "trio",
            "objective_mode": "workflow",
        },
        "routing": {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "z-ai/glm-5.3-flash",
            "allow_fallbacks": False,
        },
        "generation": {
            "temperature": 0.2,
            "attacker_max_tokens": 256,
            "defender_max_tokens": 256,
            "attacker_timeout_seconds": 30,
            "defender_timeout_seconds": 30,
        },
        "caps": {
            "max_cost_usd": "5.0",
            "attacker_per_call_generated_token_cap": 256,
            "defender_per_call_generated_token_cap": 256,
        },
        "pins": {
            "honeyval_git_sha": "86272d8d1fb4b3090037561cc31b28dc8a8350f8",
            "agentenv_git_sha": "666c26a586c9118599352c7caa52f53d2e89fb62",
            "target_image_digest": "sha256:" + _sha("12"),
            "bridge_image_digest": "sha256:" + _sha("34"),
            "lock_sha256": _sha("56"),
        },
    }


def test_live_manifest_requires_numeric_cap_and_pins() -> None:
    manifest = parse_manifest(live_payload())
    assert isinstance(manifest, LiveScoredManifest)
    assert manifest.caps.max_cost_usd == Decimal("5.0")
    assert manifest.provider_credential.env_var_name == "OPENROUTER_API_KEY"
    assert manifest.caps.team_attempt_budget == 90
    assert manifest.caps.team_generated_token_budget == 24_000
    assert manifest.caps.attempts_per_defender_decision == 6
    assert manifest.caps.max_decoys == 2
    assert manifest.caps.description_max_unicode_chars == 240
    assert manifest.caps.files_per_decoy == 2
    assert manifest.caps.bytes_per_decoy == 4_096
    assert manifest.validity.refusals_are_not_defender_wins is True
    assert manifest.routing.allow_fallbacks is False

    missing_pins = live_payload()
    del missing_pins["pins"]
    with pytest.raises(ValidationError):
        parse_manifest(missing_pins)

    missing_cap = live_payload()
    assert isinstance(missing_cap["caps"], dict)
    del missing_cap["caps"]["max_cost_usd"]
    with pytest.raises(ValidationError):
        parse_manifest(missing_cap)

    null_cap = live_payload()
    assert isinstance(null_cap["caps"], dict)
    null_cap["caps"]["max_cost_usd"] = None
    with pytest.raises(ValidationError):
        parse_manifest(null_cap)

    raised_budget = live_payload()
    assert isinstance(raised_budget["caps"], dict)
    raised_budget["caps"]["team_attempt_budget"] = 91
    with pytest.raises(ValidationError):
        parse_manifest(raised_budget)


def test_scripted_test_double_cannot_be_selected_for_live_or_scored_runs() -> None:
    payload = live_payload()
    payload["model_adapter"] = TEST_DOUBLE_MODEL_ADAPTER_ID
    with pytest.raises(ValidationError):
        parse_manifest(payload)
    payload["purpose"] = "scored"
    with pytest.raises(ValidationError):
        parse_manifest(payload)

    development = live_payload()
    development["purpose"] = "development"
    development["model_adapter"] = TEST_DOUBLE_MODEL_ADAPTER_ID
    del development["pins"]
    manifest = parse_manifest(development)
    assert isinstance(manifest, DevelopmentManifest)
    assert manifest.model_adapter == TEST_DOUBLE_MODEL_ADAPTER_ID
    assert manifest.pins is None


def test_no_field_can_carry_a_key_value() -> None:
    assert set(SecretReference.model_fields) == {"env_var_name"}
    payload = live_payload()
    payload["comparison_fixture_id"] = "sk-or-v1-test-only-not-a-credential"
    with pytest.raises(ValidationError):
        parse_manifest(payload)

    extra = live_payload()
    extra["api_key"] = "sk-or-v1-test-only-not-a-credential"
    with pytest.raises(ValidationError):
        parse_manifest(extra)

    nested = live_payload()
    nested["provider_credential"] = {
        "env_var_name": "OPENROUTER_API_KEY",
        "value": "sk-or-v1-test-only-not-a-credential",
    }
    with pytest.raises(ValidationError):
        parse_manifest(nested)

    forbidden_names = {"api_key", "api_key_value", "password", "token", "secret_value"}
    for model in (LiveScoredManifest, DevelopmentManifest, SecretReference, DemoProfile):
        assert forbidden_names.isdisjoint(model.model_fields)


def test_demo_profile_sets_the_operator_cap() -> None:
    profile = load_demo_profile(Path("demo.yaml"))
    assert profile.runtime.max_cost_usd == DEMO_MAX_COST_USD == Decimal("5.0")
    assert profile.attacker.model == "z-ai/glm-5.3-flash"
    assert profile.defender.model == "z-ai/glm-5.3-flash"
    with pytest.raises(ValidationError):
        DemoProfile.model_validate(
            {
                **profile.model_dump(mode="json"),
                "runtime": {"max_cost_usd": None},
            }
        )
