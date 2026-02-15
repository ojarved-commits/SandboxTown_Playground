from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .agent_state import AgentState
from .environment_state import EnvironmentState


@dataclass(frozen=True)
class ContagionConfig:
    """
    Simple contagion v1:
      - If any agent is unstable at the *start* of a step (HELP_SEEKING or REST),
        other agents get a small stability downshift before transition evaluation.
      - Environment scales effect: DENSE = full, CALM = half.
      - Completely optional: if None or enabled=False, engine behavior is unchanged.
    """
    enabled: bool = True
    delta: float = 0.05  # how much stability to subtract from non-unstable agents
    dense_multiplier: float = 1.0
    calm_multiplier: float = 0.5
    clamp_min: float = 0.0
    clamp_max: float = 1.0


def is_unstable_state(state: AgentState) -> bool:
    return state in (AgentState.HELP_SEEKING, AgentState.REST)


def apply_contagion(
    raw_stabilities: List[float],
    current_states: List[AgentState],
    env: EnvironmentState,
    cfg: ContagionConfig,
) -> List[float]:
    """
    Apply a simple global contagion: if any agent is unstable,
    reduce stability of agents who are NOT unstable.
    """
    if not cfg.enabled:
        return raw_stabilities

    any_unstable = any(is_unstable_state(s) for s in current_states)
    if not any_unstable:
        return raw_stabilities

    multiplier = cfg.dense_multiplier if env == EnvironmentState.DENSE else cfg.calm_multiplier
    shift = cfg.delta * multiplier

    out: List[float] = []
    for s, st in zip(raw_stabilities, current_states):
        if is_unstable_state(st):
            # unstable agents keep their raw stability input unchanged (v1 rule)
            out.append(_clamp(s, cfg.clamp_min, cfg.clamp_max))
        else:
            out.append(_clamp(s - shift, cfg.clamp_min, cfg.clamp_max))
    return out


def _clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
