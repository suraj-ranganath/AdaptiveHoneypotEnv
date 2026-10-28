"""Defender observation allowlist and padded encoding."""

import pytest
from adaptivehoneypotenv.contracts.limits import (
    MAX_ACTIVITIES_PER_DECISION,
    MAX_DECOYS,
)
from adaptivehoneypotenv.contracts.observations import (
    ACTIVITY_STRIDE,
    OWNED_STRIDE,
    PAD,
    DefenderObservation,
    OwnedDeployment,
    RedactedActivity,
    encode_observation,
    project_search_term,
)
from adaptivehoneypotenv.contracts.telemetry import (
    DefenderVisibleToolName,
    HttpMethodCategory,
    HttpStatusCategory,
    PathCategory,
)
from pydantic import ValidationError
from tests.support import sample_observation

FORBIDDEN_FIELD_NAMES = {
    "private_goal",
    "goal",
    "credential",
    "credentials",
    "password",
    "canary",
    "flag",
    "registry",
    "messageboard",
    "jwt",
    "api_key",
    "authorization",
    "body",
    "secret",
    "workflow_label",
    "post_text",
    "posts",
}


def _schema_property_names(schema: object, found: set[str] | None = None) -> set[str]:
    names: set[str] = set() if found is None else found
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.update(str(key) for key in properties)
            for child in properties.values():
                _schema_property_names(child, names)
        for key in ("$defs", "definitions"):
            definitions = schema.get(key)
            if isinstance(definitions, dict):
                for child in definitions.values():
                    _schema_property_names(child, names)
        for key in ("anyOf", "oneOf", "allOf"):
            options = schema.get(key)
            if isinstance(options, list):
                for child in options:
                    _schema_property_names(child, names)
        items = schema.get("items")
        if items is not None:
            _schema_property_names(items, names)
    return names


def test_private_goal_credentials_registry_and_messageboard_absent_from_observations() -> None:
    observation = sample_observation()
    names = _schema_property_names(DefenderObservation.model_json_schema())
    names.update(DefenderObservation.model_fields)
    names.update(RedactedActivity.model_fields)
    names.update(OwnedDeployment.model_fields)
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(names)
    assert "post_to_messageboard" not in {item.value for item in DefenderVisibleToolName}
    assert "read_messageboard" not in {item.value for item in DefenderVisibleToolName}

    payload = observation.model_dump(mode="json")
    payload["private_goal"] = "release"
    with pytest.raises(ValidationError):
        DefenderObservation.model_validate(payload)
    payload = observation.model_dump(mode="json")
    payload["messageboard"] = []
    with pytest.raises(ValidationError):
        DefenderObservation.model_validate(payload)

    with pytest.raises(ValidationError):
        RedactedActivity.model_validate(
            {
                "tool_name": "post_to_messageboard",
                "path_category": "none",
                "actor_id": "attacker-1",
                "attempt_number": 1,
                "sequence_number": 1,
                "duration_ns": 1,
            }
        )

    sanitized = project_search_term(
        "backup synthetic-fixture-literal token=abc",
        fixture_literals=("synthetic-fixture-literal",),
    )
    assert "synthetic-fixture-literal" not in sanitized
    assert "[redacted]" in sanitized

    activity = RedactedActivity(
        tool_name=DefenderVisibleToolName.search_files,
        normalized_path="ops/ci",
        path_category=PathCategory.ops_ci,
        sanitized_search_term=sanitized,
        returned_hit_count=2,
        actor_id="attacker-2",
        attempt_number=4,
        sequence_number=9,
        duration_ns=15,
    )
    with_activity = sample_observation(activity=(activity,))
    empty = sample_observation()
    encoded_empty = encode_observation(empty)
    encoded_full = encode_observation(with_activity)
    assert len(encoded_empty.activity) == len(encoded_full.activity)
    assert len(encoded_empty.activity) == MAX_ACTIVITIES_PER_DECISION * ACTIVITY_STRIDE
    assert len(encoded_empty.owned_deployments) == MAX_DECOYS * OWNED_STRIDE
    assert encoded_empty.pad == PAD
    assert encoded_empty.action_mask == tuple(1 if bit else 0 for bit in empty.safe_action_mask)
    assert encoded_full.activity[0] != PAD
    assert PAD in encoded_empty.activity

    service = RedactedActivity(
        tool_name=DefenderVisibleToolName.request_service,
        path_category=PathCategory.service,
        http_method=HttpMethodCategory.POST,
        http_status_category=HttpStatusCategory.success,
        actor_id="attacker-1",
        attempt_number=2,
        sequence_number=3,
        duration_ns=8,
    )
    assert service.normalized_path is None
    dumped = service.model_dump_json()
    assert "messageboard" not in dumped
    assert "authorization" not in dumped
