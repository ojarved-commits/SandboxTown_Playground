# sandboxtown_v2/core/hysteresis.py
from __future__ import annotations

"""
Public import shim.

Tests and callers can import:
    from sandboxtown_v2.core.hysteresis import next_agent_status

But the implementation lives in:
    sandboxtown_v2.core.stability_rules
"""

from .stability_rules import (  # noqa: F401
    Thresholds,
    TransitionResult,
    next_agent_status,
    environment_downshift_if_needed,
)

__all__ = [
    "Thresholds",
    "TransitionResult",
    "next_agent_status",
    "environment_downshift_if_needed",
]
