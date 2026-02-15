from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .agent_state import AgentState
from .environment_state import EnvironmentState


@dataclass(frozen=True)
class ContagionConfig:
    """
    Minimal deterministic contagion (Spec-Only, Canon-safe):
    - If any agent is in an "unstable source" state, it reduces the stability inputs
      of OTHER agents on this timestep (pre-transition).
    - Deterministic, no randomness.
    """
    enabled: bool = True

    # Base stability reduction per unstable source agent (per step)
    delta: float = 0.05

    # Cap for total reduction applied to a target in one step
    max_total_delta: float = 0.30

    # Environment scaling:
    # - DENSE amplifies contagion
    # - CALM dampens contagion
    dense_scale: float = 1.0
    calm_scale: float = 0.5

    # Which states count as "contagion sources"
    source_states: tuple[AgentState, ...] = (AgentState.HELP_SEEKING, AgentState.REST)

    # If True, only agents currently STABLE can be affected
    only_affects_stable: bool = False


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def apply_contagion(
    *,
    raw_stabilities: Sequence[float],
    current_states: Sequence[AgentState],
    env: EnvironmentState,
    cfg: ContagionConfig,
) -> List[float]:
    """
    Apply contagion to stability inputs BEFORE next_agent_status() evaluation.

    Rule:
      total_influence = min(cfg.max_total_delta, cfg.delta * num_sources * env_scale)
      For each i:
        - if current_states[i] is a source -> unchanged
        - else stability_i = clamp01(raw - total_influence)
        - optional gating: only_affects_stable
    """
    if not cfg.enabled:
        return list(raw_stabilities)

    if len(raw_stabilities) != len(current_states):
        raise ValueError("raw_stabilities and current_states must be the same length.")

    num_sources = sum(1 for s in current_states if s in cfg.source_states)
    if num_sources == 0:
        return list(raw_stabilities)

    env_scale = cfg.dense_scale if env == EnvironmentState.DENSE else cfg.calm_scale
    total_influence = cfg.delta * float(num_sources) * env_scale
    if total_influence > cfg.max_total_delta:
        total_influence = cfg.max_total_delta

    out: List[float] = []
    for raw, st in zip(raw_stabilities, current_states):
        # Sources don't get destabilized by their own broadcast (keeps it simple + deterministic)
        if st in cfg.source_states:
            out.append(_clamp01(float(raw)))
            continue

        if cfg.only_affects_stable and st != AgentState.STABLE:
            out.append(_clamp01(float(raw)))
            continue

        out.append(_clamp01(float(raw) - total_influence))

    return out
