from sandboxtown_v2.core import AgentState, AgentStatus, EnvironmentState
from sandboxtown_v2.core.multi_agent_simulation import run_multi_agent_simulation
from sandboxtown_v2.core.stability_rules import Thresholds


def th():
    return Thresholds(
        help_enter=0.30,
        help_exit=0.40,
        rest_enter=0.20,
        rest_exit=0.35,
        visual_min_stable=0.75,
    )


def test_environment_upshifts_when_all_stable():
    agents = [
        AgentStatus(AgentState.STABLE, 0.9),
        AgentStatus(AgentState.STABLE, 0.9),
    ]

    sequences = [
        [0.9],
        [0.9],
    ]

    steps = run_multi_agent_simulation(
        agents,
        sequences,
        thresholds=th(),
        start_environment=EnvironmentState.CALM,
    )

    assert steps[0].environment == EnvironmentState.DENSE
    assert steps[0].env_event == "ENV_UPSHIFT"
