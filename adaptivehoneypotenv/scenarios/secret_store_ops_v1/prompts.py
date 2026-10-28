"""Objective prompts and benign tasks. Both are actor-visible text."""

from __future__ import annotations

import json
from pathlib import Path

from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    CONTEXTS,
    PACKAGE_DIR,
    expect_mapping,
)

PROMPTS_PATH = PACKAGE_DIR / "objective_prompts.json"
BENIGN_PATH = PACKAGE_DIR / "benign_tasks.json"


def load_objective_prompts(path: Path | None = None) -> dict[str, dict[str, str]]:
    raw: object = json.loads((path or PROMPTS_PATH).read_text(encoding="utf-8"))
    payload = expect_mapping(raw, "objective prompts")
    prompts = expect_mapping(payload.get("prompts"), "prompts")
    result: dict[str, dict[str, str]] = {}
    for workflow in CONTEXTS:
        row = expect_mapping(prompts.get(workflow), workflow)
        parsed: dict[str, str] = {}
        for awareness in ("naive", "deception_aware"):
            text = row.get(awareness)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"missing {workflow}/{awareness} objective prompt")
            parsed[awareness] = text
        result[workflow] = parsed
    return result


def load_benign_tasks(path: Path | None = None) -> tuple[dict[str, object], ...]:
    raw: object = json.loads((path or BENIGN_PATH).read_text(encoding="utf-8"))
    payload = expect_mapping(raw, "benign tasks")
    tasks_raw = payload.get("tasks")
    if not isinstance(tasks_raw, list):
        raise ValueError("benign tasks must be a list")
    tasks = tuple(expect_mapping(item, "benign task") for item in tasks_raw)
    kinds: set[object] = {task.get("kind") for task in tasks}
    expected: set[object] = {
        "find_configuration",
        "explain_workflow",
        "diagnose_authorized_integration",
    }
    if kinds != expected:
        raise ValueError(f"benign task kinds must be {sorted(str(item) for item in expected)}")
    return tasks
