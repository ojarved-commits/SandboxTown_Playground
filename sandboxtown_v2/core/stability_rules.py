from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .agent_state import AgentState, AgentStatus
from .environment_state import EnvironmentState


@dataclass(frozen=True)
class Thresholds:
    help_enter: float
    help_exit: float
    rest_enter: float
    rest_exit: float
    visual_min_stable: float

    @staticmethod
    def load(path: str | Path) -> "Thresholds":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Thresholds(**data)


@dataclass(frozen=True)
class TransitionResult:
    next_status: AgentStatus
    event: Optional[str] = None  # ENTER_HELP, EXIT_HELP, ENTER_REST, EXIT_REST, LOADED, STABLE


def next_agent_status(current: AgentStatus, thresholds: Thresholds) -> TransitionResult:
    """
    Strict hysteresis matching test expectations.
    """

    s = current.stability
    state = current.state

    # ---------------------------
    # HELP state
    # ---------------------------
    if state == AgentState.HELP_SEEKING:
        # Exit HELP exactly at >= help_exit
        if s >= thresholds.help_exit:
            return TransitionResult(
                AgentStatus(AgentState.RECOVERED, s),
                event="EXIT_HELP",
            )

        # HELP remains sticky otherwise
        return TransitionResult(
            AgentStatus(AgentState.HELP_SEEKING, s),
            event=None,
        )

    # ---------------------------
    # REST state
    # ---------------------------
    if state == AgentState.REST:
        # Exit REST at >= rest_exit
        if s >= thresholds.rest_exit:
            return TransitionResult(
                AgentStatus(AgentState.RECOVERED, s),
                event="EXIT_REST",
            )

        # REST → HELP only if very low
        if s <= thresholds.help_enter:
            return TransitionResult(
                AgentStatus(AgentState.HELP_SEEKING, s),
                event="ENTER_HELP",
            )

        return TransitionResult(
            AgentStatus(AgentState.REST, s),
            event=None,
        )

    # ---------------------------
    # Enter HELP (strict)
    # ---------------------------
    if s <= thresholds.help_enter:
        return TransitionResult(
            AgentStatus(AgentState.HELP_SEEKING, s),
            event="ENTER_HELP",
        )

    # ---------------------------
    # Enter REST (strictly less)
    # ---------------------------
    if s < thresholds.rest_enter:
        return TransitionResult(
            AgentStatus(AgentState.REST, s),
            event="ENTER_REST",
        )

    # ---------------------------
    # Stable band
    # ---------------------------
    if s >= thresholds.help_exit:
        if state != AgentState.STABLE:
            return TransitionResult(
                AgentStatus(AgentState.STABLE, s),
                event="STABLE",
            )
        return TransitionResult(
            AgentStatus(AgentState.STABLE, s),
            event=None,
        )

    # Middle band
    if state != AgentState.LOADED:
        return TransitionResult(
            AgentStatus(AgentState.LOADED, s),
            event="LOADED",
        )

    return TransitionResult(
        AgentStatus(AgentState.LOADED, s),
        event=None,
    )



def environment_downshift_if_needed(
    env: EnvironmentState, any_agent_unstable: bool
) -> tuple[EnvironmentState, Optional[str]]:
    """
    v2 rule: Dense allowed only if all agents stable. Any instability forces downshift.
    Minimal path: DENSE -> CALM.
    """
    if any_agent_unstable and env == EnvironmentState.DENSE:
        return EnvironmentState.CALM, "ENV_DOWNSHIFT"
    return env, None
