import pytest

from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.stability_rules import Thresholds, next_agent_status


def test_threshold_hysteresis_sequence():
    thresholds = Thresholds(
        help_enter=0.30,
        help_exit=0.35,
        rest_enter=0.60,
        rest_exit=0.65,
        visual_min_stable=0.80,
    )

    # Start in a non-rest state (LOADED is a safe default from your enum list)
    status = AgentStatus(state=AgentState.LOADED, stability=0.0)

    # Values hovering around rest_enter/rest_exit band
    sequence = [0.59, 0.61, 0.58, 0.62, 0.60, 0.59, 0.61, 0.66, 0.64, 0.62]

    states = []
    for value in sequence:
        status = AgentStatus(state=status.state, stability=value)
        result = next_agent_status(status, thresholds)
        status = result.next_status
        states.append(status.state)

    # We should see REST at least once (crossing rest_enter)
    assert AgentState.REST in states

    # We should also see at least one NON-REST state somewhere in the run
    assert any(s != AgentState.REST for s in states)

    # Optional: basic “no frantic flip-flop” check (hysteresis sanity)
    flips = sum(1 for a, b in zip(states, states[1:]) if a != b)
    assert flips <= 6
