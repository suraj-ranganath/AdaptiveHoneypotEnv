"""Task package for ``secret_store_ops/v1``.

Phase 0 owns the action schema, catalogue builder, event envelope, defender
observation, and run manifest. This module loads the authored scenario and
re-exports fixture, renderer, solver, and verifier functions. Approved
description ids are passed to ``contracts.catalogue.build_catalogue``.
"""

from adaptivehoneypotenv.contracts.actions import CatalogueDecoySpec, ContextualDecoySpec
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.catalogue import (
    AUDIT_VERSION,
    SCENARIO_AUDIT_VERSION,
    approved_description_ids,
    audit_description,
    build_scenario_catalogue,
    load_description_catalogue,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.fixtures import (
    build_fixture_bundle,
    materialize_workspace,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.heuristic import (
    load_heuristic_policy,
    select_heuristic_plan,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.prompts import (
    load_benign_tasks,
    load_objective_prompts,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.rng import make_streams
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.solver import (
    discover_credential,
    export_solver_trace,
    solve_reference_route,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    SCENARIO_ID,
    load_scenario_document,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.templates.renderers import render_decoy
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.verifier import (
    giveaway_findings,
    grade_benign_task,
    structural_findings,
    template_fields_match_account,
)

__all__ = [
    "AUDIT_VERSION",
    "SCENARIO_AUDIT_VERSION",
    "SCENARIO_ID",
    "CatalogueDecoySpec",
    "ContextualDecoySpec",
    "approved_description_ids",
    "audit_description",
    "build_fixture_bundle",
    "build_scenario_catalogue",
    "discover_credential",
    "export_solver_trace",
    "giveaway_findings",
    "grade_benign_task",
    "load_benign_tasks",
    "load_description_catalogue",
    "load_heuristic_policy",
    "load_objective_prompts",
    "load_scenario_document",
    "make_streams",
    "materialize_workspace",
    "render_decoy",
    "select_heuristic_plan",
    "solve_reference_route",
    "structural_findings",
    "template_fields_match_account",
]
