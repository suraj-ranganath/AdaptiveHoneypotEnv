"""One opt-in live OpenRouter call.

Refuses to run unless ``ADAPTIVEHONEYPOT_SMOKE_LIVE=1``. CI must not set that
flag. This module does not call the provider on import.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from adaptivehoneypotenv.contracts.limits import DEFAULT_MODEL, OPENROUTER_BASE_URL
from adaptivehoneypotenv.contracts.manifest import load_demo_profile
from adaptivehoneypotenv.model_api import ChatCompletionRequest, ChatMessage
from adaptivehoneypotenv.models.adapter import OpenAICompatibleAdapter, controller_setting
from adaptivehoneypotenv.models.config import AdapterConfig
from adaptivehoneypotenv.models.redact import redact_text


def main() -> int:
    if controller_setting("ADAPTIVEHONEYPOT_SMOKE_LIVE") != "1":
        print("refusing live call: set ADAPTIVEHONEYPOT_SMOKE_LIVE=1", file=sys.stderr)
        return 2
    try:
        return _one_call()
    except Exception as exc:
        print(redact_text(str(exc)), file=sys.stderr)
        return 1


def _demo_path() -> Path:
    override = controller_setting("ADAPTIVEHONEYPOT_DEMO_PROFILE")
    if override:
        return Path(override)
    cwd = Path.cwd() / "demo.yaml"
    if cwd.is_file():
        return cwd
    return Path(__file__).resolve().parents[2] / "demo.yaml"


def _one_call() -> int:
    profile = load_demo_profile(_demo_path())
    ledger_dir = Path(tempfile.mkdtemp(prefix="adaptivehoneypotenv-smoke-"))
    config = AdapterConfig(
        cap_usd=profile.runtime.max_cost_usd,
        ledger_path=ledger_dir / "spend.json",
        model=profile.attacker.model,
        base_url=OPENROUTER_BASE_URL,
        attacker_max_tokens=16,
        defender_max_tokens=16,
        attacker_timeout_seconds=30,
        defender_timeout_seconds=30,
        attacker_per_call_cap=16,
        defender_per_call_cap=16,
        temperature=0,
    )
    if config.model != DEFAULT_MODEL:
        print("demo model is not the pinned model", file=sys.stderr)
        return 1
    adapter = OpenAICompatibleAdapter(config)
    result = adapter.complete(
        ChatCompletionRequest(
            model=config.model,
            messages=(ChatMessage(role="user", content="Reply with the single word pong."),),
            max_tokens=1,
            temperature=0,
        )
    )
    summary = {
        "adapter_id": adapter.adapter_id,
        "model": config.model,
        "finish_reason": result.finish_reason.value,
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "refusal": result.refusal is not None,
        "spent_usd": format(adapter.spent_usd(), "f"),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
