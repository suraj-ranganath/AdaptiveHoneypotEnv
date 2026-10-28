"""The scripted completion double is not a live adapter."""

from pathlib import Path

import pytest
from adaptivehoneypotenv.contracts.limits import TEST_DOUBLE_MODEL_ADAPTER_ID
from adaptivehoneypotenv.model_api import (
    ChatCompletionRequest,
    ChatCompletionResult,
    ChatMessage,
    FinishReason,
    TokenUsage,
    ToolCall,
    is_live_adapter_id,
)
from adaptivehoneypotenv.testing.scripted_model_test_double import (
    ScriptedModelTestDouble,
    ScriptExhaustedError,
)
from pydantic import ValidationError


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="z-ai/glm-5.3-flash",
        messages=(ChatMessage(role="user", content="look at the workspace"),),
    )


def test_scripted_double_returns_tool_calls_usage_finish_reason_and_refusal() -> None:
    tool_result = ChatCompletionResult(
        message=ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_list1",
                    name="list_directory",
                    arguments_json='{"path":"."}',
                ),
            ),
        ),
        usage=TokenUsage(
            prompt_tokens=3,
            completion_tokens=5,
            reasoning_tokens=2,
            reasoning_included_in_completion=True,
        ),
        finish_reason=FinishReason.tool_calls,
    )
    refusal = ChatCompletionResult(
        message=ChatMessage(role="assistant", content=None),
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        finish_reason=FinishReason.stop,
        refusal="refused",
    )
    adapter = ScriptedModelTestDouble((tool_result, refusal))
    assert adapter.adapter_id == TEST_DOUBLE_MODEL_ADAPTER_ID
    assert is_live_adapter_id(adapter.adapter_id) is False

    first = adapter.complete(_request())
    assert first.finish_reason is FinishReason.tool_calls
    assert first.message.tool_calls[0].name == "list_directory"
    assert first.usage.generated_tokens == 5
    second = adapter.complete(_request())
    assert second.refusal == "refused"
    assert second.message.tool_calls == ()
    with pytest.raises(ScriptExhaustedError):
        adapter.complete(_request())

    separate = TokenUsage(
        prompt_tokens=1,
        completion_tokens=4,
        reasoning_tokens=3,
        reasoning_included_in_completion=False,
    )
    assert separate.generated_tokens == 7

    with pytest.raises(ValidationError):
        ChatCompletionResult(
            message=ChatMessage(
                role="assistant",
                tool_calls=(ToolCall(id="call_x", name="finish", arguments_json="{}"),),
            ),
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason=FinishReason.stop,
            refusal="no",
        )
    with pytest.raises(ValidationError):
        ChatCompletionRequest.model_validate(
            {
                "model": "z-ai/glm-5.3-flash",
                "messages": [{"role": "user", "content": "hi"}],
                "api_key": "sk-or-v1-test-only-not-a-credential",
            }
        )


def test_package_does_not_read_provider_env_or_import_a_network_client() -> None:
    """Only the adapter send path may read the provider env or import httpx."""

    banned_imports = (
        "import httpx",
        "import urllib",
        "import requests",
        "import socket",
        "import aiohttp",
        "import openai",
        "from httpx",
        "from urllib",
        "from requests",
        "from socket",
        "from openai",
        "os.environ",
        "getenv(",
    )
    # deployment.py is the trusted launcher. It opens the loopback relay and
    # the Docker API. Every other module stays free of network clients, and
    # the launcher itself still must not read a provider credential.
    launcher = Path("adaptivehoneypotenv/deployment.py")
    # The send path is the only module that may import httpx or touch
    # os.environ for the provider key. Contract modules name that variable;
    # they do not read it.
    send_path = Path("adaptivehoneypotenv/models/adapter.py")
    key_name_sites = {
        send_path,
        Path("adaptivehoneypotenv/contracts/limits.py"),
        Path("adaptivehoneypotenv/contracts/manifest.py"),
    }
    send_path_only = {"import httpx", "from httpx", "os.environ"}
    provider_reads = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "getenv(")
    # Both stdlib spellings, plus ``from http.client import``. The loopback
    # bridge client may use them. The launcher is already outside this scan
    # because it opens the relay. Every other module, including the adapter,
    # still may not.
    http_client_spellings = (
        "import http.client",
        "from http import client",
        "from http.client import",
    )
    bridge = Path("adaptivehoneypotenv/gateway/upstream.py")
    assert "os.environ.get(PROVIDER_CREDENTIAL_ENV_VAR)" in send_path.read_text(encoding="utf-8")
    for path in Path("adaptivehoneypotenv").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path == launcher:
            for banned in provider_reads:
                assert banned not in text, f"{path} contains {banned}"
            continue
        for banned in banned_imports:
            if path == send_path and banned in send_path_only:
                continue
            assert banned not in text, f"{path} contains {banned}"
        if path != bridge:
            for banned in http_client_spellings:
                assert banned not in text, f"{path} contains {banned}"
        if path not in key_name_sites:
            for banned in provider_reads:
                assert banned not in text, f"{path} contains {banned}"
