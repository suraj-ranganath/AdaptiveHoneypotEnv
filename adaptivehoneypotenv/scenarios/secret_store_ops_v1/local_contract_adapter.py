"""LOCAL ADAPTER — delete this module after Phase 0 merges.

Phase 0 freezes the action schema, the catalogue builder, the event envelope,
the defender observation, and the run manifest. Those types are not defined
here, and this package does not invent a second copy of them.

``ValidatedDecoySpec`` is only the four fields the renderer is allowed to
read once a deploy item has already been validated: template, slot, context,
and description. It is not an action schema. It has no path, URL, username,
password, or stored-value field. The model does not supply those.

When Phase 0 lands, construct this spec from the frozen validated item (or
replace the parameter type) and pass ``load_description_catalogue()`` into
the catalogue builder. Do not fork an action enum in this package.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatedDecoySpec:
    """Renderer input for one decoy that has already passed schema checks.

    Catalogue track: set ``description_id`` and leave ``description`` empty.
    Contextual track: set ``description`` and leave ``description_id`` empty.
    """

    template_id: str
    slot_id: str
    context_id: str
    description: str = ""
    description_id: str | None = None
