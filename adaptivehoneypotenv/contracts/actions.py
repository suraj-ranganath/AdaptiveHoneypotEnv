"""Defender action schema, version 1.0.0.

``deploy`` and ``wait`` are the only actions. A deploy carries one or two
decoy specs. Catalogue items carry ``description_id`` and no free text.
Contextual items carry ``description`` (at most 240 Unicode characters) and
no ``description_id``. Unknown fields are invalid. A batch that fails any
check is rejected as a whole.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Final, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from adaptivehoneypotenv.contracts.limits import (
    DESCRIPTION_MAX_UNICODE_CHARS,
    MAX_DECOYS,
    MAX_DESCRIPTION_VARIANTS,
)
from adaptivehoneypotenv.contracts.versions import (
    ACTION_SCHEMA_VERSION,
    DESCRIPTION_AUDIT_VERSION,
)

_DESCRIPTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,48}(?:\.[a-z][a-z0-9_]{0,48}){1,6}$")
_URL_RE = re.compile(r"(?i)\b(?:https?://|ssh://|file://|www\.)|\b[a-z][a-z0-9+.-]*://")
_SECRET_RE = re.compile(
    r"(?i)(sk-or-|sk-[a-z0-9]{4,}|bearer\s+[a-z0-9]|api[_-]?key\s*[:=]|password\s*[:=]|"
    r"secret\s*[:=]|token\s*[:=])"
)
_DECOY_LABEL_RE = re.compile(r"(?i)\b(honeypots?|decoys?|canaries|canary|honeytokens?)\b")
_INJECTION_RE = re.compile(
    r"(?i)(ignore (all |any )?(previous|prior) instructions|you are now|system prompt|"
    r"<\s*/?\s*system\s*>)"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class TemplateId(str, Enum):
    integration_config = "integration_config"
    ci_credential_record = "ci_credential_record"
    runbook_reference = "runbook_reference"


class SlotId(str, Enum):
    deployment_notes = "deployment_notes"
    integration_records = "integration_records"
    ci_records = "ci_records"
    runbooks = "runbooks"


class ContextId(str, Enum):
    release = "release"
    backup = "backup"


TEMPLATE_ORDER: Final[tuple[TemplateId, ...]] = (
    TemplateId.integration_config,
    TemplateId.ci_credential_record,
    TemplateId.runbook_reference,
)
SLOT_ORDER: Final[tuple[SlotId, ...]] = (
    SlotId.deployment_notes,
    SlotId.integration_records,
    SlotId.ci_records,
    SlotId.runbooks,
)
CONTEXT_ORDER: Final[tuple[ContextId, ...]] = (ContextId.release, ContextId.backup)

# DESIGN §3.1. Order inside each value is the table order, not the sort key.
COMPATIBILITY: Final[dict[TemplateId, tuple[SlotId, ...]]] = {
    TemplateId.integration_config: (SlotId.deployment_notes, SlotId.integration_records),
    TemplateId.ci_credential_record: (SlotId.ci_records, SlotId.deployment_notes),
    TemplateId.runbook_reference: (SlotId.runbooks, SlotId.deployment_notes),
}

SLOT_DIRECTORIES: Final[dict[SlotId, str]] = {
    SlotId.deployment_notes: "ops/deploy",
    SlotId.integration_records: "ops/integrations",
    SlotId.ci_records: "ops/ci",
    SlotId.runbooks: "ops/runbooks",
}

# Maximum files the compiler may render for that template. The episode cap
# remains FILES_PER_DECOY.
TEMPLATE_FILE_COUNTS: Final[dict[TemplateId, int]] = {
    TemplateId.integration_config: 1,
    TemplateId.ci_credential_record: 1,
    TemplateId.runbook_reference: 2,
}

# Phase 0 has no approved description text. WS2 owns that catalogue.
# These ids exist so the discrete catalogue can be built and tested.
PLACEHOLDER_DESCRIPTION_IDS: Final[tuple[str, ...]] = (
    "placeholder.secret_store_ops_v1.alpha",
    "placeholder.secret_store_ops_v1.beta",
)
PLACEHOLDER_DESCRIPTION_PREFIX: Final = "placeholder.secret_store_ops_v1."


def validate_description_id(description_id: str) -> str:
    """Accept a dotted lowercase id.

    The Phase 0 placeholders use ``placeholder.secret_store_ops_v1.*``.
    Approved non-placeholder ids that match this grammar can be passed to
    the catalogue builder; the text those ids name is not part of this schema.
    """

    if not _DESCRIPTION_ID_RE.fullmatch(description_id):
        raise ValueError(
            f"description_id must be a dotted lowercase id (audit {DESCRIPTION_AUDIT_VERSION})"
        )
    return description_id


def audit_description(text: str) -> tuple[str, ...]:
    """Versioned syntax audit. This does not prove semantic inertness."""

    violations: list[str] = []
    if _CONTROL_RE.search(text):
        violations.append("control_characters")
    if "{" in text or "}" in text:
        violations.append("embedded_control_fields")
    if _URL_RE.search(text):
        violations.append("embedded_url")
    if _SECRET_RE.search(text):
        violations.append("embedded_credential")
    if _DECOY_LABEL_RE.search(text):
        violations.append("decoy_label")
    if _INJECTION_RE.search(text):
        violations.append("injection_wording")
    return tuple(violations)


def slot_compatible(template_id: TemplateId, slot_id: SlotId) -> bool:
    return slot_id in COMPATIBILITY[template_id]


class _SpecBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = ACTION_SCHEMA_VERSION
    template_id: TemplateId
    slot_id: SlotId
    context_id: ContextId

    @model_validator(mode="after")
    def template_allows_slot(self) -> _SpecBase:
        if not slot_compatible(self.template_id, self.slot_id):
            raise ValueError(
                f"{self.template_id.value} cannot use slot {self.slot_id.value}; "
                "the whole batch is invalid"
            )
        return self


class CatalogueDecoySpec(_SpecBase):
    """Catalogue track: an approved description id and no free text."""

    track: Literal["catalogue"]
    description_id: str

    @model_validator(mode="after")
    def description_id_ok(self) -> CatalogueDecoySpec:
        validate_description_id(self.description_id)
        return self


class ContextualDecoySpec(_SpecBase):
    """Contextual track: bounded description text and no description id."""

    track: Literal["contextual"]
    description: Annotated[str, Field(min_length=1, max_length=DESCRIPTION_MAX_UNICODE_CHARS)]

    @model_validator(mode="after")
    def description_ok(self) -> ContextualDecoySpec:
        violations = audit_description(self.description)
        if violations:
            raise ValueError(
                f"description failed {DESCRIPTION_AUDIT_VERSION}: {', '.join(violations)}"
            )
        return self


DecoySpec = Annotated[
    Union[CatalogueDecoySpec, ContextualDecoySpec],
    Field(discriminator="track"),
]


class WaitAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = ACTION_SCHEMA_VERSION
    kind: Literal["wait"]


class DeployAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = ACTION_SCHEMA_VERSION
    kind: Literal["deploy"]
    decoys: Annotated[tuple[DecoySpec, ...], Field(min_length=1, max_length=MAX_DECOYS)]

    @model_validator(mode="after")
    def whole_batch(self) -> DeployAction:
        slots = [spec.slot_id for spec in self.decoys]
        if len(slots) != len(set(slots)):
            raise ValueError("deploy batch slots must be distinct; the whole batch is invalid")
        tracks = {spec.track for spec in self.decoys}
        if len(tracks) != 1:
            raise ValueError("a deploy batch must use one track; the whole batch is invalid")
        return self


Action = Annotated[Union[DeployAction, WaitAction], Field(discriminator="kind")]
ActionAdapter: TypeAdapter[Action] = TypeAdapter(Action)


def parse_action(payload: object) -> Action:
    return ActionAdapter.validate_python(payload)


class BudgetState(BaseModel):
    """Global episode decoy budget. There is no per-actor creation budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    occupied_slots: tuple[SlotId, ...] = ()
    decoys_committed: Annotated[int, Field(ge=0, le=MAX_DECOYS)] = 0

    @model_validator(mode="after")
    def occupancy_matches_budget(self) -> BudgetState:
        if len(set(self.occupied_slots)) != len(self.occupied_slots):
            raise ValueError("occupied slots must be unique")
        if len(self.occupied_slots) != self.decoys_committed:
            raise ValueError("occupied slots must equal the global decoy count")
        return self


