# sandboxtown_v2/tests/test_hysteresis.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional

import pytest

from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.hysteresis import next_agent_status, Thresholds


def th() -> Thresholds:
    # Default thresholds used across tests
    return Thresholds(
        help_enter=0.30,
        help_exit=0.35,
        rest_enter=0.60,
        rest_exit=0.65,
        visual_min_stable=0.80,
    )


def step(state: AgentState, stability: float) -> AgentStatus:
    return AgentStatus(state=state, stability=stability)


def run_sequence(
    start_state: AgentState,
    stabilities: List[float],
    thresholds: Thresholds,
) -> List[Tuple[AgentState, Optional[str]]]:
    """
    Returns a per-step list of (state, event) after applying next_agent_status.
    """
    cur = step(start_state, stabilities[0])
    out: List[Tuple[AgentState, Optional[str]]] = []

    for s in stabilities:
        cur = AgentStatus(state=cur.state, stability=s)
        res = next_agent_status(cur, thresholds)
        cur = res.next_status
        out.append((cur.state, res.event))

    return out


# ============================================================
# Existing baseline tests (keep / extend as needed)
# ============================================================

def test_help_hysteresis_sequence():
    """
    Dip below help_enter, hover below help_exit, then recover above help_exit.
    Verify HELP_SEEKING appears and doesn't exit until we cross help_exit.
    """
    thresholds = th()

    seq = [0.40, 0.31, 0.29, 0.32, 0.34, 0.36, 0.40]
    timeline = run_sequence(AgentState.STABLE, seq, thresholds)
    states = [s for (s, _) in timeline]

    assert AgentState.HELP_SEEKING in states

    idx = states.index(AgentState.HELP_SEEKING)
    # once we enter HELP at 0.29, we should still be in HELP at 0.32 and 0.34
    if idx + 2 < len(states):
        assert states[idx + 1] == AgentState.HELP_SEEKING
        assert states[idx + 2] == AgentState.HELP_SEEKING

    # after 0.36+ we should be out of HELP (we don't force which non-HELP state)
    assert states[-1] != AgentState.HELP_SEEKING


def test_help_exit_event_only_fires_once():
    """
    After EXIT_HELP, further steps should not keep emitting EXIT_HELP unless you re-enter HELP again.
    """
    thresholds = th()
    timeline = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.29, 0.35, 0.36, 0.40],
        thresholds=thresholds,
    )
    events = [e for (_, e) in timeline]

    # First step enters help
    assert "ENTER_HELP" in events
    # Exit should happen once when we cross >= help_exit
    assert events.count("EXIT_HELP") == 1
    # After exit, no more EXIT_HELP
    exit_i = events.index("EXIT_HELP")
    assert all(ev != "EXIT_HELP" for ev in events[exit_i + 1:])


# ============================================================
# B) Boundary precision tests
# ============================================================

def test_boundary_help_enter_exactly_enters_help():
    thresholds = th()
    timeline = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.40, thresholds.help_enter],
        thresholds=thresholds,
    )
    # At exactly help_enter, we expect HELP to enter (your code uses <=)
    assert timeline[-1][0] == AgentState.HELP_SEEKING
    assert timeline[-1][1] == "ENTER_HELP"


def test_boundary_help_exit_exactly_exits_help():
    thresholds = th()
    timeline = run_sequence(
        start_state=AgentState.HELP_SEEKING,
        stabilities=[0.34, thresholds.help_exit],
        thresholds=thresholds,
    )
    # At exactly help_exit, we expect HELP to exit (your code uses >=)
    assert timeline[-1][0] != AgentState.HELP_SEEKING
    assert timeline[-1][1] == "EXIT_HELP"


def test_boundary_rest_enter_exactly_does_not_enter_rest():
    thresholds = th()
    timeline = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.80, thresholds.rest_enter],
        thresholds=thresholds,
    )
    # REST triggers only when s < rest_enter (strict)
    assert timeline[-1][0] != AgentState.REST
    assert timeline[-1][1] is None


def test_boundary_rest_enter_just_below_enters_rest():
    thresholds = th()
    eps = 1e-6
    timeline = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.80, thresholds.rest_enter - eps],
        thresholds=thresholds,
    )
    assert timeline[-1][0] == AgentState.REST
    assert timeline[-1][1] == "ENTER_REST"


def test_boundary_rest_exit_exactly_exits_rest():
    thresholds = th()
    timeline = run_sequence(
        start_state=AgentState.REST,
        stabilities=[0.64, thresholds.rest_exit],
        thresholds=thresholds,
    )
    assert timeline[-1][0] != AgentState.REST
    assert timeline[-1][1] == "EXIT_REST"


# ============================================================
# A) REST symmetry tests (mirrors HELP suite)
# ============================================================

def test_rest_overrides_everything_even_if_help_seeking():
    thresholds = th()
    # In HELP, but stability drops below rest_enter -> REST must win
    timeline = run_sequence(
        start_state=AgentState.HELP_SEEKING,
        stabilities=[0.40, 0.59],  # 0.59 < 0.60 => REST
        thresholds=thresholds,
    )
    assert timeline[-1][0] == AgentState.REST
    assert timeline[-1][1] == "ENTER_REST"


def test_rest_exit_event_only_fires_once():
    thresholds = th()
    timeline = run_sequence(
        start_state=AgentState.REST,
        stabilities=[0.62, 0.65, 0.66, 0.80],
        thresholds=thresholds,
    )
    events = [e for (_, e) in timeline]
    assert events.count("EXIT_REST") == 1
    exit_i = events.index("EXIT_REST")
    assert all(ev != "EXIT_REST" for ev in events[exit_i + 1:])


def test_rest_does_not_exit_until_crossing_rest_exit():
    thresholds = th()
    # Hover below rest_exit should stay REST, then cross and exit.
    timeline = run_sequence(
        start_state=AgentState.REST,
        stabilities=[0.60, 0.64, 0.649, 0.65],
        thresholds=thresholds,
    )
    states = [s for (s, _) in timeline]
    # first 3 should still be REST
    assert states[0] == AgentState.REST
    assert states[1] == AgentState.REST
    assert states[2] == AgentState.REST
    # final should exit REST
    assert states[3] != AgentState.REST
    assert timeline[3][1] == "EXIT_REST"


def test_rest_can_reenter_after_exiting_if_stability_drops_again():
    thresholds = th()
    eps = 1e-6
    timeline = run_sequence(
        start_state=AgentState.REST,
        stabilities=[
            0.65,  # exit rest
            0.80,  # stable-ish
            thresholds.rest_enter - eps,  # drop -> re-enter rest
        ],
        thresholds=thresholds,
    )
    states = [s for (s, _) in timeline]
    events = [e for (_, e) in timeline]

    assert "EXIT_REST" in events
    assert states[-1] == AgentState.REST
    assert events[-1] == "ENTER_REST"
