# sandboxtown_v2/core/stability_rules.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Tuple, Union, overload

from .agent_state import AgentState, AgentStatus
from .environment_policy import EnvironmentState  # adjust if needed


# -----------------------------
# Transition Events + Result
# -----------------------------

class TransitionEvent(str, Enum):
    ENTER_HELP = "ENTER_HELP"
    EXIT_HELP = "EXIT_HELP"
    ENTER_REST = "ENTER_REST"
    EXIT_REST = "EXIT_REST"
    RECOVERED_TO_STABLE = "RECOVERED_TO_STABLE"
    ENV_DOWNSHIFT = "ENV_DOWNSHIFT"
    ENV_UPSHIFT = "ENV_UPSHIFT"


@dataclass(frozen=True)
class TransitionResult:
    next_status: AgentStatus
    events: Tuple[TransitionEvent, ...] = ()

    @property
    def event(self) -> Optional[TransitionEvent]:
        # Tests are using `.event` in places.
        return self.events[0] if self.events else None


# -----------------------------
# Thresholds
# -----------------------------

@dataclass(frozen=True)
class Thresholds:
    help_enter: float
    help_exit: float
    rest_enter: float
    rest_exit: float
    visual_min_stable: float

    def __post_init__(self) -> None:
        # numeric checks
        for k, v in {
            "help_enter": self.help_enter,
            "help_exit": self.help_exit,
            "rest_enter": self.rest_enter,
            "rest_exit": self.rest_exit,
            "visual_min_stable": self.visual_min_stable,
        }.items():
            if not isinstance(v, (int, float)):
                raise TypeError(f"{k} must be a number")

        # visual min stable must always be valid
        if not (0.0 <= float(self.visual_min_stable) <= 1.0):
            raise ValueError("visual_min_stable must be within [0,1]")

        # Help can be "disabled" by setting BOTH help_enter and help_exit < 0
        # (your tests do this with -1.0)
        help_disabled = (self.help_enter < 0.0 and self.help_exit < 0.0)

        # Rest can stay strict (tests expect in-range)
        if not (0.0 <= self.rest_enter <= 1.0 and 0.0 <= self.rest_exit <= 1.0):
            raise ValueError("All threshold values must be within [0,1]")

        if not (self.rest_enter < self.rest_exit):
            raise ValueError("rest_enter must be < rest_exit")

        # When help is enabled, keep it strict too
        if not help_disabled:
            if not (0.0 <= self.help_enter <= 1.0 and 0.0 <= self.help_exit <= 1.0):
                raise ValueError("All threshold values must be within [0,1]")
            if not (self.help_enter < self.help_exit):
                raise ValueError("help_enter must be < help_exit")


def _help_enabled(th: Thresholds) -> bool:
    return not (th.help_enter < 0.0 and th.help_exit < 0.0)


def _rest_enabled(th: Thresholds) -> bool:
    return True


# -----------------------------
# Core Logic
# -----------------------------

def is_unstable_state(state: AgentState) -> bool:
    return state != AgentState.STABLE


