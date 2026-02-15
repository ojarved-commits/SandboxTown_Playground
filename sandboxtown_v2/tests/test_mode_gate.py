import pytest

from sandboxtown_v2.core.mode_gate import enforce_mode, Mode
from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.stability_rules import Thresholds


def make_status(state: AgentState, stability: float) -> AgentStatus:
    return AgentStatus(state=state, stability=stability)


def make_thresholds(min_stable: float) -> Thresholds:
    # These extra fields are required by Thresholds.__init__ in your core.
    # Values here are just sensible defaults for tests; tune later if needed.
    return Thresholds(
        visual_min_stable=min_stable,
        help_enter=0.3,
        help_exit=0.5,
        rest_enter=0.2,
        rest_exit=0.4,
    )


def test_visual_forced_to_headless_when_not_stable_state():
    # Visual is only allowed when state == STABLE and stability >= visual_min_stable
    status = make_status(AgentState.LOADED, stability=0.9)  # not STABLE
    thresholds = make_thresholds(min_stable=0.5)

    result = enforce_mode(Mode.VISUAL, status, thresholds)

    assert result.mode == Mode.HEADLESS
    assert result.event == "EXIT_VISUAL_TO_HEADLESS"


def test_visual_forced_to_headless_when_stability_too_low():
    status = make_status(AgentState.STABLE, stability=0.2)  # below min
    thresholds = make_thresholds(min_stable=0.5)

    result = enforce_mode(Mode.VISUAL, status, thresholds)

    assert result.mode == Mode.HEADLESS
    assert result.event == "EXIT_VISUAL_TO_HEADLESS"


def test_visual_allowed_when_stable_and_high_enough():
    status = make_status(AgentState.STABLE, stability=0.9)  # above min
    thresholds = make_thresholds(min_stable=0.5)

    result = enforce_mode(Mode.VISUAL, status, thresholds)

    assert result.mode == Mode.VISUAL
    assert result.event is None


def test_headless_mode_unchanged():
    # If already headless, enforce_mode should not change it (based on your current core logic).
    status = make_status(AgentState.STABLE, stability=0.9)
    thresholds = make_thresholds(min_stable=0.5)

    result = enforce_mode(Mode.HEADLESS, status, thresholds)

    assert result.mode == Mode.HEADLESS
    assert result.event is None
