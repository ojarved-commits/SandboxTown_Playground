from sandboxtown_v2.core import (
    AgentState,
    AgentStatus,
    Thresholds,
    next_agent_status,
)


def th():
    return Thresholds(
        help_enter=0.30,
        help_exit=0.50,
        rest_enter=0.20,
        rest_exit=0.40,
        visual_min_stable=0.70,
    )


def test_help_sticky_below_exit():
    thresholds = th()
    status = AgentStatus(AgentState.HELP_SEEKING, 0.31)

    result = next_agent_status(status, thresholds)

    assert result.next_status.state == AgentState.HELP_SEEKING
    assert result.event is None


def test_no_double_events():
    thresholds = th()
    status = AgentStatus(AgentState.STABLE, 0.60)

    result = next_agent_status(status, thresholds)

    # event must be single or None
    assert result.event is None or isinstance(result.event, str)


def test_event_only_when_state_changes():
    thresholds = th()
    status = AgentStatus(AgentState.STABLE, 0.75)

    result = next_agent_status(status, thresholds)

    if result.event is None:
        assert result.next_status.state == AgentState.STABLE
