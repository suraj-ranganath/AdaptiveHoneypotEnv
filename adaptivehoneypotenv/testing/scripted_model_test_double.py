"""Scripted model test double.

This is not an attacker policy and it does not invent tool results, search
hits, or HTTP responses. It returns the next scripted completion so other
components can be tested without a live model call.

A live or scored run manifest cannot name this adapter.
"""

from __future__ import annotations

from collections.abc import Sequence

from adaptivehoneypotenv.contracts.limits import TEST_DOUBLE_MODEL_ADAPTER_ID
from adaptivehoneypotenv.model_api import ChatCompletionRequest, ChatCompletionResult


class ScriptExhaustedError(RuntimeError):
    """The script has no remaining completion."""


class ScriptedModelTestDouble:
    """TEST DOUBLE. ``adapter_id`` is rejected by live and scored manifests."""

    adapter_id = TEST_DOUBLE_MODEL_ADAPTER_ID

    def __init__(self, script: Sequence[ChatCompletionResult]) -> None:
        self._script = tuple(script)
        self._index = 0

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        if not isinstance(request, ChatCompletionRequest):
            raise TypeError("scripted test double requires a ChatCompletionRequest")
        if self._index >= len(self._script):
            raise ScriptExhaustedError("scripted test double has no remaining turns")
        result = self._script[self._index]
        self._index += 1
        return result

    @property
    def remaining(self) -> int:
        return len(self._script) - self._index
