"""Turn attacker tool calls and defender text into recorded outcomes.

A refusal or a parse failure has ``counts_as_defender_win`` fixed to false.
The defender schema exposes template, slot, context, and a bounded
description or description id. It has no credential, canary, or flag field,
and the parser rejects those keys if a model emits them anyway.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from adaptivehoneypotenv.contracts.actions import (
    CONTEXT_ORDER,
    SLOT_ORDER,
    TEMPLATE_ORDER,
    Action,
    parse_action,
)
from adaptivehoneypotenv.contracts.limits import (
    DESCRIPTION_MAX_UNICODE_CHARS,
    MAX_DECOYS,
)
from adaptivehoneypotenv.contracts.tools import (
    TOOL_MODELS,
    AttackerToolName,
    RequestServiceArgs,
    ToolProfile,
    classify_service_request,
)
from adaptivehoneypotenv.contracts.versions import ACTION_SCHEMA_VERSION
from adaptivehoneypotenv.model_api import ChatCompletionResult, FinishReason

TrackName = Literal["catalogue", "contextual"]
_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "canary",
        "credential",
        "credentials",
        "flag",
        "jwt",
        "password",
        "private_key",
        "secret",
        "token",
    }
)


class DefenderParseError(ValueError):
    """The model text is not a defender action. Not a win."""


def defender_response_format(track: TrackName) -> dict[str, Any]:
    """OpenAI ``response_format`` for one defender decision.

    Bounds and the syntax audit are enforced by ``parse_action`` after the
    provider returns. The schema itself only offers the action fields.
    """

    text_field = "description" if track == "contextual" else "description_id"
    spec_properties: dict[str, Any] = {
        "template_id": {"type": "string", "enum": [item.value for item in TEMPLATE_ORDER]},
        "slot_id": {"type": "string", "enum": [item.value for item in SLOT_ORDER]},
        "context_id": {"type": "string", "enum": [item.value for item in CONTEXT_ORDER]},
        text_field: {"type": "string"},
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "defender_action",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["wait", "deploy"]},
                    "decoys": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": spec_properties,
                            "required": [
                                "template_id",
                                "slot_id",
                                "context_id",
                                text_field,
                            ],
                        },
                    },
                },
                "required": ["kind", "decoys"],
            },
        },
    }


def parse_defender_action(content: str, *, track: TrackName) -> Action:
    """Parse model text into ``wait`` or ``deploy``. Raises on failure."""

    payload = _load_object(_strip_fence(content))
    _reject_forbidden_keys(payload)
    kind = payload.get("kind")
    raw_decoys = payload.get("decoys", [])
    if set(payload) - {"kind", "decoys"}:
        raise DefenderParseError("defender action has unknown fields")
    if not isinstance(raw_decoys, list):
        raise DefenderParseError("decoys must be a list")
    if kind == "wait":
        if raw_decoys:
            raise DefenderParseError("wait cannot carry decoys")
        return parse_action({"schema_version": ACTION_SCHEMA_VERSION, "kind": "wait"})
    if kind != "deploy":
        raise DefenderParseError("defender action must be wait or deploy")
    if not 1 <= len(raw_decoys) <= MAX_DECOYS:
        raise DefenderParseError("deploy carries one or two decoys")
    text_field = "description" if track == "contextual" else "description_id"
    allowed = {"template_id", "slot_id", "context_id", text_field}
    specs: list[dict[str, str]] = []
    for item in raw_decoys:
        if not isinstance(item, dict):
            raise DefenderParseError("decoy spec must be an object")
        _reject_forbidden_keys(item)
        if set(item) != allowed:
            raise DefenderParseError("decoy spec fields do not match the track")
        spec: dict[str, str] = {
            "schema_version": ACTION_SCHEMA_VERSION,
            "track": track,
        }
        for key in ("template_id", "slot_id", "context_id", text_field):
            value = item[key]
            if not isinstance(value, str):
                raise DefenderParseError("decoy fields must be strings")
            if key == "description" and len(value) > DESCRIPTION_MAX_UNICODE_CHARS:
                raise DefenderParseError("description exceeds 240 characters")
            spec[key] = value
        specs.append(spec)
    try:
        return parse_action(
            {"schema_version": ACTION_SCHEMA_VERSION, "kind": "deploy", "decoys": specs}
        )
    except (ValidationError, ValueError):
        raise DefenderParseError("defender action failed schema validation") from None


def classify_attacker_outcome(
    result: ChatCompletionResult,
    *,
    profile: ToolProfile,
) -> tuple[Literal["ok", "refusal", "parse_failure", "invalid_tool_call"], str | None, bool]:
    """Classify one attacker completion.

    Returns status, detail, and whether the explicit refusal ends that
    attacker session. Plain text and malformed calls do not end the session
    and are not refusals. Nothing returned here is a defender win.
    """

    if result.refusal is not None or result.finish_reason is FinishReason.content_filter:
        return "refusal", result.refusal or "content_filter", True
    calls = result.message.tool_calls
    if len(calls) != 1:
        detail = "no tool call" if not calls else "multiple tool calls"
        return "invalid_tool_call", detail, False
    call = calls[0]
    try:
        name = AttackerToolName(call.name)
    except ValueError:
        return "parse_failure", "unknown tool", False
    try:
        arguments = json.loads(call.arguments_json)
    except json.JSONDecodeError:
        return "parse_failure", "tool arguments are not json", False
    if not isinstance(arguments, dict):
        return "parse_failure", "tool arguments must be an object", False
    try:
        validated = TOOL_MODELS[name].model_validate(arguments)
    except ValidationError:
        return "parse_failure", "tool arguments failed schema validation", False
    if isinstance(validated, RequestServiceArgs):
        pairs = [(header.name, header.value) for header in validated.headers]
        decision = classify_service_request(
            validated.method,
            validated.path,
            pairs,
            profile=profile,
        )
        if not decision.allowed:
            return "parse_failure", "service request is not allowed", False
    return "ok", None, False


TurnStatus = Literal["ok", "refusal", "parse_failure", "invalid_tool_call"]


class AttackerTurn(BaseModel):
    """One attacker model turn. Refusals and bad calls are not defender wins."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: TurnStatus
    completion: ChatCompletionResult
    detail: str | None = None
    ends_attacker_session: bool = False
    counts_as_defender_win: Literal[False] = False


class DefenderTurn(BaseModel):
    """One defender model turn. A parsed action is still not a detection."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ok", "refusal", "parse_failure"]
    completion: ChatCompletionResult
    action: Action | None = None
    detail: str | None = None
    counts_as_defender_win: Literal[False] = False


def _load_object(text: str) -> dict[str, Any]:
    try:
        loaded: Any = json.loads(text)
    except json.JSONDecodeError:
        raise DefenderParseError("defender output is not json") from None
    if not isinstance(loaded, dict):
        raise DefenderParseError("defender output must be an object")
    return loaded


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _reject_forbidden_keys(payload: dict[str, Any]) -> None:
    for key in payload:
        if key.lower() in _FORBIDDEN_KEYS:
            raise DefenderParseError("defender output included a forbidden field")
