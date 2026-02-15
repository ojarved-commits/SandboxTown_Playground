import pytest

from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.stability_rules import Thresholds, next_agent_status


def th():
    # Use explicit thresholds here so this file is self-contained and predictable.
    return Thresholds(
        help_enter=0.30,
        help_exit=0.35,
        rest_enter=0.60,
        rest_exit=0.65,
        visual_min_stable=0.80,
    )


def th_disable_help():
    # Helpful for testing REST behavior without HELP stealing the transition.
    return Thresholds(
        help_enter=-1.0,   # impossible to go below, so HELP never enters
        help_exit=-1.0,
        rest_enter=0.60,
        rest_exit=0.65,
        visual_min_stable=0.80,
    )


def test_help_overrides_rest_floor_when_already_in_help():
    """
    Your machine: if already HELP_SEEKING, it stays HELP until help_exit is crossed.
    Even if stability is very low (< rest_enter), it does NOT switch to REST.
    """
    r = next_agent_status(AgentStatus(AgentState.HELP_SEEKING, 0.27), th())
    assert r.next_status.state == AgentState.HELP_SEEKING


def test_rest_can_be_preempted_by_help_if_below_help_enter():
    """
    Your machine checks 'enter HELP' before 'enter REST'.
    So if stability <= help_enter, you enter HELP even if stability is also < rest_enter.
    """
    r = next_agent_status(AgentStatus(AgentState.REST, 0.29), th())
    assert r.next_status.state == AgentState.HELP_SEEKING


def test_rest_exit_only_at_rest_exit_when_help_disabled():
    """
    With HELP disabled, we can cleanly test REST hysteresis:
    - stay REST while < rest_exit
    - exit REST only when >= rest_exit -> RECOVERED
    """
    thresholds = th_disable_help()

    # still in REST when below rest_exit
    r1 = next_agent_status(AgentStatus(AgentState.REST, 0.64), thresholds)
    assert r1.next_status.state == AgentState.REST

    # exit REST only when we cross rest_exit
    r2 = next_agent_status(AgentStatus(AgentState.REST, 0.65), thresholds)
    assert r2.next_status.state == AgentState.RECOVERED
