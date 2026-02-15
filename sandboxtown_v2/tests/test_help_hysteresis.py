# sandboxtown_v2/tests/test_help_hysteresis.py
from __future__ import annotations

from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.hysteresis import Thresholds, next_agent_status


def th() -> Thresholds:
    # Keep REST well below our HELP test values so it cannot interfere
    return Thresholds(
        help_enter=0.30,
        help_exit=0.35,
        rest_enter=0.20,
        rest_exit=0.25,
        visual_min_stable=0.80,
    )


def run_sequence(start_state: AgentState, stabilities: list[float]) -> list[tuple[AgentState, str | None]]:
    """
    Returns [(state_after_step, event), ...] for each stability input.
    """
    t = th()
    status = AgentStatus(state=start_state, stability=stabilities[0])
    out: list[tuple[AgentState, str | None]] = []

    for s in stabilities:
        status = AgentStatus(state=status.state, stability=s)
        r = next_agent_status(status, t)
        status = r.next_status
        out.append((status.state, r.event))

    return out


def test_help_enters_once_and_holds_until_help_exit():
    """
    Dip below help_enter => ENTER_HELP.
    Hover below help_exit => remain HELP with no exit.
    Cross help_exit => EXIT_HELP exactly at that boundary.
    """
    seq = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.40, 0.29, 0.34, 0.349, 0.35],
    )

    # Must enter HELP at first dip
    assert seq[1] == (AgentState.HELP_SEEKING, "ENTER_HELP")

    # Must remain HELP while < help_exit (no EXIT_HELP yet)
    assert seq[2][0] == AgentState.HELP_SEEKING and seq[2][1] is None
    assert seq[3][0] == AgentState.HELP_SEEKING and seq[3][1] is None

    # Exit exactly when >= help_exit
    assert seq[4][1] == "EXIT_HELP"


def test_help_exit_event_only_fires_once_then_never_repeats_above_exit():
    """
    After EXIT_HELP, further steps above help_exit must NOT emit EXIT_HELP again.
    (It may emit other events like STABLE depending on your band mapping.)
    """
    seq = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.40, 0.29, 0.35, 0.36, 0.40, 0.38],
    )

    events = [e for _, e in seq]

    assert events.count("ENTER_HELP") == 1
    assert events.count("EXIT_HELP") == 1

    # Everything after the EXIT_HELP step must not be EXIT_HELP
    exit_idx = events.index("EXIT_HELP")
    assert all(e != "EXIT_HELP" for e in events[exit_idx + 1 :])


def test_help_can_reenter_after_exit_when_dipping_below_help_enter_again():
    """
    Enter HELP -> Exit HELP -> later dip again -> ENTER_HELP again.
    """
    seq = run_sequence(
        start_state=AgentState.STABLE,
        stabilities=[0.40, 0.29, 0.35, 0.40, 0.29],
    )

    events = [e for _, e in seq]
    assert events.count("ENTER_HELP") == 2
    assert events.count("EXIT_HELP") == 1
    assert seq[-1][0] == AgentState.HELP_SEEKING  # last dip should put us back in HELP


def test_help_jitter_near_exit_does_not_exit_early():
    """
    While HELP_SEEKING, values just below help_exit must NOT exit.
    Only >= help_exit exits.
    """
    t = th()

    status = AgentStatus(state=AgentState.HELP_SEEKING, stability=0.34)
    r1 = next_agent_status(status, t)
    assert r1.next_status.state == AgentState.HELP_SEEKING
    assert r1.event is None

    status = AgentStatus(state=r1.next_status.state, stability=0.3499)
    r2 = next_agent_status(status, t)
    assert r2.next_status.state == AgentState.HELP_SEEKING
    assert r2.event is None

    status = AgentStatus(state=r2.next_status.state, stability=0.35)
    r3 = next_agent_status(status, t)
    assert r3.event == "EXIT_HELP"
