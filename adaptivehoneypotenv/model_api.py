"""OpenAI-compatible chat completion interface shared by attacker and defender calls.

The trusted controller is the only caller. This module has no HTTP client and
no credential field. WS4 implements the live adapter behind ``adapter_id``
``openai_compatible``. The scripted test double is a separate type and cannot
be selected by a live or scored manifest.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptivehoneypotenv.contracts.limits import LIVE_MODEL_ADAPTER_ID
from adaptivehoneypotenv.contracts.versions import MODEL_API_SCHEMA_VERSION


class FinishReason(str, Enum):
    stop = "stop"
    tool_calls = "tool_calls"
    length = "length"
    content_filter = "content_filter"


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Annotated[str, Field(pattern=r"^call_[A-Za-z0-9_-]{1,64}$")]
    name: Annotated[str, Field(min_length=1, max_length=64)]
    arguments_json: Annotated[str, Field(max_length=16_384)]


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prompt_tokens: Annotated[int, Field(ge=0)]
    completion_tokens: Annotated[int, Field(ge=0)]
    reasoning_tokens: Annotated[int, Field(ge=0)] = 0
    # When true, completion_tokens already includes reasoning tokens.
    reasoning_included_in_completion: bool = True

    @property
    def generated_tokens(self) -> int:
        if self.reasoning_included_in_completion:
            return self.completion_tokens
        return self.completion_tokens + self.reasoning_tokens


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ChatCompletionRequest(BaseModel):
    """A completion request. Provider credentials are not a field."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = MODEL_API_SCHEMA_VERSION
    model: str
    messages: Annotated[tuple[ChatMessage, ...], Field(min_length=1)]
    tools: tuple[dict[str, Any], ...] = ()
    temperature: Annotated[float, Field(ge=0, le=2)] | None = None
    max_tokens: Annotated[int, Field(ge=1)] | None = None


class ChatCompletionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = MODEL_API_SCHEMA_VERSION
    message: ChatMessage
    usage: TokenUsage
    finish_reason: FinishReason
    refusal: str | None = None

    @model_validator(mode="after")
    def refusal_excludes_tool_calls(self) -> ChatCompletionResult:
        if self.refusal is not None and self.message.tool_calls:
            raise ValueError("a refusal does not include tool calls")
        if self.message.role != "assistant":
            raise ValueError("completion message role is assistant")
        return self


class ModelAdapter(Protocol):
    """The interface WS4's OpenAI-compatible client and the test double share."""

    adapter_id: str

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult: ...


def is_live_adapter_id(adapter_id: str) -> bool:
    return adapter_id == LIVE_MODEL_ADAPTER_ID
