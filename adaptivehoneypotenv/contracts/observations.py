"""Safe defender observation, version 1.0.0.

This is an allowlisted typed projection. It is not a scrubber over a world
object. Messageboard operations, the private goal, credentials, canaries,
flags, and the decoy registry are not fields of this model.
"""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from adaptivehoneypotenv.contracts.actions import (
    COMPATIBILITY,
    CONTEXT_ORDER,
    TEMPLATE_ORDER,
    ContextId,
    SlotId,
    TemplateId,
    audit_description,
    validate_description_id,
)
from adaptivehoneypotenv.contracts.catalogue import DiscreteCatalogue, build_catalogue
from adaptivehoneypotenv.contracts.limits import (
    ATTEMPTS_PER_DEFENDER_DECISION,
    DESCRIPTION_MAX_UNICODE_CHARS,
    MAX_ACTIVITIES_PER_DECISION,
    MAX_DECOYS,
    SEARCH_QUERY_MAX_CHARS,
    TEAM_ATTEMPT_BUDGET,
    TEAM_GENERATED_TOKEN_BUDGET,
)
from adaptivehoneypotenv.contracts.telemetry import (
    DefenderVisibleToolName,
    HttpMethodCategory,
    HttpStatusCategory,
    PathCategory,
)
from adaptivehoneypotenv.contracts.tools import validate_workspace_path
from adaptivehoneypotenv.contracts.versions import (
    CATALOGUE_ORDERING_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    SCENARIO_ID,
)

PAD: Final = -1
SEARCH_PAD_CHARS: Final = SEARCH_QUERY_MAX_CHARS
ACTIVITY_HEADER_WIDTH: Final = 10
ACTIVITY_STRIDE: Final = ACTIVITY_HEADER_WIDTH + SEARCH_PAD_CHARS
OWNED_STRIDE: Final = 8 + DESCRIPTION_MAX_UNICODE_CHARS

_ACTOR_ID_RE = re.compile(r"^attacker-[123]$")
_DEPLOYMENT_ID_RE = re.compile(r"^dep_[a-z0-9]{8,32}$")
_CREDENTIAL_SHAPE_RE = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._\-+/=]{6,}|sk-[A-Za-z0-9_\-]{4,}|"
    r"password\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S+)"
)

TOOL_CODES: Final[dict[DefenderVisibleToolName, int]] = {
    DefenderVisibleToolName.list_directory: 1,
    DefenderVisibleToolName.search_files: 2,
    DefenderVisibleToolName.read_file: 3,
    DefenderVisibleToolName.request_service: 4,
    DefenderVisibleToolName.finish: 5,
}
PATH_CODES: Final[dict[PathCategory, int]] = {
    PathCategory.none: 1,
    PathCategory.source: 2,
    PathCategory.ops_deploy: 3,
    PathCategory.ops_integrations: 4,
    PathCategory.ops_ci: 5,
    PathCategory.ops_runbooks: 6,
    PathCategory.service: 7,
}
HTTP_METHOD_CODES: Final[dict[HttpMethodCategory, int]] = {
    HttpMethodCategory.none: 1,
    HttpMethodCategory.GET: 2,
    HttpMethodCategory.POST: 3,
}
HTTP_STATUS_CODES: Final[dict[HttpStatusCategory, int]] = {
    HttpStatusCategory.none: 1,
    HttpStatusCategory.success: 2,
    HttpStatusCategory.client_error: 3,
    HttpStatusCategory.server_error: 4,
    HttpStatusCategory.other: 5,
}
TEMPLATE_CODES: Final[dict[TemplateId, int]] = {
    template: index + 1 for index, template in enumerate(TEMPLATE_ORDER)
}
SLOT_CODES: Final[dict[SlotId, int]] = {
    SlotId.deployment_notes: 1,
    SlotId.integration_records: 2,
    SlotId.ci_records: 3,
    SlotId.runbooks: 4,
}
CONTEXT_CODES: Final[dict[ContextId, int]] = {
    ContextId.release: 1,
    ContextId.backup: 2,
}
TRACK_CODES: Final[dict[str, int]] = {"catalogue": 1, "contextual": 2}


class CompatibilityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    template_id: TemplateId
    slot_ids: tuple[SlotId, ...]


def frozen_compatibility() -> tuple[CompatibilityEntry, ...]:
    return tuple(
        CompatibilityEntry(template_id=template, slot_ids=COMPATIBILITY[template])
        for template in TEMPLATE_ORDER
    )


def project_search_term(query: str, *, fixture_literals: tuple[str, ...] = ()) -> str:
    """Typed projection for one search string. Not a recursive world scrub."""

    if len(query) > SEARCH_QUERY_MAX_CHARS:
        raise ValueError("search term exceeds the query cap")
    redacted = query
    for literal in fixture_literals:
        if len(literal) < 4:
            continue
        redacted = redacted.replace(literal, "[redacted]")
    return _CREDENTIAL_SHAPE_RE.sub("[redacted]", redacted)


class RedactedActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tool_name: DefenderVisibleToolName
    normalized_path: str | None = None
    path_category: PathCategory
    sanitized_search_term: Annotated[str, Field(max_length=SEARCH_QUERY_MAX_CHARS)] = ""
    search_clipped: bool = False
    returned_hit_count: Annotated[int, Field(ge=0, le=100)] = 0
    http_method: HttpMethodCategory = HttpMethodCategory.none
    http_status_category: HttpStatusCategory = HttpStatusCategory.none
    actor_id: str
    attempt_number: Annotated[int, Field(ge=1, le=TEAM_ATTEMPT_BUDGET)]
    sequence_number: Annotated[int, Field(ge=0)]
    duration_ns: Annotated[int, Field(ge=0)]

    @field_validator("actor_id")
    @classmethod
    def actor_ok(cls, value: str) -> str:
        if not _ACTOR_ID_RE.fullmatch(value):
            raise ValueError("activity actor_id must be attacker-1, attacker-2, or attacker-3")
        return value

    @field_validator("normalized_path")
    @classmethod
    def path_ok(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_workspace_path(value)

    @model_validator(mode="after")
    def tool_fields(self) -> RedactedActivity:
        if self.tool_name is DefenderVisibleToolName.request_service:
            if self.http_method is HttpMethodCategory.none:
                raise ValueError("service activity needs an HTTP method category")
            if self.path_category is not PathCategory.service:
                raise ValueError("service activity uses the service path category")
        else:
            if self.http_method is not HttpMethodCategory.none:
                raise ValueError("only service activity sets an HTTP method")
            if self.http_status_category is not HttpStatusCategory.none:
                raise ValueError("only service activity sets an HTTP status category")
        if (
            self.tool_name is not DefenderVisibleToolName.search_files
            and self.sanitized_search_term
        ):
            raise ValueError("search terms are only retained for search_files")
        return self


class OwnedDeployment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    deployment_id: str
    template_id: TemplateId
    slot_id: SlotId
    context_id: ContextId
    track: Literal["catalogue", "contextual"]
    description_id: str | None = None
    description: str | None = None
    status: Literal["committed"]

    @field_validator("deployment_id")
    @classmethod
    def deployment_id_ok(cls, value: str) -> str:
        if not _DEPLOYMENT_ID_RE.fullmatch(value):
            raise ValueError("deployment_id must be a public dep_ id")
        return value

    @model_validator(mode="after")
    def public_spec_only(self) -> OwnedDeployment:
        if self.slot_id not in COMPATIBILITY[self.template_id]:
            raise ValueError("owned deployment breaks the compatibility matrix")
        if self.track == "catalogue":
            if self.description_id is None or self.description is not None:
                raise ValueError("catalogue deployments carry description_id only")
            validate_description_id(self.description_id)
        else:
            if self.description is None or self.description_id is not None:
                raise ValueError("contextual deployments carry description only")
            if len(self.description) > DESCRIPTION_MAX_UNICODE_CHARS:
                raise ValueError("description exceeds 240 characters")
            violations = audit_description(self.description)
            if violations:
                raise ValueError(f"description failed audit: {', '.join(violations)}")
        return self


class DefenderObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = OBSERVATION_SCHEMA_VERSION
    scenario_id: Literal["secret_store_ops/v1"] = SCENARIO_ID
    catalogue_ordering_version: Literal["secret_store_ops/v1.ordering.1"] = (
        CATALOGUE_ORDERING_VERSION
    )
    description_ids: tuple[str, ...]
    owned_deployments: Annotated[
        tuple[OwnedDeployment, ...],
        Field(max_length=MAX_DECOYS),
    ] = ()
    compatibility: tuple[CompatibilityEntry, ...]
    contexts: tuple[ContextId, ...]
    remaining_decoy_budget: Annotated[int, Field(ge=0, le=MAX_DECOYS)]
    safe_action_mask: tuple[bool, ...]
    catalogue_size: Annotated[int, Field(ge=1)]
    remaining_team_attempts: Annotated[int, Field(ge=0, le=TEAM_ATTEMPT_BUDGET)]
    remaining_team_generated_tokens: Annotated[int, Field(ge=0, le=TEAM_GENERATED_TOKEN_BUDGET)]
    activity: Annotated[
        tuple[RedactedActivity, ...],
        Field(max_length=MAX_ACTIVITIES_PER_DECISION),
    ] = ()

    @model_validator(mode="after")
    def allowlist_holds(self) -> DefenderObservation:
        if self.compatibility != frozen_compatibility():
            raise ValueError("compatibility catalogue is frozen")
        if self.contexts != CONTEXT_ORDER:
            raise ValueError("contexts are release and backup")
        if len(self.safe_action_mask) != self.catalogue_size:
            raise ValueError("safe action mask length must equal the catalogue size")
        catalogue = build_catalogue(self.description_ids)
        if catalogue.ordering_version != self.catalogue_ordering_version:
            raise ValueError("catalogue ordering version mismatch")
        if len(catalogue.plans) != self.catalogue_size:
            raise ValueError("catalogue_size does not match the description list")
        occupied = tuple(item.slot_id for item in self.owned_deployments)
        if len(occupied) != len(set(occupied)):
            raise ValueError("owned deployments must use distinct slots")
        for item in self.owned_deployments:
            if item.track == "catalogue" and item.description_id not in self.description_ids:
                raise ValueError("owned description_id is not in the scenario list")
        if self.remaining_decoy_budget != MAX_DECOYS - len(self.owned_deployments):
            raise ValueError("remaining decoy budget is the global remainder")
        if len(self.activity) > ATTEMPTS_PER_DEFENDER_DECISION:
            raise ValueError("activity window exceeds the attempts per decision")
        return self


class EncodedObservation(BaseModel):
    """Fixed-width integer arrays for a future text-free Gymnasium wrapper.

    Unused slots use ``pad`` (-1). Width depends on the frozen description
    list only through ``action_mask``, which is exactly ``catalogue_size``.
    Activity and owned-deployment arrays are padded to their episode caps.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = OBSERVATION_SCHEMA_VERSION
    pad: Literal[-1] = PAD
    activity: tuple[int, ...]
    owned_deployments: tuple[int, ...]
    action_mask: tuple[int, ...]
    remaining_decoy_budget: int
    remaining_team_attempts: int
    remaining_team_generated_tokens: int

    @model_validator(mode="after")
    def widths(self) -> EncodedObservation:
        expected_activity = MAX_ACTIVITIES_PER_DECISION * ACTIVITY_STRIDE
        expected_owned = MAX_DECOYS * OWNED_STRIDE
        if len(self.activity) != expected_activity:
            raise ValueError("activity encoding is not the padded width")
        if len(self.owned_deployments) != expected_owned:
            raise ValueError("owned-deployment encoding is not the padded width")
        return self


def _actor_code(actor_id: str) -> int:
    return int(actor_id.rsplit("-", 1)[1])


def _encode_activity(activity: RedactedActivity) -> list[int]:
    chars = [ord(char) for char in activity.sanitized_search_term]
    padded = chars + [PAD] * (SEARCH_PAD_CHARS - len(chars))
    header = [
        TOOL_CODES[activity.tool_name],
        PATH_CODES[activity.path_category],
        HTTP_METHOD_CODES[activity.http_method],
        HTTP_STATUS_CODES[activity.http_status_category],
        _actor_code(activity.actor_id),
        activity.attempt_number,
        activity.sequence_number,
        activity.returned_hit_count,
        1 if activity.search_clipped else 0,
        activity.duration_ns,
    ]
    return header + padded


def _encode_owned(deployment: OwnedDeployment, description_ids: tuple[str, ...]) -> list[int]:
    if deployment.track == "catalogue":
        assert deployment.description_id is not None
        description_index = description_ids.index(deployment.description_id)
        text = ""
    else:
        description_index = PAD
        text = deployment.description or ""
    chars = [ord(char) for char in text][:DESCRIPTION_MAX_UNICODE_CHARS]
    padded = chars + [PAD] * (DESCRIPTION_MAX_UNICODE_CHARS - len(chars))
    header = [
        TEMPLATE_CODES[deployment.template_id],
        SLOT_CODES[deployment.slot_id],
        CONTEXT_CODES[deployment.context_id],
        TRACK_CODES[deployment.track],
        description_index,
        1,
        len(text),
        0,
    ]
    return header + padded


def encode_observation(observation: DefenderObservation) -> EncodedObservation:
    """Pad the allowlisted observation into bounded integer arrays."""

    activity_slots = [_encode_activity(item) for item in observation.activity]
    while len(activity_slots) < MAX_ACTIVITIES_PER_DECISION:
        activity_slots.append([PAD] * ACTIVITY_STRIDE)
    owned_slots = [
        _encode_owned(item, observation.description_ids) for item in observation.owned_deployments
    ]
    while len(owned_slots) < MAX_DECOYS:
        owned_slots.append([PAD] * OWNED_STRIDE)
    flat_activity = tuple(value for slot in activity_slots for value in slot)
    flat_owned = tuple(value for slot in owned_slots for value in slot)
    return EncodedObservation(
        activity=flat_activity,
        owned_deployments=flat_owned,
        action_mask=tuple(1 if bit else 0 for bit in observation.safe_action_mask),
        remaining_decoy_budget=observation.remaining_decoy_budget,
        remaining_team_attempts=observation.remaining_team_attempts,
        remaining_team_generated_tokens=observation.remaining_team_generated_tokens,
    )


def catalogue_for_observation(observation: DefenderObservation) -> DiscreteCatalogue:
    return build_catalogue(observation.description_ids)
