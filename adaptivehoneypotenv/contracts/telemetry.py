"""Categorical telemetry codes shared by observations and event projections.

Messageboard tools are intentionally absent. A defender projection cannot
name them.
"""

from __future__ import annotations

from enum import Enum


class DefenderVisibleToolName(str, Enum):
    list_directory = "list_directory"
    search_files = "search_files"
    read_file = "read_file"
    request_service = "request_service"
    finish = "finish"


class PathCategory(str, Enum):
    source = "source"
    ops_deploy = "ops_deploy"
    ops_integrations = "ops_integrations"
    ops_ci = "ops_ci"
    ops_runbooks = "ops_runbooks"
    service = "service"
    none = "none"


class HttpMethodCategory(str, Enum):
    none = "none"
    GET = "GET"
    POST = "POST"


class HttpStatusCategory(str, Enum):
    none = "none"
    success = "success"
    client_error = "client_error"
    server_error = "server_error"
    other = "other"


PATH_CATEGORY_BY_PREFIX: dict[str, PathCategory] = {
    "source": PathCategory.source,
    "ops/deploy": PathCategory.ops_deploy,
    "ops/integrations": PathCategory.ops_integrations,
    "ops/ci": PathCategory.ops_ci,
    "ops/runbooks": PathCategory.ops_runbooks,
}


def category_for_workspace_path(path: str) -> PathCategory:
    for prefix, category in PATH_CATEGORY_BY_PREFIX.items():
        if path == prefix or path.startswith(prefix + "/"):
            return category
    if path == ".":
        return PathCategory.none
    return PathCategory.source if path.startswith("source/") else PathCategory.none
