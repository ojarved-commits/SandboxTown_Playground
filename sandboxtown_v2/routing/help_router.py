from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

from ..core.agent_state import AgentState, AgentStatus


class HelpRoute(str, Enum):
    ENVIRONMENT = "Environment"
    PEER = "Peer"
    SUPERVISOR = "Supervisor"
    NONE = "None"


@dataclass(frozen=True)
class HelpDecision:
    route: HelpRoute
    help_available: bool
    event: str | None = None  # e.g. HELP_ROUTED_ENV, HELP_UNAVAILABLE


def route_help(status: AgentStatus, peer_available: bool = False, supervisor_available: bool = False) -> HelpDecision:
    """
    Non-dominating routing order:
      1) Environment
      2) Peer (optional, stub)
      3) Supervisor (circuit breaker only, stub)
    If nothing available, return NONE.
    """
    if status.state != AgentState.HELP_SEEKING:
        return HelpDecision(HelpRoute.NONE, help_available=False)

    # Environment help is assumed available in v2 baseline (can be toggled for tests)
    return HelpDecision(HelpRoute.ENVIRONMENT, help_available=True, event="HELP_ROUTED_ENV")
