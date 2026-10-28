"""Live OpenRouter adapter. The scripted test double is a different type."""

from adaptivehoneypotenv.models.adapter import OpenAICompatibleAdapter, open_adapter
from adaptivehoneypotenv.models.errors import (
    CostCapExceeded,
    MissingProviderCredential,
    ModelAdapterError,
    ProviderRequestError,
    ProviderTransportExhausted,
    ScriptedAdapterRejected,
    TeamGeneratedTokenBudgetExhausted,
)
from adaptivehoneypotenv.models.parsing import AttackerTurn, DefenderTurn

__all__ = [
    "AttackerTurn",
    "CostCapExceeded",
    "DefenderTurn",
    "MissingProviderCredential",
    "ModelAdapterError",
    "OpenAICompatibleAdapter",
    "ProviderRequestError",
    "ProviderTransportExhausted",
    "ScriptedAdapterRejected",
    "TeamGeneratedTokenBudgetExhausted",
    "open_adapter",
]
