import pytest
from sandboxtown_v2.core.stability_rules import Thresholds


def test_thresholds_constructor_edges_cover_validation():
    # If those lines are validation, hit both valid and invalid.
    Thresholds(
        help_enter=0.30,
        help_exit=0.40,
        rest_enter=0.20,
        rest_exit=0.35,
        visual_min_stable=0.75,
    )

    # Common invalid case: enter >= exit or out of [0,1]
    with pytest.raises(ValueError):
        Thresholds(
            help_enter=0.50,
            help_exit=0.40,   # invalid ordering
            rest_enter=0.20,
            rest_exit=0.35,
            visual_min_stable=0.75,
        )
