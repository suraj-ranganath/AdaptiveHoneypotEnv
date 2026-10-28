"""Event envelope and role projections, version 1.0.0.

Every record carries the DESIGN §10 envelope. Derived scoring events cite
source sequence numbers and use deterministic ids that do not depend on the
wall clock. Role projections are typed constructors. The defender projection
has no messageboard variant and drops messageboard tool activity.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from adaptivehoneypotenv.contracts.actions import DecoySpec
from adaptivehoneypotenv.contracts.limits import (
    ATTEMPTS_PER_DEFENDER_DECISION,
    MESSAGEBOARD_POST_MAX_CHARS,
    MESSAGEBOARD_READ_MAX_POSTS,
)
from adaptivehoneypotenv.contracts.telemetry import (
    DefenderVisibleToolName,
    HttpMethodCategory,
    HttpStatusCategory,
    PathCategory,
)
from adaptivehoneypotenv.contracts.tools import MESSAGEBOARD_TOOL_NAMES, AttackerToolName
from adaptivehoneypotenv.contracts.transition import (
    RewardComponents,
    TerminationReason,
    TruncationReason,
)
from adaptivehoneypotenv.contracts.versions import EVENT_SCHEMA_VERSION

DefenderVisibleKind = Literal[
    "episode_started",
    "model_call_started",
    "model_call_finished",
    "tool_started",
    "tool_completed",
    "actor_turn_rejected",
    "deployment_started",
    "deployment_committed",
    "deployment_rejected",
    "decoy_exposed",
    "decoy_inspected",
    "decoy_authenticated",
    "verified_engagement",
    "protected_value_exposed",
    "transition_completed",
    "episode_finished",
]

HISTORY_KINDS = frozenset(
    {
        "model_call_started",
        "model_call_finished",
        "tool_started",
        "tool_completed",
        "actor_turn_rejected",
    }
)


class EventStatus(str, Enum):
    ok = "ok"
    error = "error"
    rejected = "rejected"
    invalid = "invalid"
    refused = "refused"
    clipped = "clipped"


class TurnRejectionReason(str, Enum):
    zero_tool_calls = "zero_tool_calls"
    multiple_tool_calls = "multiple_tool_calls"
    malformed_arguments = "malformed_arguments"
    plain_text = "plain_text"
    provider_refusal = "provider_refusal"


class DeploymentRejectionReason(str, Enum):
    invalid_batch = "invalid_batch"
    budget = "budget"
    incompatible = "incompatible"
    occupied_slot = "occupied_slot"
    audit = "audit"


class FinishReasonName(str, Enum):
    stop = "stop"
    tool_calls = "tool_calls"
    length = "length"
    content_filter = "content_filter"


class PayloadRef(BaseModel):
    """Pointer to a private payload. The bytes are not on the envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ref_id: Annotated[str, Field(pattern=r"^payload_[0-9a-f]{16,64}$")]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    byte_length: Annotated[int, Field(ge=0, le=1_048_576)]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["operator", "controller", "defender", "attacker", "system"]
    actor_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]


def compute_event_id(episode_id: str, sequence: int, kind: str) -> str:
    raw = f"{EVENT_SCHEMA_VERSION}|{episode_id}|{sequence}|{kind}".encode()
    return hashlib.sha256(raw).hexdigest()


def compute_derived_id(episode_id: str, kind: str, source_sequences: tuple[int, ...]) -> str:
    cited = ",".join(str(item) for item in source_sequences)
    raw = f"{EVENT_SCHEMA_VERSION}|derived|{episode_id}|{kind}|{cited}".encode()
    return hashlib.sha256(raw).hexdigest()


def _check_derived(
    *,
    episode_id: str,
    sequence: int,
    kind: str,
    source_sequences: tuple[int, ...],
    deterministic_id: str,
) -> None:
    if not source_sequences:
        raise ValueError("derived events cite at least one source sequence")
    if len(set(source_sequences)) != len(source_sequences):
        raise ValueError("source sequences must be unique")
    if tuple(sorted(source_sequences)) != source_sequences:
        raise ValueError("source sequences must be strictly increasing")
    if any(source >= sequence for source in source_sequences):
        raise ValueError("source sequences must precede the derived event")
    expected = compute_derived_id(episode_id, kind, source_sequences)
    if deterministic_id != expected:
        raise ValueError("deterministic_id does not match the source citation")


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = EVENT_SCHEMA_VERSION
    event_id: str
    episode_id: Annotated[str, Field(pattern=r"^ep_[A-Za-z0-9_-]{8,64}$")]
    sequence: Annotated[int, Field(ge=0)]
    round_index: Annotated[int, Field(ge=0)]
    attempt_index: Annotated[int, Field(ge=0)]
    world_version: Annotated[int, Field(ge=0)]
    actor: Principal
    status: EventStatus
    monotonic_duration_ns: Annotated[int, Field(ge=0)]
    wall_time_unix_ns: Annotated[int, Field(ge=0)]
    request_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
    payload_refs: tuple[PayloadRef, ...] = ()

    @model_validator(mode="after")
    def deterministic_event_id(self) -> Envelope:
        kind = getattr(self, "kind", None)
        if not isinstance(kind, str):
            raise ValueError("event kind is required")
        expected = compute_event_id(self.episode_id, self.sequence, kind)
        if self.event_id != expected:
            raise ValueError("event_id is not the deterministic journal id")
        return self


