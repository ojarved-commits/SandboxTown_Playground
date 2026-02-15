from sandboxtown_v2.core.environment_state import EnvironmentState
from sandboxtown_v2.core.stability_rules import environment_downshift_if_needed


def test_dense_downshifts_on_instability():
    env, ev = environment_downshift_if_needed(EnvironmentState.DENSE, any_agent_unstable=True)
    assert env == EnvironmentState.CALM
    assert ev == "ENV_DOWNSHIFT"
