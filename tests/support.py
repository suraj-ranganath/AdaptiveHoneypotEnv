"""Shared builders for contract tests."""

from adaptivehoneypotenv.contracts.actions import (
    CONTEXT_ORDER,
    PLACEHOLDER_DESCRIPTION_IDS,
    BudgetState,
    ContextId,
    SlotId,
    TemplateId,
)
from adaptivehoneypotenv.contracts.catalogue import action_mask, build_catalogue
from adaptivehoneypotenv.contracts.events import (
    EventStatus,
    Principal,
    compute_event_id,
)
from adaptivehoneypotenv.contracts.observations import (
    DefenderObservation,
    frozen_compatibility,
)
from adaptivehoneypotenv.contracts.telemetry import PathCategory

EPISODE_ID = "ep_phase0demo01"


def sample_observation(
    *,
    description_ids: tuple[str, ...] = PLACEHOLDER_DESCRIPTION_IDS,
    occupied: tuple[SlotId, ...] = (),
    activity: tuple[object, ...] = (),
    owned: tuple[object, ...] = (),
) -> DefenderObservation:
    catalogue = build_catalogue(description_ids)
    committed = len(occupied)
    mask = action_mask(catalogue, occupied_slots=occupied, decoys_committed=committed)
    return DefenderObservation(
        description_ids=description_ids,
        compatibility=frozen_compatibility(),
        contexts=CONTEXT_ORDER,
        remaining_decoy_budget=2 - committed,
        safe_action_mask=mask,
        catalogue_size=len(catalogue.plans),
        remaining_team_attempts=90,
        remaining_team_generated_tokens=24_000,
        activity=activity,  # type: ignore[arg-type]
        owned_deployments=owned,  # type: ignore[arg-type]
    )


def envelope(
    kind: str,
    sequence: int,
    *,
    actor: Principal | None = None,
    round_index: int = 0,
    attempt_index: int = 0,
    world_version: int = 0,
    wall_time_unix_ns: int = 1_700_000_000_000_000_000,
) -> dict[str, object]:
    return {
        "event_id": compute_event_id(EPISODE_ID, sequence, kind),
        "episode_id": EPISODE_ID,
        "sequence": sequence,
        "round_index": round_index,
        "attempt_index": attempt_index,
        "world_version": world_version,
        "actor": actor or Principal(role="attacker", actor_id="attacker-1"),
        "status": EventStatus.ok,
        "monotonic_duration_ns": 5,
        "wall_time_unix_ns": wall_time_unix_ns,
        "request_id": f"req-{sequence}",
    }


def catalogue_spec(
    template: TemplateId = TemplateId.integration_config,
    slot: SlotId = SlotId.deployment_notes,
    context: ContextId = ContextId.release,
    description_id: str = PLACEHOLDER_DESCRIPTION_IDS[0],
) -> dict[str, str]:
    return {
        "track": "catalogue",
        "template_id": template.value,
        "slot_id": slot.value,
        "context_id": context.value,
        "description_id": description_id,
    }


def empty_budget() -> BudgetState:
    return BudgetState()


def service_activity_path_category() -> PathCategory:
    return PathCategory.service