class EpisodeStarted(Envelope):
    kind: Literal["episode_started"]
    scenario_id: Literal["secret_store_ops/v1"]
    catalogue_ordering_version: Literal["secret_store_ops/v1.ordering.1"]
    team: Literal["solo", "trio"]


class ModelCallStarted(Envelope):
    kind: Literal["model_call_started"]
    adapter_id: Literal["openai_compatible", "scripted_test_double"]
    model: Literal["z-ai/glm-5.3-flash"]


class ModelCallFinished(Envelope):
    kind: Literal["model_call_finished"]
    adapter_id: Literal["openai_compatible", "scripted_test_double"]
    model: Literal["z-ai/glm-5.3-flash"]
    finish_reason: FinishReasonName
    refusal: bool
    prompt_tokens: Annotated[int, Field(ge=0)]
    completion_tokens: Annotated[int, Field(ge=0)]
    reasoning_tokens: Annotated[int, Field(ge=0)] = 0
    reasoning_included_in_completion: bool = True


class ToolStarted(Envelope):
    kind: Literal["tool_started"]
    tool_name: AttackerToolName
    normalized_path: str | None = None
    path_category: PathCategory = PathCategory.none

    @model_validator(mode="after")
    def attacker_tool(self) -> ToolStarted:
        if self.actor.role != "attacker":
            raise ValueError("tool events belong to an attacker")
        return self


class ToolCompleted(Envelope):
    kind: Literal["tool_completed"]
    tool_name: AttackerToolName
    normalized_path: str | None = None
    path_category: PathCategory = PathCategory.none
    sanitized_search_term: Annotated[str, Field(max_length=256)] = ""
    search_clipped: bool = False
    returned_hit_count: Annotated[int, Field(ge=0, le=100)] = 0
    http_method: HttpMethodCategory = HttpMethodCategory.none
    http_status_category: HttpStatusCategory = HttpStatusCategory.none
    clipped: bool = False

    @model_validator(mode="after")
    def attacker_tool(self) -> ToolCompleted:
        if self.actor.role != "attacker":
            raise ValueError("tool events belong to an attacker")
        return self


class ActorTurnRejected(Envelope):
    kind: Literal["actor_turn_rejected"]
    reason_category: TurnRejectionReason

    @model_validator(mode="after")
    def attacker_turn(self) -> ActorTurnRejected:
        if self.actor.role != "attacker":
            raise ValueError("rejected turns belong to an attacker")
        return self


class MessageboardPosted(Envelope):
    kind: Literal["messageboard_posted"]
    post_id: Annotated[int, Field(ge=1)]
    author_actor_id: Annotated[str, Field(pattern=r"^attacker-[123]$")]
    char_count: Annotated[int, Field(ge=1, le=MESSAGEBOARD_POST_MAX_CHARS)]

    @model_validator(mode="after")
    def board_actor(self) -> MessageboardPosted:
        if self.actor.role != "attacker" or self.actor.actor_id != self.author_actor_id:
            raise ValueError("a post is attributed to the attacker who wrote it")
        return self


class MessageboardRead(Envelope):
    kind: Literal["messageboard_read"]
    after_post_id: Annotated[int, Field(ge=0)]
    returned_count: Annotated[int, Field(ge=0, le=MESSAGEBOARD_READ_MAX_POSTS)]
    clipped: bool

    @model_validator(mode="after")
    def board_actor(self) -> MessageboardRead:
        if self.actor.role != "attacker":
            raise ValueError("a board read belongs to an attacker")
        return self


