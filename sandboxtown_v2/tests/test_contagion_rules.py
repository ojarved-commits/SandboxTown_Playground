# sandboxtown_v2/tests/test_contagion_rules.py

import pytest

from sandboxtown_v2.core.agent_state import AgentState
from sandboxtown_v2.core.contagion_rules import (
    ContagionConfig,
    apply_contagion,
    is_unstable_state,
    _clamp,
)
from sandboxtown_v2.core.environment_state import EnvironmentState


def test_is_unstable_state_flags_help_and_rest_only():
    assert is_unstable_state(AgentState.HELP_SEEKING) is True
    assert is_unstable_state(AgentState.REST) is True

    # everything else should be stable (adjust if you add more "unstable" states later)
    assert is_unstable_state(AgentState.LOADED) is False


def test_apply_contagion_disabled_returns_raw_unchanged_object_identity():
    raw = [0.5, 0.6]
    states = [AgentState.LOADED, AgentState.HELP_SEEKING]
    cfg = ContagionConfig(enabled=False)

    out = apply_contagion(raw, states, EnvironmentState.DENSE, cfg)

    # spec says "unchanged" when disabled; current impl returns the same list object
    assert out is raw
    assert out == [0.5, 0.6]


def test_apply_contagion_no_unstable_agents_returns_raw_unchanged_object_identity():
    raw = [0.5, 0.6, 0.7]
    states = [AgentState.LOADED, AgentState.LOADED, AgentState.LOADED]
    cfg = ContagionConfig(enabled=True, delta=0.05)

    out = apply_contagion(raw, states, EnvironmentState.DENSE, cfg)

    # current impl returns raw list directly when no unstable agents exist
    assert out is raw
    assert out == [0.5, 0.6, 0.7]


def test_dense_environment_applies_full_shift_to_stable_agents_only():
    raw = [0.8, 0.6]
    states = [AgentState.HELP_SEEKING, AgentState.LOADED]
    cfg = ContagionConfig(delta=0.1, dense_multiplier=1.0, calm_multiplier=0.5)

    out = apply_contagion(raw, states, EnvironmentState.DENSE, cfg)

    # unstable agent unchanged (but clamped)
    assert out[0] == pytest.approx(0.8)
    # stable agent shifted by full delta
    assert out[1] == pytest.approx(0.5)


def test_calm_environment_applies_half_shift_to_stable_agents_only():
    raw = [0.8, 0.6]
    states = [AgentState.REST, AgentState.LOADED]  # REST is also unstable
    cfg = ContagionConfig(delta=0.1, dense_multiplier=1.0, calm_multiplier=0.5)

    out = apply_contagion(raw, states, EnvironmentState.CALM, cfg)

    # unstable agent unchanged (but clamped)
    assert out[0] == pytest.approx(0.8)
    # stable agent shifted by half delta
    assert out[1] == pytest.approx(0.55)


def test_apply_contagion_clamps_shifted_values_to_min_max():
    # stable agent goes below clamp_min after shift => clamp to 0.0
    raw = [0.2, 0.02]
    states = [AgentState.HELP_SEEKING, AgentState.LOADED]
    cfg = ContagionConfig(delta=0.1, clamp_min=0.0, clamp_max=1.0)

    out = apply_contagion(raw, states, EnvironmentState.DENSE, cfg)

    assert out[0] == pytest.approx(0.2)  # unstable unchanged
    assert out[1] == pytest.approx(0.0)  # clamped


def test_apply_contagion_clamps_unstable_agent_input_too():
    # unstable agent input is > clamp_max => should clamp even though "unchanged"
    raw = [1.2, 0.6]
    states = [AgentState.HELP_SEEKING, AgentState.LOADED]
    cfg = ContagionConfig(delta=0.1, clamp_min=0.0, clamp_max=1.0)

    out = apply_contagion(raw, states, EnvironmentState.DENSE, cfg)

    assert out[0] == pytest.approx(1.0)  # clamped
    assert out[1] == pytest.approx(0.5)  # shifted


def test__clamp_behavior_min_max_and_in_range():
    assert _clamp(-1.0, 0.0, 1.0) == pytest.approx(0.0)
    assert _clamp(2.0, 0.0, 1.0) == pytest.approx(1.0)
    assert _clamp(0.25, 0.0, 1.0) == pytest.approx(0.25)