class BatchDecision(BaseModel):
    """A batch is accepted entirely or not at all."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    accepted: bool
    specs: tuple[DecoySpec, ...] = ()
    reason: str | None = None

    @model_validator(mode="after")
    def no_partial_specs(self) -> BatchDecision:
        if self.accepted and self.reason is not None:
            raise ValueError("an accepted batch has no rejection reason")
        if not self.accepted and self.specs:
            raise ValueError("a rejected batch must not retain specs")
        if not self.accepted and not self.reason:
            raise ValueError("a rejected batch needs a reason")
        return self


def _description_ids_of(
    catalogue_description_ids: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if catalogue_description_ids is None:
        return None
    if len(catalogue_description_ids) > MAX_DESCRIPTION_VARIANTS:
        raise ValueError(f"at most {MAX_DESCRIPTION_VARIANTS} description variants")
    return catalogue_description_ids


def validate_deploy_batch(
    action: Action,
    state: BudgetState,
    *,
    catalogue_description_ids: tuple[str, ...] | None = None,
    track: Literal["catalogue", "contextual"] | None = None,
) -> BatchDecision:
    """Validate a batch against free slots and the global two-decoy budget.

    ``Wait`` is accepted and commits nothing. A deploy that fails any item
    returns an empty spec tuple. This function does not mutate ``state``.
    """

    if isinstance(action, WaitAction):
        return BatchDecision(accepted=True, specs=(), reason=None)

    specs = action.decoys
    reasons: list[str] = []
    if track is not None and any(spec.track != track for spec in specs):
        reasons.append("batch track does not match the run track")
    allowed_ids = _description_ids_of(catalogue_description_ids)
    seen: list[SlotId] = []
    for spec in specs:
        if spec.slot_id in state.occupied_slots:
            reasons.append(f"slot {spec.slot_id.value} is occupied")
        if spec.slot_id in seen:
            reasons.append(f"slot {spec.slot_id.value} is repeated")
        seen.append(spec.slot_id)
        if isinstance(spec, CatalogueDecoySpec) and allowed_ids is not None:
            if spec.description_id not in allowed_ids:
                reasons.append(f"unknown description_id {spec.description_id}")
    if state.decoys_committed + len(specs) > MAX_DECOYS:
        reasons.append("global decoy budget exceeded")
    if reasons:
        return BatchDecision(accepted=False, specs=(), reason="; ".join(reasons))
    return BatchDecision(accepted=True, specs=specs, reason=None)


def commit_batch(state: BudgetState, decision: BatchDecision) -> BudgetState:
    """Return the next budget state. A rejection returns ``state`` unchanged."""

    if not decision.accepted:
        return state
    if not decision.specs:
        return state
    return BudgetState(
        occupied_slots=state.occupied_slots + tuple(spec.slot_id for spec in decision.specs),
        decoys_committed=state.decoys_committed + len(decision.specs),
    )


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "Action",
    "ActionAdapter",
    "BatchDecision",
    "BudgetState",
    "COMPATIBILITY",
    "CONTEXT_ORDER",
    "CatalogueDecoySpec",
    "ContextId",
    "ContextualDecoySpec",
    "DecoySpec",
    "DeployAction",
    "PLACEHOLDER_DESCRIPTION_IDS",
    "PLACEHOLDER_DESCRIPTION_PREFIX",
    "SLOT_DIRECTORIES",
    "SLOT_ORDER",
    "TEMPLATE_FILE_COUNTS",
    "TEMPLATE_ORDER",
    "TemplateId",
    "SlotId",
    "WaitAction",
    "audit_description",
    "commit_batch",
    "parse_action",
    "slot_compatible",
    "validate_deploy_batch",
    "validate_description_id",
]