class DeploymentStarted(Envelope):
    kind: Literal["deployment_started"]
    transaction_id: Annotated[str, Field(pattern=r"^txn_[A-Za-z0-9_-]{8,64}$")]
    specs: Annotated[tuple[DecoySpec, ...], Field(min_length=1, max_length=2)]


class DeploymentCommitted(Envelope):
    kind: Literal["deployment_committed"]
    transaction_id: Annotated[str, Field(pattern=r"^txn_[A-Za-z0-9_-]{8,64}$")]
    specs: Annotated[tuple[DecoySpec, ...], Field(min_length=1, max_length=2)]
    deployment_ids: Annotated[
        tuple[Annotated[str, Field(pattern=r"^dep_[a-z0-9]{8,32}$")], ...],
        Field(min_length=1, max_length=2),
    ]

    @model_validator(mode="after")
    def ids_match_specs(self) -> DeploymentCommitted:
        if len(self.deployment_ids) != len(self.specs):
            raise ValueError("each committed spec has one public deployment id")
        return self


class DeploymentRejected(Envelope):
    kind: Literal["deployment_rejected"]
    transaction_id: Annotated[str, Field(pattern=r"^txn_[A-Za-z0-9_-]{8,64}$")]
    reason_category: DeploymentRejectionReason
    specs: Annotated[tuple[DecoySpec, ...], Field(min_length=1, max_length=2)]


class _Scoring(Envelope):
    source_sequences: Annotated[tuple[int, ...], Field(min_length=1)]
    deterministic_id: str
    recipient_actor_id: Annotated[str, Field(pattern=r"^attacker-[123]$")]

    @model_validator(mode="after")
    def citation(self) -> _Scoring:
        kind = getattr(self, "kind", None)
        if not isinstance(kind, str):
            raise ValueError("scoring event kind is required")
        _check_derived(
            episode_id=self.episode_id,
            sequence=self.sequence,
            kind=kind,
            source_sequences=self.source_sequences,
            deterministic_id=self.deterministic_id,
        )
        return self


class DecoyExposed(_Scoring):
    kind: Literal["decoy_exposed"]
    decoy_public_id: Annotated[str, Field(pattern=r"^decoy_[a-z0-9]{8,32}$")]


class DecoyInspected(_Scoring):
    kind: Literal["decoy_inspected"]
    decoy_public_id: Annotated[str, Field(pattern=r"^decoy_[a-z0-9]{8,32}$")]


class DecoyAuthenticated(_Scoring):
    kind: Literal["decoy_authenticated"]
    decoy_public_id: Annotated[str, Field(pattern=r"^decoy_[a-z0-9]{8,32}$")]


class VerifiedEngagement(_Scoring):
    kind: Literal["verified_engagement"]
    decoy_public_id: Annotated[str, Field(pattern=r"^decoy_[a-z0-9]{8,32}$")]


class ProtectedValueExposed(_Scoring):
    kind: Literal["protected_value_exposed"]


class TransitionCompleted(Envelope):
    kind: Literal["transition_completed"]
    valid: bool
    invalid_reason: str | None = None
    terminated: bool
    truncated: bool
    termination_reason: TerminationReason | None = None
    truncation_reason: TruncationReason | None = None
    attempts_consumed: Annotated[int, Field(ge=0, le=ATTEMPTS_PER_DEFENDER_DECISION)]
    reward_components: RewardComponents

    @model_validator(mode="after")
    def flags(self) -> TransitionCompleted:
        if self.terminated and self.truncated:
            raise ValueError("a transition is terminated or truncated, not both")
        if self.valid and self.invalid_reason is not None:
            raise ValueError("a valid transition has no invalid reason")
        if not self.valid and not self.invalid_reason:
            raise ValueError("an invalid transition needs a reason")
        return self


class EpisodeFinished(Envelope):
    kind: Literal["episode_finished"]
    valid: bool
    invalid_reason: str | None = None
    terminated: bool
    truncated: bool
    termination_reason: TerminationReason | None = None
    truncation_reason: TruncationReason | None = None

    @model_validator(mode="after")
    def flags(self) -> EpisodeFinished:
        if self.terminated and self.truncated:
            raise ValueError("an episode is terminated or truncated, not both")
        if not self.terminated and not self.truncated:
            raise ValueError("episode_finished records an end")
        return self


Event = Annotated[
    Union[
        EpisodeStarted,
        ModelCallStarted,
        ModelCallFinished,
        ToolStarted,
        ToolCompleted,
        ActorTurnRejected,
        MessageboardPosted,
        MessageboardRead,
        DeploymentStarted,
        DeploymentCommitted,
        DeploymentRejected,
        DecoyExposed,
        DecoyInspected,
        DecoyAuthenticated,
        VerifiedEngagement,
        ProtectedValueExposed,
        TransitionCompleted,
        EpisodeFinished,
    ],
    Field(discriminator="kind"),
]
EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(payload: object) -> Event:
    return EventAdapter.validate_python(payload)


