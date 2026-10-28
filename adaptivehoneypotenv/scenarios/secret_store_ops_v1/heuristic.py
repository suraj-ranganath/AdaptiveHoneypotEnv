"""Reference interpreter for the versioned heuristic asset.

Gate D's heuristic and oracle-goal arms should call this instead of inventing
another keyword table. ``forced_context`` is the oracle-goal workflow label.
The interpreter does not see credentials, stored values, or the messageboard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from adaptivehoneypotenv.contracts.actions import (
    CatalogueDecoySpec,
    ContextId,
    SlotId,
    TemplateId,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.catalogue import (
    DescriptionItem,
    catalogue_index,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    COMPATIBILITY,
    CONTEXTS,
    PACKAGE_DIR,
    SLOT_DIRS,
    expect_mapping,
    expect_string_list,
)

HEURISTIC_PATH = PACKAGE_DIR / "heuristic_policy.json"


@dataclass(frozen=True)
class ActivityObservation:
    """Sanitized search text and read path. Not a defender-observation schema."""

    seq: int
    search_text: str = ""
    path: str = ""


class FallbackRow(TypedDict):
    slot_id: str
    template_id: str
    description_id: str


@dataclass(frozen=True)
class HeuristicChoice:
    context_id: str
    slot_id: str
    template_id: str
    description_id: str
    description: str

    def to_catalogue_spec(self) -> CatalogueDecoySpec:
        """The same plan as a Phase 0 catalogue-track decoy spec."""

        return CatalogueDecoySpec(
            track="catalogue",
            template_id=TemplateId(self.template_id),
            slot_id=SlotId(self.slot_id),
            context_id=ContextId(self.context_id),
            description_id=self.description_id,
        )


@dataclass(frozen=True)
class HeuristicPolicy:
    asset_version: str
    keywords: dict[str, tuple[str, ...]]
    path_slots: tuple[tuple[str, str], ...]
    fallback: dict[str, tuple[FallbackRow, ...]]


def load_heuristic_policy(path: Path | None = None) -> HeuristicPolicy:
    raw: object = json.loads((path or HEURISTIC_PATH).read_text(encoding="utf-8"))
    payload = expect_mapping(raw, "heuristic policy")
    keywords_raw = expect_mapping(payload.get("keywords"), "heuristic keywords")
    keywords = {
        context: expect_string_list(terms, f"heuristic keywords for {context}")
        for context, terms in keywords_raw.items()
    }
    if set(keywords) != set(CONTEXTS):
        raise ValueError("heuristic keywords must cover release and backup only")
    release_terms = {term.casefold() for term in keywords["release"]}
    backup_terms = {term.casefold() for term in keywords["backup"]}
    if release_terms & backup_terms:
        raise ValueError("heuristic keyword sets overlap")
    activity_raw = payload.get("activity_path_slots")
    if not isinstance(activity_raw, list):
        raise ValueError("heuristic activity_path_slots must be a list")
    path_slots_list: list[tuple[str, str]] = []
    for row in activity_raw:
        document = expect_mapping(row, "activity path slot")
        prefix = document.get("prefix")
        slot_id = document.get("slot_id")
        if not isinstance(prefix, str) or not isinstance(slot_id, str):
            raise ValueError("activity path slot requires prefix and slot_id")
        path_slots_list.append((prefix, slot_id))
    path_slots = tuple(path_slots_list)
    for _, slot_id in path_slots:
        if slot_id not in SLOT_DIRS:
            raise ValueError(f"unknown activity slot {slot_id}")
    catalogue = catalogue_index()
    fallback_raw = expect_mapping(payload.get("fallback"), "heuristic fallback")
    fallback: dict[str, tuple[FallbackRow, ...]] = {}
    for context in CONTEXTS:
        rows: list[FallbackRow] = []
        seen_slots: set[str] = set()
        context_rows = fallback_raw.get(context)
        if not isinstance(context_rows, list):
            raise ValueError(f"heuristic fallback for {context} must be a list")
        for row in context_rows:
            document = expect_mapping(row, f"heuristic fallback {context}")
            slot_id = document.get("slot_id")
            template_id = document.get("template_id")
            description_id = document.get("description_id")
            if (
                not isinstance(slot_id, str)
                or not isinstance(template_id, str)
                or not isinstance(description_id, str)
            ):
                raise ValueError(f"heuristic fallback row for {context} is incomplete")
            if slot_id in seen_slots:
                raise ValueError(f"duplicate fallback slot {slot_id} for {context}")
            seen_slots.add(slot_id)
            allowed = COMPATIBILITY.get(template_id)
            if allowed is None or slot_id not in allowed:
                raise ValueError(f"{template_id} is not compatible with {slot_id}")
            if description_id not in catalogue:
                raise ValueError(f"unknown description_id {description_id}")
            rows.append(
                {
                    "slot_id": slot_id,
                    "template_id": template_id,
                    "description_id": description_id,
                }
            )
        if seen_slots != set(SLOT_DIRS):
            raise ValueError(f"fallback for {context} does not cover every slot")
        fallback[context] = tuple(rows)
    return HeuristicPolicy(
        asset_version=_require_str(payload, "asset_version"),
        keywords=keywords,
        path_slots=path_slots,
        fallback=fallback,
    )


def select_heuristic_plan(
    observations: list[ActivityObservation],
    occupied_slots: set[str] | frozenset[str],
    *,
    forced_context: str | None = None,
    policy: HeuristicPolicy | None = None,
    catalogue: dict[str, DescriptionItem] | None = None,
) -> HeuristicChoice | None:
    """Return the fixed plan, or None when the arm should wait."""

    policy = policy or load_heuristic_policy()
    catalogue = catalogue or catalogue_index()
    if forced_context is not None and forced_context not in CONTEXTS:
        raise ValueError("forced_context must be release or backup")
    context = forced_context or _latest_context(observations, policy)
    if context is None:
        return None
    if forced_context is None:
        anchor = _latest_unambiguous(observations, policy)
    else:
        anchor = _latest_any(observations)
    slot_hint = _slot_for_path(anchor.path, policy) if anchor is not None else None
    rows = list(policy.fallback[context])
    if slot_hint is not None:
        for index, row in enumerate(rows):
            if row["slot_id"] == slot_hint:
                picked = rows.pop(index)
                rows.insert(0, picked)
                break
    for row in rows:
        if row["slot_id"] in occupied_slots:
            continue
        item = catalogue[row["description_id"]]
        return HeuristicChoice(
            context_id=context,
            slot_id=row["slot_id"],
            template_id=row["template_id"],
            description_id=row["description_id"],
            description=item.text,
        )
    return None


def _require_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"heuristic field {key} must be a string")
    return value


def _latest_context(
    observations: list[ActivityObservation],
    policy: HeuristicPolicy,
) -> str | None:
    chosen = _latest_unambiguous(observations, policy)
    if chosen is None:
        return None
    return _contexts_for(chosen, policy)


def _latest_unambiguous(
    observations: list[ActivityObservation],
    policy: HeuristicPolicy,
) -> ActivityObservation | None:
    for observation in sorted(observations, key=lambda item: item.seq, reverse=True):
        if _contexts_for(observation, policy) is not None:
            return observation
    return None


def _latest_any(observations: list[ActivityObservation]) -> ActivityObservation | None:
    if not observations:
        return None
    return max(observations, key=lambda item: item.seq)


def _contexts_for(observation: ActivityObservation, policy: HeuristicPolicy) -> str | None:
    haystack = f"{observation.search_text}\n{observation.path}".casefold()
    matched = [
        context
        for context, terms in policy.keywords.items()
        if any(term.casefold() in haystack for term in terms)
    ]
    if len(matched) == 1:
        return matched[0]
    return None


def _slot_for_path(path: str, policy: HeuristicPolicy) -> str | None:
    normalized = path.replace("\\", "/").lstrip("./")
    for prefix, slot_id in policy.path_slots:
        if normalized.startswith(prefix):
            return slot_id
    return None
