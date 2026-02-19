import pytest

from sandboxtown_v2.core.contagion import apply_contagion, ContagionConfig
from sandboxtown_v2.core.agent_state import AgentState
from sandboxtown_v2.core.environment_state import EnvironmentState


def test_contagion_length_mismatch_raises():
    cfg = ContagionConfig(enabled=True)

    with pytest.raises(ValueError):
        apply_contagion(
            raw_stabilities=[0.5],
            current_states=[AgentState.STABLE, AgentState.STABLE],
            env=EnvironmentState.CALM,
            cfg=cfg,
        )

def test_contagion_only_affects_stable_blocks_non_stable():
    cfg = ContagionConfig(
        enabled=True,
        delta=0.2,
        max_total_delta=1.0,
        dense_scale=1.0,
        calm_scale=1.0,
        source_states={AgentState.HELP_SEEKING},
        only_affects_stable=True,
    )

    raw = [0.8, 0.8]
    states = [AgentState.HELP_SEEKING, AgentState.REST]

    out = apply_contagion(
        raw_stabilities=raw,
        current_states=states,
        env=EnvironmentState.CALM,
        cfg=cfg,
    )

    # UNSTABLE is source → unchanged
    assert out[0] == pytest.approx(0.8)

    # RESTING should NOT be affected because only_affects_stable=True
    assert out[1] == pytest.approx(0.8)