def next_agent_status(a: AgentStatus, thresholds: Thresholds) -> TransitionResult:
    s = a.state
    x = float(a.stability)

    help_on = _help_enabled(thresholds)
    rest_on = _rest_enabled(thresholds)

    # 1) HELP is the highest priority + sticky once entered
    if s == AgentState.HELP_SEEKING and help_on:
        if x >= thresholds.help_exit:
            return TransitionResult(
                AgentStatus(AgentState.RECOVERED, x),
                (TransitionEvent.EXIT_HELP,),
            )
        return TransitionResult(AgentStatus(AgentState.HELP_SEEKING, x), ())

    # 2) ENTER HELP pre-empts everything (even REST)
    if help_on and x <= thresholds.help_enter:
        return TransitionResult(
            AgentStatus(AgentState.HELP_SEEKING, x),
            (TransitionEvent.ENTER_HELP,),
        )

    # 3) REST is sticky once entered (but below HELP in priority)
    if s == AgentState.REST and rest_on:
        if x >= thresholds.rest_exit:
            return TransitionResult(
                AgentStatus(AgentState.RECOVERED, x),
                (TransitionEvent.EXIT_REST,),
            )
        return TransitionResult(AgentStatus(AgentState.REST, x), ())

    # 4) ENTER REST (strict <, exact threshold does NOT enter)
    if rest_on and x < thresholds.rest_enter:
        return TransitionResult(
            AgentStatus(AgentState.REST, x),
            (TransitionEvent.ENTER_REST,),
        )

    # 5) RECOVERED -> STABLE gate
    if s == AgentState.RECOVERED and x >= thresholds.visual_min_stable:
        return TransitionResult(
            AgentStatus(AgentState.STABLE, x),
            (TransitionEvent.RECOVERED_TO_STABLE,),
        )

    # 6) LOADED can become STABLE when stable enough
    if s == AgentState.LOADED and x >= thresholds.visual_min_stable:
        return TransitionResult(AgentStatus(AgentState.STABLE, x), ())

    return TransitionResult(AgentStatus(s, x), ())

# -----------------------------
# Environment Policy Helpers
# -----------------------------
# IMPORTANT: tests call these positionally.

def environment_downshift_if_needed(
    env: EnvironmentState,
    any_agent_unstable: bool,
) -> Tuple[EnvironmentState, Optional[TransitionEvent]]:
    if env == EnvironmentState.DENSE and any_agent_unstable:
        return (EnvironmentState.CALM, TransitionEvent.ENV_DOWNSHIFT)
    return (env, None)


def environment_upshift_if_needed(
    env: EnvironmentState,
    all_agents_stable: bool,
) -> Tuple[EnvironmentState, Optional[TransitionEvent]]:
    if env == EnvironmentState.CALM and all_agents_stable:
        return (EnvironmentState.DENSE, TransitionEvent.ENV_UPSHIFT)
    return (env, None)


# -----------------------------
# apply_rules (required by simulation_runner)
# -----------------------------

@overload
def apply_rules(
    agent_statuses: AgentStatus,
    env: EnvironmentState,
    thresholds: Thresholds,
) -> Tuple[AgentStatus, EnvironmentState]: ...


@overload
def apply_rules(
    agent_statuses: Iterable[AgentStatus],
    env: EnvironmentState,
    thresholds: Thresholds,
) -> Tuple[List[AgentStatus], EnvironmentState]: ...


def apply_rules(
    agent_statuses: Union[AgentStatus, Iterable[AgentStatus]],
    env: EnvironmentState,
    thresholds: Thresholds,
) -> Tuple[Union[AgentStatus, List[AgentStatus]], EnvironmentState]:
    """
    Key behavior:
    - If caller passes a single AgentStatus, return a single AgentStatus.
      (This fixes: 'list' object has no attribute 'state' in simulation_runner.)
    - If caller passes iterable/list, return list.
    """
    single_in = isinstance(agent_statuses, AgentStatus)

    current: List[AgentStatus]
    if single_in:
        current = [agent_statuses]  # type: ignore[list-item]
    else:
        current = list(agent_statuses)  # type: ignore[arg-type]

    any_unstable = any(is_unstable_state(s.state) for s in current)
    all_stable = all(s.state == AgentState.STABLE for s in current)

    # downshift priority
    env2, _ = environment_downshift_if_needed(env, any_unstable)

    # upshift only if no downshift happened
    if env2 == env:
        env2, _ = environment_upshift_if_needed(env2, all_stable)

    next_statuses: List[AgentStatus] = []
    for st in current:
        r = next_agent_status(st, thresholds)
        next_statuses.append(r.next_status)

    if single_in:
        return (next_statuses[0], env2)
    return (next_statuses, env2)
