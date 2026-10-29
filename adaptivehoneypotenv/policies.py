"""Defender request and scripted completion parsing.

Attacker actions are not chosen here. The live defender turn is parsed by
the OpenRouter adapter. The scripted test double returns one wait or deploy
tool call, which this module turns into an action. A refusal or unusable
completion is a no-op, not a win.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from adaptivehoneypotenv.contracts.actions import Action, DeployAction, WaitAction, parse_action
from adaptivehoneypotenv.contracts.limits import DEFAULT_MODEL
from adaptivehoneypotenv.contracts.observations import DefenderObservation
from adaptivehoneypotenv.model_api import (
    ChatCompletionRequest,
    ChatCompletionResult,
    ChatMessage,
    FinishReason,
)
from adaptivehoneypotenv.testing.scripted_model_test_double import ScriptedModelTestDouble

_DEFENDER_SYSTEM = (
    "You defend a software operation by choosing wait or deploy. "
    "A deploy uses one or two decoy specs drawn from the observation. "
    "You see redacted activity and your committed deployments. "
    "Choose from that observation alone."
)

_DEFENDER_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Leave the workspace unchanged.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy",
            "description": "Commit one or two decoy specs.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"decoys": {"type": "array"}},
                "required": ["decoys"],
            },
        },
    },
)


def defender_request(
    observation: DefenderObservation,
    *,
    max_tokens: int | None = None,
) -> ChatCompletionRequest:
    """Build the defender completion. The text is the redacted observation."""

    return ChatCompletionRequest(
        model=DEFAULT_MODEL,
        messages=(
            ChatMessage(role="system", content=_DEFENDER_SYSTEM),
            ChatMessage(role="user", content=observation.model_dump_json()),
        ),
        tools=_DEFENDER_TOOLS,
        temperature=0,
        max_tokens=max_tokens,
    )


def parse_defender_action(result: ChatCompletionResult) -> Action | None:
    """Parse one scripted tool call. Anything else is a no-op."""

    if result.refusal is not None or result.finish_reason is FinishReason.content_filter:
        return None
    calls = result.message.tool_calls
    if len(calls) != 1:
        return None
    call = calls[0]
    try:
        payload = json.loads(call.arguments_json) if call.arguments_json else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if call.name == "wait":
        if payload:
            return None
        return WaitAction(kind="wait")
    if call.name != "deploy":
        return None
    decoys = payload.get("decoys")
    if not isinstance(decoys, list):
        return None
    try:
        action = parse_action({"kind": "deploy", "decoys": decoys})
    except ValidationError:
        return None
    if not isinstance(action, DeployAction):
        return None
    return action


class ScriptedDefender:
    """Holds the scripted test double. Not an attacker policy."""

    adapter_id = ScriptedModelTestDouble.adapter_id

    def __init__(self, script: Sequence[ChatCompletionResult]) -> None:
        self._model = ScriptedModelTestDouble(script)

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        return self._model.complete(request)
