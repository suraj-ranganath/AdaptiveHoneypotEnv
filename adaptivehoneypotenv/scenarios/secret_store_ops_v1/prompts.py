"""Objective prompts and benign tasks. Both are actor-visible text."""

from __future__ import annotations

import json
from pathlib import Path

from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import CONTEXTS, PACKAGE_DIR

PROMPTS_PATH = PACKAGE_DIR / "objective_prompts.json"
BENIGN_PATH = PACKAGE_DIR / "benign_tasks.json"


def load_objective_prompts(path: Path | None = None) -> dict[str, dict[str, str]]:
    payload = json.loads((path or PROMPTS_PATH).read_text(encoding="utf-8"))
    prompts = payload["prompts"]
    for workflow in CONTEXTS:
        for awareness in ("naive", "deception_aware"):
            text = prompts[workflow][awareness]
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"missing {workflow}/{awareness} objective prompt")
    return prompts


def load_benign_tasks(path: Path | None = None) -> tuple[dict, ...]:
    payload = json.loads((path or BENIGN_PATH).read_text(encoding="utf-8"))
    tasks = tuple(payload["tasks"])
    kinds = {task["kind"] for task in tasks}
    expected = {"find_configuration", "explain_workflow", "diagnose_authorized_integration"}
    if kinds != expected:
        raise ValueError(f"benign task kinds must be {sorted(expected)}")
    return tasks
