"""
SandboxTown v2 Core Public API

This module exposes the stable public surface for:
- State transitions (hysteresis)
- Threshold definitions
- Environment regulation

Internal modules (stability_rules, hysteresis, etc.)
are implementation details and should not be imported directly
outside core or tests.
"""

from .agent_state import AgentState, AgentStatus
from .environment_state import EnvironmentState
from .stability_rules import (
    Thresholds,
    TransitionResult,
    next_agent_status,
    environment_downshift_if_needed,
)

__all__ = [
    "AgentState",
    "AgentStatus",
    "EnvironmentState",
    "Thresholds",
    "TransitionResult",
    "next_agent_status",
    "environment_downshift_if_needed",
]
