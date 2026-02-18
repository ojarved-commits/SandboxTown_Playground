import pytest

from sandboxtown_v2.core.agent_state import AgentState, AgentStatus
from sandboxtown_v2.core.environment_policy import EnvironmentState
from sandboxtown_v2.core.stability_rules import (
    Thresholds,
    TransitionEvent,
    is_unstable_state,
    environment_downshift_if_needed,
    environment_upshift_if_needed,
)

# NOTE:
# There's a function in stability_rules.py that contains:
#   single_in = isinstance(agent_statuses, AgentStatus)
# and returns either a single AgentStatus or a list plus env.
# Import it here once you confirm its exact name.
#
# Example (rename as needed):
# from sandboxtown_v2.core.stability_rules import apply_environment_policy
#
# Then uncomment the tests in the last section.


# -------------------------
# Thresholds validation
# -------------------------

def test_thresholds_rejects_non_numeric_values():
    # hits: "must be a number" branch
    with pytest.raises(TypeError):
        Thresholds(
            visual_min_stable="0.5",  # not numeric
            help_enter=0.3,
            help_exit=0.5,
            rest_enter=0.2,
            rest_exit=0.4,
        )

def test_thresholds_rejects_visual_min_stable_out_of_range_low():
    with pytest.raises(ValueError):
        Thresholds(
            visual_min_stable=-0.01,
            help_enter=0.3,
            help_exit=0.5,
            rest_enter=0.2,
            rest_exit=0.4,
        )

def test_thresholds_rejects_visual_min_stable_out_of_range_high():
    with pytest.raises(ValueError):
        Thresholds(
            visual_min_stable=1.01,
            help_enter=0.3,
            help_exit=0.5,
            rest_enter=0.2,
            rest_exit=0.4,
        )

def test_thresholds_rejects_rest_thresholds_out_of_range():
    # hits: "All threshold values must be within [0,1]" (rest strict path)
    with pytest.raises(ValueError):
        Thresholds(
            visual_min_stable=0.5,
            help_enter=0.3,
            help_exit=0.5,
            rest_enter=-0.1,
            rest_exit=0.4,
        )

def test_thresholds_rejects_rest_enter_not_less_than_exit():
    # hits: "rest_enter must be < rest_exit"
    with pytest.raises(ValueError):
        Thresholds(
            visual_min_stable=0.5,
            help_enter=0.3,
            help_exit=0.5,
            rest_enter=0.4,
            rest_exit=0.4,
        )

def test_thresholds_rejects_help_thresholds_out_of_range_when_enabled():
    # help enabled means help thresholds must be in [0,1]
    with pytest.raises(ValueError):
        Thresholds(
            visual_min_stable=0.5,
            help_enter=0.3,
            help_exit=1.5,  # out of range
            rest_enter=0.2,
            rest_exit=0.4,
        )

def test_thresholds_rejects_help_enter_not_less_than_exit_when_enabled():
    # hits: "help_enter must be < help_exit"
    with pytest.raises(ValueError):
        Thresholds(
            visual_min_stable=0.5,
            help_enter=0.6,
            help_exit=0.6,
            rest_enter=0.2,
            rest_exit=0.4,
        )

def test_thresholds_allows_help_disabled_but_rest_still_strict():
    # help disabled via both < 0.0 should bypass help strict checks
    # but rest still must be valid and ordered
    th = Thresholds(
        visual_min_stable=0.5,
        help_enter=-1.0,
        help_exit=-1.0,
        rest_enter=0.2,
        rest_exit=0.4,
    )
    assert th.help_enter < 0.0 and th.help_exit < 0.0


# -------------------------
# is_unstable_state coverage
# -------------------------

def test_is_unstable_state_true_for_non_stable_states():
    assert is_unstable_state(AgentState.LOADED) is True
    # add others if you want, but one non-stable already hits the branch

def test_is_unstable_state_false_for_stable():
    assert is_unstable_state(AgentState.STABLE) is False


# -------------------------
# Environment policy helpers coverage
# -------------------------

def test_environment_downshift_triggers_when_dense_and_any_unstable():
    env2, ev = environment_downshift_if_needed(EnvironmentState.DENSE, True)
    assert env2 == EnvironmentState.CALM
    assert ev == TransitionEvent.ENV_DOWNSHIFT

def test_environment_downshift_noop_when_not_dense():
    env2, ev = environment_downshift_if_needed(EnvironmentState.CALM, True)
    assert env2 == EnvironmentState.CALM
    assert ev is None

def test_environment_downshift_noop_when_no_unstable_agents():
    env2, ev = environment_downshift_if_needed(EnvironmentState.DENSE, False)
    assert env2 == EnvironmentState.DENSE
    assert ev is None

def test_environment_upshift_triggers_when_calm_and_all_stable():
    env2, ev = environment_upshift_if_needed(EnvironmentState.CALM, True)
    assert env2 == EnvironmentState.DENSE
    assert ev == TransitionEvent.ENV_UPSHIFT

def test_environment_upshift_noop_when_not_calm():
    env2, ev = environment_upshift_if_needed(EnvironmentState.DENSE, True)
    assert env2 == EnvironmentState.DENSE
    assert ev is None

def test_environment_upshift_noop_when_not_all_stable():
    env2, ev = environment_upshift_if_needed(EnvironmentState.CALM, False)
    assert env2 == EnvironmentState.CALM
    assert ev is None


# -------------------------
# Single vs list wrapper coverage
# -------------------------
# Uncomment once you confirm the function name inside stability_rules.py
# (the one containing: single_in = isinstance(agent_statuses, AgentStatus))
#
# def test_wrapper_accepts_single_agentstatus_and_returns_single():
#     th = Thresholds(
#         visual_min_stable=0.5,
#         help_enter=-1.0,
#         help_exit=-1.0,
#         rest_enter=0.2,
#         rest_exit=0.4,
#     )
#     a = AgentStatus(state=AgentState.STABLE, stability=0.9)
#     # rename apply_environment_policy to the real function name
#     nxt, env2 = apply_environment_policy(a, th, EnvironmentState.CALM)
#     assert isinstance(nxt, AgentStatus)
#     assert isinstance(env2, EnvironmentState)
#
# def test_wrapper_accepts_list_and_returns_list():
#     th = Thresholds(
#         visual_min_stable=0.5,
#         help_enter=-1.0,
#         help_exit=-1.0,
#         rest_enter=0.2,
#         rest_exit=0.4,
#     )
#     a1 = AgentStatus(state=AgentState.STABLE, stability=0.9)
#     a2 = AgentStatus(state=AgentState.LOADED, stability=0.2)
#     nxt_list, env2 = apply_environment_policy([a1, a2], th, EnvironmentState.DENSE)
#     assert isinstance(nxt_list, list)
#     assert len(nxt_list) == 2
#     assert isinstance(env2, EnvironmentState)
