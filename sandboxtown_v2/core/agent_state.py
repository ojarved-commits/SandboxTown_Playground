from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class AgentState(str, Enum):
    STABLE = "Stable"
    LOADED = "Loaded"
    HELP_SEEKING = "Help-Seeking"
    REST = "Rest"
    RECOVERED = "Recovered"


@dataclass(frozen=True)
class AgentStatus:
    state: AgentState
    stability: float  # 0.0 .. 1.0
