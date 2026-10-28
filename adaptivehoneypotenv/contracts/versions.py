"""Frozen schema versions.

Only the orchestrator changes this module. Subagents propose changes in a
pull request and leave the frozen files untouched on main.
"""

from typing import Final

DESIGN_VERSION: Final = "1.1"
SCENARIO_ID: Final = "secret_store_ops/v1"

ACTION_SCHEMA_VERSION: Final = "1.0.0"
OBSERVATION_SCHEMA_VERSION: Final = "1.0.0"
EVENT_SCHEMA_VERSION: Final = "1.0.0"
TRANSITION_SCHEMA_VERSION: Final = "1.0.0"
TOOL_SCHEMA_VERSION: Final = "1.0.0"
MANIFEST_SCHEMA_VERSION: Final = "1.0.0"
MODEL_API_SCHEMA_VERSION: Final = "1.0.0"

CATALOGUE_ORDERING_VERSION: Final = "secret_store_ops/v1.ordering.1"
DESCRIPTION_AUDIT_VERSION: Final = "secret_store_ops/v1.audit.1"
