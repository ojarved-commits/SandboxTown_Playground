from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.stability_rules import Thresholds, next_agent_status


def th():
    return Thresholds(help_enter=0.60, help_exit=0.65, rest_enter=0.30, rest_exit=0.40, visual_min_stable=0.65)


def test_help_enter():
    r = next_agent_status(AgentStatus(AgentState.STABLE, 0.58), th())
    assert r.next_status.state == AgentState.HELP_SEEKING


def test_help_exit_to_recovered():
    r = next_agent_status(AgentStatus(AgentState.HELP_SEEKING, 0.66), th())
    assert r.next_status.state == AgentState.RECOVERED
