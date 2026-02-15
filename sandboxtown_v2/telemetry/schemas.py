from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ..core.agent_state import AgentState


@dataclass(frozen=True)
class TelemetryRecord:
    t: int
    state: AgentState
    stability: float
    mode: str  # "Headless" or "Visual"
    event: Optional[str] = None
