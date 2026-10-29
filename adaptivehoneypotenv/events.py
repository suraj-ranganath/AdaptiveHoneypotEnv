"""Controller journal on the shared episode log.

Tool events and controller events share one sequence. This module does not
open a second log and does not score.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from adaptivehoneypotenv.contracts.events import (
    Event,
    EventAdapter,
    EventStatus,
    PayloadRef,
    compute_event_id,
)
from adaptivehoneypotenv.gateway.gateway import ToolGateway


class ControllerLog:
    """Append-only controller writer. Sequences come from the gateway journal."""

    def __init__(self, gateway: ToolGateway) -> None:
        self._gateway = gateway

    def next_sequence(self) -> int:
        return self._gateway.next_sequence()

    def store(self, data: bytes) -> PayloadRef:
        return self._gateway.controller_store(data)

    def append(self, event: Event) -> None:
        self._gateway.controller_append(event)

    def events(self) -> tuple[Event, ...]:
        return self._gateway.events


def build_event(payload: Mapping[str, Any]) -> Event:
    return EventAdapter.validate_python(dict(payload))


def envelope(
    *,
    episode_id: str,
    sequence: int,
    kind: str,
    round_index: int,
    attempt_index: int,
    world_version: int,
    role: str,
    actor_id: str,
    status: EventStatus,
    started_ns: int,
    request_id: str | None = None,
    payload_refs: tuple[PayloadRef, ...] = (),
) -> dict[str, Any]:
    """Common envelope fields. ``event_id`` is the deterministic journal id."""

    return {
        "event_id": compute_event_id(episode_id, sequence, kind),
        "episode_id": episode_id,
        "sequence": sequence,
        "round_index": round_index,
        "attempt_index": attempt_index,
        "world_version": world_version,
        "actor": {"role": role, "actor_id": actor_id},
        "status": status,
        "monotonic_duration_ns": max(0, time.monotonic_ns() - started_ns),
        "wall_time_unix_ns": time.time_ns(),
        "request_id": request_id or f"req-{sequence}",
        "payload_refs": payload_refs,
    }
