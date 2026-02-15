from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

from .agent_state import AgentState, AgentStatus
from .stability_rules import Thresholds


class Mode(str, Enum):
    HEADLESS = "Headless"
    VISUAL = "Visual"


@dataclass(frozen=True)
class ModeResult:
    mode: Mode
    event: str | None = None  # e.g. EXIT_VISUAL_TO_HEADLESS


def enforce_mode(current_mode: Mode, status: AgentStatus, thresholds: Thresholds) -> ModeResult:
    """
    v2 rule: Visual only allowed when Stable and stability >= visual_min_stable.
    If not, force Headless.
    """
    if current_mode == Mode.VISUAL:
        if not (status.state == AgentState.STABLE and status.stability >= thresholds.visual_min_stable):
            return ModeResult(Mode.HEADLESS, event="EXIT_VISUAL_TO_HEADLESS")
    return ModeResult(current_mode)
