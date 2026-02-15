import pytest

from sandboxtown_v2.core.mode_gate import (
    enforce_mode,
    Mode,
)
from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.stability_rules import Thresholds


def make_status(state, stability):
    return AgentStatus(state=state, stability=stability)


def make_threshold(min_stable):
    return Thresholds(visual_min_stable=min_stable)


def test_visual_forced_to_headless_when_unstable():
    status = make_status(AgentState.UNSTABLE, stability=0.9)
    thresholds = make_threshold(min_stable=0.5)

    result = enforce_mode(Mode.VISUAL, status, thresholds)

    assert result.mode == Mode.HEADLESS
    assert result.event == "EXIT_VISUAL_TO_HEADLESS"


def test_visual_forced_when_stability_too_low():
    status = make_status(AgentState.STABLE, stability=0.2)
    thresholds = make_threshold(min_stable=0.5)

    result = enforce_mode(Mode.VISUAL, status, thresholds)

    assert result.mode == Mode.HEADLESS
    assert result.event == "EXIT_VISUAL_TO_HEADLESS"


def test_visual_allowed_when_stable_and_high_enough():
    status = make_status(AgentState.STABLE, stability=0.9)
    thresholds = make_threshold(min_stable=0.5)

    result = enforce_mode(Mode.VISUAL, status, thresholds)

    assert result.mode == Mode.VISUAL
    assert result.event is None


def test_headless_mode_unchanged():
    status = make_status(AgentState.STABLE, stability=0.9)
    thresholds = make_threshold(min_stable=0.5)

    result = enforce_mode(Mode.HEADLESS, status, thresholds)

    assert result.mode == Mode.HEADLESS
    assert result.event is None
