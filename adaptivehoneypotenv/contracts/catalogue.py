"""Immutable discrete catalogue for the catalogue track.

Indices are a function of the scenario description list and
``CATALOGUE_ORDERING_VERSION``. Occupancy and the remaining decoy budget
change the mask only. ``wait`` is always available. Contextual free text is
not part of this enumeration.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptivehoneypotenv.contracts.actions import (
    COMPATIBILITY,
    CONTEXT_ORDER,
    SLOT_ORDER,
    TEMPLATE_ORDER,
    CatalogueDecoySpec,
    ContextId,
    SlotId,
    TemplateId,
    validate_description_id,
)
from adaptivehoneypotenv.contracts.limits import MAX_DECOYS, MAX_DESCRIPTION_VARIANTS
from adaptivehoneypotenv.contracts.versions import CATALOGUE_ORDERING_VERSION


class CataloguePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: Annotated[int, Field(ge=0)]
    plan_id: str
    kind: Literal["wait", "single", "pair"]
    specs: tuple[CatalogueDecoySpec, ...]

    @model_validator(mode="after")
    def shape(self) -> CataloguePlan:
        expected = {"wait": 0, "single": 1, "pair": 2}[self.kind]
        if len(self.specs) != expected:
            raise ValueError("plan spec count does not match its kind")
        if self.kind == "pair" and self.specs[0].slot_id == self.specs[1].slot_id:
            raise ValueError("a pair must use two slots")
        return self


class DiscreteCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordering_version: Literal["secret_store_ops/v1.ordering.1"] = CATALOGUE_ORDERING_VERSION
    description_ids: tuple[str, ...]
    plans: tuple[CataloguePlan, ...]

    @model_validator(mode="after")
    def stable_indices(self) -> DiscreteCatalogue:
        if not self.plans or self.plans[0].kind != "wait" or self.plans[0].index != 0:
            raise ValueError("index 0 is wait")
        ids: list[str] = []
        for index, plan in enumerate(self.plans):
            if plan.index != index:
                raise ValueError("plan indices must equal their position")
            ids.append(plan.plan_id)
        if len(ids) != len(set(ids)):
            raise ValueError("plan ids must be unique")
        return self

    def plan_ids(self) -> tuple[str, ...]:
        return tuple(plan.plan_id for plan in self.plans)


def single_plan_id(spec: CatalogueDecoySpec) -> str:
    return (
        f"single/{spec.template_id.value}/{spec.slot_id.value}/"
        f"{spec.context_id.value}/{spec.description_id}"
    )


def pair_plan_id(first: CatalogueDecoySpec, second: CatalogueDecoySpec) -> str:
    left = single_plan_id(first).removeprefix("single/")
    right = single_plan_id(second).removeprefix("single/")
    return f"pair/{left}+{right}"


def build_catalogue(description_ids: tuple[str, ...] | list[str]) -> DiscreteCatalogue:
    """Build the catalogue for one frozen description list.

    Description order is the list order. The same list always yields the
    same ids and indices. Reordering the list is a different scenario
    catalogue version and may change indices.
    """

    ids = tuple(description_ids)
    if len(ids) > MAX_DESCRIPTION_VARIANTS:
        raise ValueError(f"at most {MAX_DESCRIPTION_VARIANTS} description variants")
    if len(ids) != len(set(ids)):
        raise ValueError("description ids must be unique")
    for description_id in ids:
        validate_description_id(description_id)

    singles: list[CatalogueDecoySpec] = []
    for template_id in TEMPLATE_ORDER:
        for slot_id in SLOT_ORDER:
            if slot_id not in COMPATIBILITY[template_id]:
                continue
            for context_id in CONTEXT_ORDER:
                for description_id in ids:
                    singles.append(
                        CatalogueDecoySpec(
                            track="catalogue",
                            template_id=template_id,
                            slot_id=slot_id,
                            context_id=context_id,
                            description_id=description_id,
                        )
                    )

    plans: list[CataloguePlan] = [
        CataloguePlan(index=0, plan_id="wait", kind="wait", specs=()),
    ]
    for spec in singles:
        plans.append(
            CataloguePlan(
                index=len(plans),
                plan_id=single_plan_id(spec),
                kind="single",
                specs=(spec,),
            )
        )
    for left_index, left in enumerate(singles):
        for right in singles[left_index + 1 :]:
            if left.slot_id == right.slot_id:
                continue
            plans.append(
                CataloguePlan(
                    index=len(plans),
                    plan_id=pair_plan_id(left, right),
                    kind="pair",
                    specs=(left, right),
                )
            )
    return DiscreteCatalogue(description_ids=ids, plans=tuple(plans))


def action_mask(
    catalogue: DiscreteCatalogue,
    *,
    occupied_slots: tuple[SlotId, ...],
    decoys_committed: int,
) -> tuple[bool, ...]:
    """Dynamic mask. The catalogue index mapping is not an argument and cannot change."""

    if decoys_committed < 0 or decoys_committed > MAX_DECOYS:
        raise ValueError("decoys_committed is outside the global budget")
    if len(set(occupied_slots)) != len(occupied_slots):
        raise ValueError("occupied slots must be unique")
    unknown = [slot for slot in occupied_slots if slot not in SLOT_ORDER]
    if unknown:
        raise ValueError("unknown slot in occupancy")
    occupied = set(occupied_slots)
    flags: list[bool] = []
    for plan in catalogue.plans:
        if plan.kind == "wait":
            flags.append(True)
            continue
        slots = [spec.slot_id for spec in plan.specs]
        if any(slot in occupied for slot in slots):
            flags.append(False)
            continue
        if decoys_committed + len(slots) > MAX_DECOYS:
            flags.append(False)
            continue
        flags.append(True)
    return tuple(flags)


def sort_key(
    template_id: TemplateId,
    slot_id: SlotId,
    context_id: ContextId,
    description_index: int,
) -> tuple[int, int, int, int]:
    return (
        TEMPLATE_ORDER.index(template_id),
        SLOT_ORDER.index(slot_id),
        CONTEXT_ORDER.index(context_id),
        description_index,
    )


__all__ = [
    "CATALOGUE_ORDERING_VERSION",
    "CataloguePlan",
    "DiscreteCatalogue",
    "action_mask",
    "build_catalogue",
    "pair_plan_id",
    "single_plan_id",
    "sort_key",
]