def validate_journal(events: Sequence[Event]) -> None:
    """Sequence starts at 0 and increases by one. Round and world version do not go backwards."""

    for index, event in enumerate(events):
        if event.sequence != index:
            raise ValueError(f"journal sequence {event.sequence} is not {index}")
        if index == 0:
            continue
        previous = events[index - 1]
        if event.round_index < previous.round_index:
            raise ValueError("round index decreased")
        if event.world_version < previous.world_version:
            raise ValueError("world version decreased")


class DefenderEventView(BaseModel):
    """Allowlisted defender view. Messageboard fields are not declared."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = EVENT_SCHEMA_VERSION
    kind: DefenderVisibleKind
    episode_id: str
    sequence: int
    round_index: int
    attempt_index: int
    world_version: int
    actor_id: str
    actor_role: Literal["operator", "controller", "defender", "attacker", "system"]
    status: EventStatus
    monotonic_duration_ns: int
    wall_time_unix_ns: int
    request_id: str
    tool_name: DefenderVisibleToolName | None = None
    normalized_path: str | None = None
    path_category: PathCategory | None = None
    sanitized_search_term: str | None = None
    returned_hit_count: int | None = None
    http_method: HttpMethodCategory | None = None
    http_status_category: HttpStatusCategory | None = None
    refusal: bool | None = None
    decoy_public_id: str | None = None
    source_sequences: tuple[int, ...] = ()
    deterministic_id: str | None = None
    valid: bool | None = None
    terminated: bool | None = None
    truncated: bool | None = None


class OperatorEventView(BaseModel):
    """Operator view of every kind. Board text and secret bytes stay behind payload refs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = EVENT_SCHEMA_VERSION
    kind: str
    episode_id: str
    sequence: int
    round_index: int
    attempt_index: int
    world_version: int
    actor_id: str
    actor_role: str
    status: EventStatus
    monotonic_duration_ns: int
    wall_time_unix_ns: int
    request_id: str
    payload_refs: tuple[PayloadRef, ...] = ()
    tool_name: AttackerToolName | None = None
    post_id: int | None = None
    char_count: int | None = None
    after_post_id: int | None = None
    returned_count: int | None = None
    clipped: bool | None = None
    reward_components: RewardComponents | None = None
    source_sequences: tuple[int, ...] = ()
    deterministic_id: str | None = None


