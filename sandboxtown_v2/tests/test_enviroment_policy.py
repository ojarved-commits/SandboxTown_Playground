from sandboxtown_v2.core import EnvironmentState
from sandboxtown_v2.core.environment_policy import EnvironmentPolicy


def test_dense_downshifts_when_unstable():
    policy = EnvironmentPolicy()

    new_env, event = policy.apply(
        EnvironmentState.DENSE,
        any_agent_unstable=True,
    )

    assert new_env == EnvironmentState.CALM
    assert event == "ENV_DOWNSHIFT"


def test_dense_stays_when_all_stable():
    policy = EnvironmentPolicy()

    new_env, event = policy.apply(
        EnvironmentState.DENSE,
        any_agent_unstable=False,
    )

    assert new_env == EnvironmentState.DENSE
    assert event is None
