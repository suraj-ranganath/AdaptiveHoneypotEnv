"""OpenRouter chat-completions adapter for the trusted controller.

The provider key is read from ``OPENROUTER_API_KEY`` at call time and is not
stored on this object. Worst-case cost is reserved before each HTTP attempt
and replaced by the billed amount. ``CostCapExceeded`` is a clean external
cutoff, not a defender win. Refusals and parse failures are returned as
turns with ``counts_as_defender_win`` fixed to false.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import httpx

from adaptivehoneypotenv.contracts.actions import Action
from adaptivehoneypotenv.contracts.limits import (
    LIVE_MODEL_ADAPTER_ID,
    PROVIDER_CREDENTIAL_ENV_VAR,
    TEAM_GENERATED_TOKEN_BUDGET,
)
from adaptivehoneypotenv.contracts.manifest import ResolvedManifest, assert_live_adapter
from adaptivehoneypotenv.contracts.tools import (
    ToolProfile,
    attacker_tool_names,
    openai_tool_schemas,
)
from adaptivehoneypotenv.model_api import (
    ChatCompletionRequest,
    ChatCompletionResult,
    ChatMessage,
    FinishReason,
    TokenUsage,
    ToolCall,
)
from adaptivehoneypotenv.models.config import AdapterConfig
from adaptivehoneypotenv.models.errors import (
    MissingProviderCredential,
    ProviderRequestError,
    ProviderTransportExhausted,
    ScriptedAdapterRejected,
    TeamGeneratedTokenBudgetExhausted,
)
from adaptivehoneypotenv.models.ledger import RoleName, SpendLedger
from adaptivehoneypotenv.models.parsing import (
    AttackerTurn,
    DefenderParseError,
    DefenderTurn,
    TrackName,
    classify_attacker_outcome,
    defender_response_format,
    parse_defender_action,
)
from adaptivehoneypotenv.models.pricing import (
    CostSource,
    estimate_prompt_tokens,
    price_table_cost,
    provider_cost,
    usage_from_payload,
    worst_case_cost_usd,
)
from adaptivehoneypotenv.models.redact import (
    install_redacting_filters,
    push_secret,
    redact_provider_key,
    redact_text,
    reset_secret,
)
from adaptivehoneypotenv.models.tokens import attacker_call_token_cap

_logger = logging.getLogger(__name__)
install_redacting_filters()

Sleep = Callable[[float], None]
_CALL_ID = re.compile(r"^call_[A-Za-z0-9_-]{1,64}$")
_FINISH = {
    "stop": FinishReason.stop,
    "tool_calls": FinishReason.tool_calls,
    "length": FinishReason.length,
    "content_filter": FinishReason.content_filter,
}


@dataclass(frozen=True)
class _Exchange:
    kind: Literal["timeout", "transport", "http"]
    status: int | None = None
    payload: dict[str, Any] | None = None
    excerpt: str = ""
    retry_after: float | None = None


class OpenAICompatibleAdapter:
    """Live ``openai_compatible`` client. Not the scripted test double."""

    adapter_id = LIVE_MODEL_ADAPTER_ID

    def __init__(self, config: AdapterConfig, *, sleep: Sleep = time.sleep) -> None:
        self._config = config
        self._sleep = sleep
        self._ledger = SpendLedger(
            config.ledger_path,
            cap_usd=config.cap_usd,
            team_token_budget=config.team_token_budget,
        )
        self._url = config.base_url.rstrip("/") + "/chat/completions"

    def __repr__(self) -> str:
        return "OpenAICompatibleAdapter(adapter_id='openai_compatible')"

    @classmethod
    def from_manifest(
        cls,
        manifest: ResolvedManifest,
        *,
        ledger_path: Path,
        sleep: Sleep = time.sleep,
    ) -> OpenAICompatibleAdapter:
        """Build the live adapter. ``scripted_test_double`` is rejected."""

        if manifest.model_adapter != LIVE_MODEL_ADAPTER_ID:
            raise ScriptedAdapterRejected(manifest.purpose)
        assert_live_adapter(manifest.model_adapter, purpose=manifest.purpose)
        config = AdapterConfig.from_manifest(manifest, ledger_path=ledger_path)
        return cls(config, sleep=sleep)

    def spent_usd(self) -> Decimal:
        return self._ledger.spent()

    def attacker_generated_tokens(self) -> int:
        return self._ledger.attacker_generated_tokens()

    def token_accounting_available(self) -> bool:
        return self._ledger.token_accounting_available()

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        """Protocol completion. Uses the stricter of the attacker and defender caps.

        Team generated tokens are accounted by :meth:`complete_attacker`.
        Defender calls must use :meth:`complete_defender` so they do not
        consume that budget. This method still enforces the cost cap.
        """

        ceiling = min(self._config.attacker_per_call_cap, self._config.defender_per_call_cap)
        timeout = min(self._config.attacker_timeout_seconds, self._config.defender_timeout_seconds)
        return self._dispatch(
            request,
            role="unscoped",
            timeout_seconds=timeout,
            token_ceiling=ceiling,
            response_format=None,
        )

    def complete_attacker(
        self,
        request: ChatCompletionRequest,
        *,
        profile: ToolProfile = ToolProfile.malicious,
        parallel_calls: int = 1,
    ) -> AttackerTurn:
        """Attacker turn with the seven-tool export and the team token hook."""

        if parallel_calls < 1:
            raise ValueError("parallel_calls must be positive")
        per_call = min(self._config.attacker_max_tokens, self._config.attacker_per_call_cap)
        spent = self._ledger.attacker_generated_tokens()
        remaining = max(0, TEAM_GENERATED_TOKEN_BUDGET - spent)
        ceiling = attacker_call_token_cap(
            per_call_cap=per_call,
            remaining_team_tokens=remaining,
            parallel_calls=parallel_calls,
        )
        if ceiling < 1:
            raise TeamGeneratedTokenBudgetExhausted(
                spent_tokens=spent,
                budget=TEAM_GENERATED_TOKEN_BUDGET,
            )
        prepared = request.model_copy(update={"tools": tuple(openai_tool_schemas(profile))})
        result = self._dispatch(
            prepared,
            role="attacker",
            timeout_seconds=self._config.attacker_timeout_seconds,
            token_ceiling=ceiling,
            response_format=None,
        )
        status, detail, ends = classify_attacker_outcome(result, profile=profile)
        return AttackerTurn(
            status=status,
            completion=result,
            detail=detail,
            ends_attacker_session=ends,
        )

    def complete_defender(
        self,
        request: ChatCompletionRequest,
        *,
        track: TrackName,
    ) -> DefenderTurn:
        """Defender turn. Structured output only; credentials are not fields."""

        schema = defender_response_format(track)
        ceiling = min(self._config.defender_max_tokens, self._config.defender_per_call_cap)
        prepared = request.model_copy(update={"tools": ()})
        result = self._dispatch(
            prepared,
            role="defender",
            timeout_seconds=self._config.defender_timeout_seconds,
            token_ceiling=ceiling,
            response_format=schema,
        )
        return _defender_turn(result, track)

    def _dispatch(
        self,
        request: ChatCompletionRequest,
        *,
        role: RoleName,
        timeout_seconds: float,
        token_ceiling: int,
        response_format: dict[str, Any] | None,
    ) -> ChatCompletionResult:
        if request.model != self._config.model:
            raise ProviderRequestError("request model does not match the pinned model")
        _assert_tools_allowed(request.tools)
        if request.max_tokens is None:
            applied = token_ceiling
        else:
            applied = min(request.max_tokens, token_ceiling)
        if applied < 1:
            if role == "attacker":
                raise TeamGeneratedTokenBudgetExhausted(
                    spent_tokens=self._ledger.attacker_generated_tokens(),
                    budget=TEAM_GENERATED_TOKEN_BUDGET,
                )
            raise ProviderRequestError("max_tokens must be positive")
        prepared = request.model_copy(update={"max_tokens": applied})
        extra = json.dumps(response_format) if response_format is not None else ""
        body = _wire_body(
            prepared,
            response_format=response_format,
            seed=self._config.seed,
            default_temperature=self._config.temperature,
        )
        estimate = worst_case_cost_usd(
            max_tokens=applied,
            prompt_tokens_estimate=estimate_prompt_tokens(prepared, extra),
        )
        last_status: int | None = None
        last_excerpt = ""
        for attempt in range(1, self._config.max_attempts + 1):
            if role == "attacker":
                spent_tokens = self._ledger.attacker_generated_tokens()
                if spent_tokens >= TEAM_GENERATED_TOKEN_BUDGET:
                    raise TeamGeneratedTokenBudgetExhausted(
                        spent_tokens=spent_tokens,
                        budget=TEAM_GENERATED_TOKEN_BUDGET,
                    )
            entry_id = self._ledger.reserve(role=role, reserved_usd=estimate)
            outcome = self._exchange(body, timeout_seconds, entry_id)
            if outcome.kind in {"timeout", "transport"}:
                last_excerpt = outcome.kind
                last_status = None
                if attempt == self._config.max_attempts:
                    break
                self._sleep(backoff_seconds(attempt, None))
                _logger.info("provider retry attempt=%s kind=%s", attempt, outcome.kind)
                continue
            billed = _bill(outcome.payload, applied_max_tokens=applied, role=role)
            if outcome.status == 200 and outcome.payload is not None:
                self._ledger.settle(
                    entry_id,
                    cost_usd=billed[0],
                    source=billed[1],
                    usage=billed[2],
                    reconciled=billed[3],
                )
                _logger.info(
                    "provider completion prompt_tokens=%s completion_tokens=%s cost_source=%s",
                    billed[2].prompt_tokens,
                    billed[2].completion_tokens,
                    billed[1],
                )
                return _result_from_payload(outcome.payload, billed[2])
            if outcome.payload is not None and _has_bill(outcome.payload):
                self._ledger.settle(
                    entry_id,
                    cost_usd=billed[0],
                    source=billed[1],
                    usage=billed[2],
                    reconciled=billed[3],
                )
            else:
                self._ledger.release(entry_id)
            last_status = outcome.status
            last_excerpt = outcome.excerpt
            if outcome.status is not None and _retryable(outcome.status):
                if attempt == self._config.max_attempts:
                    break
                delay = backoff_seconds(attempt, outcome.retry_after)
                _logger.info(
                    "provider retry attempt=%s status=%s sleep_seconds=%s",
                    attempt,
                    outcome.status,
                    delay,
                )
                self._sleep(delay)
                continue
            detail = f"provider request failed status={outcome.status} excerpt={outcome.excerpt}"
            raise ProviderRequestError(redact_text(detail), status_code=outcome.status)
        raise ProviderTransportExhausted(
            redact_text(
                "provider transport exhausted after "
                f"{self._config.max_attempts} attempts "
                f"(last_status={last_status} excerpt={last_excerpt[:300]})"
            ),
            attempts=self._config.max_attempts,
        )

    def _exchange(self, body: dict[str, Any], timeout_seconds: float, entry_id: str) -> _Exchange:
        try:
            key = _read_provider_key()
        except MissingProviderCredential:
            self._ledger.release(entry_id)
            raise
        token = push_secret(key)
        try:
            headers = {
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            }
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(timeout_seconds),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = client.post(self._url, headers=headers, json=body)
                    status = response.status_code
                    text = response.text
                    retry_raw = response.headers.get("Retry-After")
                del response
            except httpx.TimeoutException:
                self._ledger.release(entry_id)
                return _Exchange(kind="timeout")
            except httpx.HTTPError:
                self._ledger.release(entry_id)
                return _Exchange(kind="transport")
            if len(text) > 1_000_000:
                text = text[:1_000_000]
            scrubbed = redact_provider_key(text, (key,))
            del text
            payload = _json_object(scrubbed)
            excerpt = redact_text(scrubbed[:500], (key,))
            return _Exchange(
                kind="http",
                status=status,
                payload=payload,
                excerpt=excerpt,
                retry_after=_retry_after(retry_raw),
            )
        finally:
            reset_secret(token)
            del key


def open_adapter(
    manifest: ResolvedManifest,
    *,
    ledger_path: Path,
    sleep: Sleep = time.sleep,
) -> OpenAICompatibleAdapter:
    """Build the live adapter. The scripted test double is rejected."""

    return OpenAICompatibleAdapter.from_manifest(manifest, ledger_path=ledger_path, sleep=sleep)


def backoff_seconds(failed_attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(30.0, max(0.0, retry_after))
    return min(8.0, 0.25 * (2.0 ** (failed_attempt - 1)))


def controller_setting(name: str) -> str | None:
    """Read a non-credential controller flag. The provider key is not available here."""

    if name == PROVIDER_CREDENTIAL_ENV_VAR:
        raise MissingProviderCredential("the provider credential is read only on the send path")
    return os.environ.get(name)


def _read_provider_key() -> str:
    raw = os.environ.get(PROVIDER_CREDENTIAL_ENV_VAR)
    if raw is None or raw.strip() == "":
        raise MissingProviderCredential("OPENROUTER_API_KEY is unset")
    key = raw.strip()
    if any(char in key for char in "\r\n\x00"):
        raise MissingProviderCredential("OPENROUTER_API_KEY is unusable")
    return key


def _retryable(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _retry_after(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        loaded: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return cast(dict[str, Any], loaded)


def _has_bill(payload: dict[str, Any]) -> bool:
    return provider_cost(payload) is not None or usage_from_payload(payload) is not None


def _bill(
    payload: dict[str, Any] | None,
    *,
    applied_max_tokens: int,
    role: RoleName,
) -> tuple[Decimal, CostSource, TokenUsage, bool]:
    parsed = usage_from_payload(payload) if payload is not None else None
    cost = provider_cost(payload) if payload is not None else None
    if parsed is None:
        completion = applied_max_tokens if role == "attacker" else 0
        usage = TokenUsage(prompt_tokens=0, completion_tokens=completion, reasoning_tokens=0)
        amount = cost if cost is not None else price_table_cost(usage)
        source: CostSource = "provider" if cost is not None else "price_table"
        return amount, source, usage, False
    usage, reconciled = parsed
    if cost is not None:
        return cost, "provider", usage, reconciled
    return price_table_cost(usage), "price_table", usage, reconciled


def _assert_tools_allowed(tools: tuple[dict[str, Any], ...]) -> None:
    if not tools:
        return
    allowed = attacker_tool_names()
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ProviderRequestError("request tools must be the attacker tool set")
        name = function.get("name")
        if not isinstance(name, str) or name not in allowed:
            raise ProviderRequestError("request tools must be the attacker tool set")


def _wire_body(
    request: ChatCompletionRequest,
    *,
    response_format: dict[str, Any] | None,
    seed: int | None,
    default_temperature: float | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [_message_to_wire(message) for message in request.messages],
        "max_tokens": request.max_tokens,
        "provider": {"allow_fallbacks": False},
        "usage": {"include": True},
        "stream": False,
    }
    temperature = request.temperature if request.temperature is not None else default_temperature
    if temperature is not None:
        body["temperature"] = temperature
    if request.tools:
        body["tools"] = list(request.tools)
        body["tool_choice"] = "auto"
        body["parallel_tool_calls"] = False
    if response_format is not None:
        body["response_format"] = response_format
    if seed is not None:
        body["seed"] = seed
    return body


def _message_to_wire(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id or ""
        payload["content"] = message.content or ""
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments_json},
            }
            for call in message.tool_calls
        ]
    return payload


def _result_from_payload(payload: dict[str, Any], usage: TokenUsage) -> ChatCompletionResult:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderRequestError("provider response did not include a completion")
    first = cast(dict[str, Any], choices[0])
    message = first.get("message")
    if not isinstance(message, dict):
        raise ProviderRequestError("provider response did not include a message")
    message_dict = cast(dict[str, Any], message)
    finish_name = first.get("finish_reason")
    finish_raw = finish_name if isinstance(finish_name, str) else ""
    refusal_raw = message_dict.get("refusal")
    if isinstance(refusal_raw, str) and refusal_raw.strip():
        refusal: str | None = redact_provider_key(refusal_raw)
    elif finish_raw in {"refusal", "content_filter"}:
        refusal = "content_filter" if finish_raw == "content_filter" else "provider refusal"
    else:
        refusal = None
    tool_calls: tuple[ToolCall, ...] = ()
    if refusal is None:
        tool_calls = _tool_calls(message_dict.get("tool_calls"))
    if refusal is not None:
        finish = (
            FinishReason.content_filter
            if finish_raw in {"content_filter", "refusal"}
            else FinishReason.stop
        )
    elif tool_calls:
        finish = FinishReason.tool_calls
    else:
        finish = _FINISH.get(finish_raw, FinishReason.stop)
    content = _content_text(message_dict.get("content"))
    if content is not None:
        content = redact_provider_key(content)
        if content == "":
            content = None
    try:
        return ChatCompletionResult(
            message=ChatMessage(role="assistant", content=content, tool_calls=tool_calls),
            usage=usage,
            finish_reason=finish,
            refusal=refusal,
        )
    except ValueError:
        raise ProviderRequestError("provider completion did not match the result schema") from None


def _tool_calls(raw: object) -> tuple[ToolCall, ...]:
    if not isinstance(raw, list):
        return ()
    calls: list[ToolCall] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            function = {}
        name = function.get("name")
        tool_name = name if isinstance(name, str) and name else "invalid"
        if len(tool_name) > 64:
            tool_name = tool_name[:64]
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            arguments_json = arguments
        else:
            try:
                arguments_json = json.dumps(arguments if arguments is not None else {})
            except TypeError:
                arguments_json = "{}"
        arguments_json = redact_provider_key(arguments_json)
        if len(arguments_json) > 16_384:
            arguments_json = "{}"
        calls.append(
            ToolCall(
                id=_tool_id(item.get("id"), index),
                name=tool_name,
                arguments_json=arguments_json,
            )
        )
    return tuple(calls)


def _tool_id(raw: object, index: int) -> str:
    if isinstance(raw, str) and _CALL_ID.fullmatch(raw):
        return raw
    material = raw if isinstance(raw, str) else str(index)
    digest = hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"call_{digest}"


def _content_text(content: object) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return None


def _defender_turn(result: ChatCompletionResult, track: TrackName) -> DefenderTurn:
    if result.refusal is not None or result.finish_reason is FinishReason.content_filter:
        return DefenderTurn(
            status="refusal",
            completion=result,
            action=None,
            detail=result.refusal or "content_filter",
        )
    try:
        action: Action = parse_defender_action(result.message.content or "", track=track)
    except DefenderParseError as exc:
        return DefenderTurn(
            status="parse_failure",
            completion=result,
            action=None,
            detail=redact_text(str(exc)),
        )
    return DefenderTurn(status="ok", completion=result, action=action, detail=None)
