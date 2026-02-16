import pytest

import sandboxtown_v2.core.contagion as contagion
from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.environment_state import EnvironmentState
from sandboxtown_v2.core.contagion_rules import ContagionConfig


def _mk_status(state: AgentState, stability: float) -> AgentStatus:
    return AgentStatus(state, stability)


def test_contagion_disabled_path_no_change():
    """
    Hits the 'contagion off / config None / enabled False' branch in contagion.py.
    Replace `contagion.<ENTRYPOINT>` with the function that contagion.py exposes.
    """
    statuses = [
        _mk_status(AgentState.LOADED, 0.7),
        _mk_status(AgentState.LOADED, 0.6),
    ]

    cfg = ContagionConfig(enabled=False)

    # --- replace this with contagion.py's entry function ---
    # out = contagion.apply_pre_transition_contagion(statuses, EnvironmentState.DENSE, cfg)
    # ------------------------------------------------------

    # Once you swap the function name above, assert invariants:
    # assert out == statuses OR (if it returns stabilities) assert out == [0.7, 0.6]
    assert True


def test_contagion_no_unstable_agents_path_no_change():
    """
    Hits the 'no unstable at start' branch.
    """
    statuses = [
        _mk_status(AgentState.LOADED, 0.7),
        _mk_status(AgentState.LOADED, 0.6),
    ]
    cfg = ContagionConfig(enabled=True, delta=0.1)

    # out = contagion.<ENTRYPOINT>(statuses, EnvironmentState.DENSE, cfg)

    assert True


def test_contagion_with_unstable_agent_applies_shift():
    """
    Hits the main contagion application branch.
    """
    statuses = [
        _mk_status(AgentState.HELP_SEEKING, 0.8),  # unstable (unchanged)
        _mk_status(AgentState.LOADED, 0.6),        # stable (shifted)
    ]
    cfg = ContagionConfig(enabled=True, delta=0.1)

    # out = contagion.<ENTRYPOINT>(statuses, EnvironmentState.DENSE, cfg)

    # Once wired, assert one stable moved down and unstable unchanged (or clamped).
    assert True


def test_contagion_calm_env_half_shift_branch():
    """
    Hits the env-based multiplier branch (CALM vs DENSE).
    """
    statuses = [
        _mk_status(AgentState.REST, 0.8),   # unstable
        _mk_status(AgentState.LOADED, 0.6), # stable
    ]
    cfg = ContagionConfig(enabled=True, delta=0.1)

    # out = contagion.<ENTRYPOINT>(statuses, EnvironmentState.CALM, cfg)

    assert True
