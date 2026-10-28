"""Attacker tool gateway.

The trusted controller executes the seven DESIGN §6 tools through
``ToolGateway``. Searches and reads hit the episode workspace. Service
calls go to a fixed-upstream bridge. The team messageboard is attacker-only.
"""

from adaptivehoneypotenv.gateway.budget import TokenCharge
from adaptivehoneypotenv.gateway.gateway import ToolDelivery, ToolGateway
from adaptivehoneypotenv.gateway.messageboard import Messageboard, PostedMessage
from adaptivehoneypotenv.gateway.upstream import (
    FixedUpstream,
    LoopbackFixedUpstream,
    UpstreamExchangeError,
    UpstreamResponse,
)

__all__ = [
    "FixedUpstream",
    "LoopbackFixedUpstream",
    "Messageboard",
    "PostedMessage",
    "TokenCharge",
    "ToolDelivery",
    "ToolGateway",
    "UpstreamExchangeError",
    "UpstreamResponse",
]
