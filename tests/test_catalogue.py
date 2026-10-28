"""Discrete catalogue indices, pairs, and the dynamic mask."""

from adaptivehoneypotenv.contracts.actions import PLACEHOLDER_DESCRIPTION_IDS, SlotId
from adaptivehoneypotenv.contracts.catalogue import (
    CATALOGUE_ORDERING_VERSION,
    action_mask,
    build_catalogue,
    pair_plan_id,
    sort_key,
)


def test_catalogue_indices_stable_and_pairs_available() -> None:
    ids = PLACEHOLDER_DESCRIPTION_IDS
    assert all(item.startswith("placeholder.secret_store_ops_v1.") for item in ids)

    first = build_catalogue(ids)
    second = build_catalogue(list(ids))
    assert first.ordering_version == CATALOGUE_ORDERING_VERSION
    assert first.plan_ids() == second.plan_ids()
    assert [plan.index for plan in first.plans] == list(range(len(first.plans)))
    assert first.plans[0].plan_id == "wait"
    assert first.plans[0].specs == ()

    singles = [plan for plan in first.plans if plan.kind == "single"]
    pairs = [plan for plan in first.plans if plan.kind == "pair"]
    expected_pair_ids: list[str] = []
    for left_index, left in enumerate(singles):
        for right in singles[left_index + 1 :]:
            if left.specs[0].slot_id == right.specs[0].slot_id:
                continue
            expected_pair_ids.append(pair_plan_id(left.specs[0], right.specs[0]))
    assert [plan.plan_id for plan in pairs] == expected_pair_ids
    assert expected_pair_ids

    reverse = pair_plan_id(pairs[0].specs[1], pairs[0].specs[0])
    assert reverse not in set(first.plan_ids())

    keys = []
    index_by_id = {description_id: index for index, description_id in enumerate(ids)}
    for plan in singles:
        spec = plan.specs[0]
        keys.append(
            sort_key(
                spec.template_id,
                spec.slot_id,
                spec.context_id,
                index_by_id[spec.description_id],
            )
        )
    assert keys == sorted(keys)

    flipped = build_catalogue(tuple(reversed(ids)))
    assert flipped.plans[0].plan_id == "wait"
    assert flipped.plan_ids() != first.plan_ids()

    before = first.plan_ids()
    open_mask = action_mask(first, occupied_slots=(), decoys_committed=0)
    busy_mask = action_mask(first, occupied_slots=(SlotId.ci_records,), decoys_committed=1)
    assert first.plan_ids() == before
    assert len(open_mask) == len(busy_mask) == len(before)
    assert open_mask[0] is True
    assert busy_mask[0] is True
    assert open_mask != busy_mask
    for plan, bit in zip(first.plans, busy_mask, strict=True):
        uses_ci = any(spec.slot_id is SlotId.ci_records for spec in plan.specs)
        if plan.kind == "pair" or uses_ci:
            assert bit is False
        elif plan.kind == "single":
            assert bit is True

    full = action_mask(
        first,
        occupied_slots=(SlotId.ci_records, SlotId.runbooks),
        decoys_committed=2,
    )
    assert full[0] is True
    assert any(full) and not any(full[1:])

    only_wait = build_catalogue(())
    assert only_wait.plan_ids() == ("wait",)
