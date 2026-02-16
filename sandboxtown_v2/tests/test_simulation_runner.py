from sandboxtown_v2.core import AgentState, AgentStatus
from sandboxtown_v2.core.simulation_runner import run_simulation
from sandboxtown_v2.core.stability_rules import Thresholds


def th():
    return Thresholds(
        help_enter=0.30,
        help_exit=0.40,
        rest_enter=0.20,
        rest_exit=0.35,
        visual_min_stable=0.75,
    )


def test_simple_help_cycle():
    start = AgentStatus(AgentState.LOADED, 0.5)

    steps = run_simulation(
        start,
        stabilities=[0.25, 0.28, 0.45],
        thresholds=th(),
    )

    assert steps[0].status.state == AgentState.HELP_SEEKING
    assert steps[0].event == "ENTER_HELP"

    assert steps[-1].event == "EXIT_HELP"