class ActorHistoryView(BaseModel):
    """One actor's own tool or model event. Board posts are not pushed here."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = EVENT_SCHEMA_VERSION
    kind: Literal[
        "model_call_started",
        "model_call_finished",
        "tool_started",
        "tool_completed",
        "actor_turn_rejected",
    ]
    episode_id: str
    sequence: int
    round_index: int
    actor_id: str
    status: EventStatus
    tool_name: AttackerToolName | None = None
    payload_refs: tuple[PayloadRef, ...] = ()


def _as_defender_tool(name: AttackerToolName) -> DefenderVisibleToolName | None:
    try:
        return DefenderVisibleToolName(name.value)
    except ValueError:
        return None


def _defender_view(
    event: Envelope, kind: DefenderVisibleKind, **extra: object
) -> DefenderEventView:
    """Build the allowlisted view field by field. Unknown keys fail closed."""

    data: dict[str, object] = {
        "kind": kind,
        "episode_id": event.episode_id,
        "sequence": event.sequence,
        "round_index": event.round_index,
        "attempt_index": event.attempt_index,
        "world_version": event.world_version,
        "actor_id": event.actor.actor_id,
        "actor_role": event.actor.role,
        "status": event.status,
        "monotonic_duration_ns": event.monotonic_duration_ns,
        "wall_time_unix_ns": event.wall_time_unix_ns,
        "request_id": event.request_id,
    }
    data.update(extra)
    return DefenderEventView.model_validate(data)


def project_defender(event: Event) -> DefenderEventView | None:
    """Typed defender projection. Messageboard events and tools return None."""

    if isinstance(event, (MessageboardPosted, MessageboardRead)):
        return None
    if isinstance(event, (ToolStarted, ToolCompleted)) and (
        event.tool_name in MESSAGEBOARD_TOOL_NAMES
    ):
        return None
    if isinstance(event, EpisodeStarted):
        return _defender_view(event, "episode_started")
    if isinstance(event, ModelCallStarted):
        return _defender_view(event, "model_call_started")
    if isinstance(event, ModelCallFinished):
        return _defender_view(event, "model_call_finished", refusal=event.refusal)
    if isinstance(event, ToolStarted):
        tool_name = _as_defender_tool(event.tool_name)
        if tool_name is None:
            return None
        return _defender_view(
            event,
            "tool_started",
            tool_name=tool_name,
            normalized_path=event.normalized_path,
            path_category=event.path_category,
        )
    if isinstance(event, ToolCompleted):
        tool_name = _as_defender_tool(event.tool_name)
        if tool_name is None:
            return None
        return _defender_view(
            event,
            "tool_completed",
            tool_name=tool_name,
            normalized_path=event.normalized_path,
            path_category=event.path_category,
            sanitized_search_term=event.sanitized_search_term,
            returned_hit_count=event.returned_hit_count,
            http_method=event.http_method,
            http_status_category=event.http_status_category,
        )
    if isinstance(event, ActorTurnRejected):
        return _defender_view(event, "actor_turn_rejected")
    if isinstance(event, (DeploymentStarted, DeploymentCommitted, DeploymentRejected)):
        return _defender_view(event, event.kind)
    if isinstance(event, (DecoyExposed, DecoyInspected, DecoyAuthenticated, VerifiedEngagement)):
        return _defender_view(
            event,
            event.kind,
            decoy_public_id=event.decoy_public_id,
            source_sequences=event.source_sequences,
            deterministic_id=event.deterministic_id,
        )
    if isinstance(event, ProtectedValueExposed):
        return _defender_view(
            event,
            "protected_value_exposed",
            source_sequences=event.source_sequences,
            deterministic_id=event.deterministic_id,
        )
    if isinstance(event, TransitionCompleted):
        return _defender_view(
            event,
            "transition_completed",
            valid=event.valid,
            terminated=event.terminated,
            truncated=event.truncated,
        )
    if isinstance(event, EpisodeFinished):
        return _defender_view(
            event,
            "episode_finished",
            valid=event.valid,
            terminated=event.terminated,
            truncated=event.truncated,
        )
    return None


def project_operator(event: Event) -> OperatorEventView:
    """Typed operator projection. Payload refs are copied; inline secrets are not a field."""

    view = OperatorEventView(
        kind=event.kind,
        episode_id=event.episode_id,
        sequence=event.sequence,
        round_index=event.round_index,
        attempt_index=event.attempt_index,
        world_version=event.world_version,
        actor_id=event.actor.actor_id,
        actor_role=event.actor.role,
        status=event.status,
        monotonic_duration_ns=event.monotonic_duration_ns,
        wall_time_unix_ns=event.wall_time_unix_ns,
        request_id=event.request_id,
        payload_refs=event.payload_refs,
    )
    if isinstance(event, (ToolStarted, ToolCompleted)):
        clipped = event.clipped if isinstance(event, ToolCompleted) else None
        return view.model_copy(update={"tool_name": event.tool_name, "clipped": clipped})
    if isinstance(event, MessageboardPosted):
        return view.model_copy(update={"post_id": event.post_id, "char_count": event.char_count})
    if isinstance(event, MessageboardRead):
        return view.model_copy(
            update={
                "after_post_id": event.after_post_id,
                "returned_count": event.returned_count,
                "clipped": event.clipped,
            }
        )
    if isinstance(event, _Scoring):
        return view.model_copy(
            update={
                "source_sequences": event.source_sequences,
                "deterministic_id": event.deterministic_id,
            }
        )
    if isinstance(event, TransitionCompleted):
        return view.model_copy(update={"reward_components": event.reward_components})
    return view


def project_actor_history(event: Event, *, actor_id: str) -> ActorHistoryView | None:
    """History projection. Messageboard events are never pushed, including to their author."""

    if isinstance(event, (MessageboardPosted, MessageboardRead)):
        return None
    if event.actor.role != "attacker" or event.actor.actor_id != actor_id:
        return None
    if event.kind not in HISTORY_KINDS:
        return None
    tool_name = event.tool_name if isinstance(event, (ToolStarted, ToolCompleted)) else None
    return ActorHistoryView(
        kind=event.kind,  # type: ignore[arg-type]
        episode_id=event.episode_id,
        sequence=event.sequence,
        round_index=event.round_index,
        actor_id=event.actor.actor_id,
        status=event.status,
        tool_name=tool_name,
        payload_refs=event.payload_refs,
    )
