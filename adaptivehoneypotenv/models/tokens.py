"""Team generated-token budget hook.

The 24,000 token budget is an attacker task limit. Defender calls do not
use this function and do not consume the budget. The cap for one of ``k``
parallel attacker calls is the frozen rule in
``per_call_generated_token_cap``.
"""

from __future__ import annotations

from adaptivehoneypotenv.contracts.limits import TEAM_GENERATED_TOKEN_BUDGET
from adaptivehoneypotenv.contracts.transition import per_call_generated_token_cap


def attacker_call_token_cap(
    *,
    per_call_cap: int,
    remaining_team_tokens: int,
    parallel_calls: int,
) -> int:
    """Maximum generated tokens for one attacker call in a lockstep round.

    Returns 0 when the remaining team budget cannot fund a positive share.
    The caller must not send that call. A zero result is task exhaustion,
    not a cost cutoff and not a defender win.
    """

    if remaining_team_tokens == 0:
        return 0
    if remaining_team_tokens > TEAM_GENERATED_TOKEN_BUDGET:
        raise ValueError("remaining team tokens are outside the task budget")
    return per_call_generated_token_cap(
        per_call_cap=per_call_cap,
        remaining_team_tokens=remaining_team_tokens,
        parallel_calls=parallel_calls,
    )
