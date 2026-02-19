import pytest
from sandboxtown_v2.core.stability_rules import Thresholds


def test_thresholds_reject_non_numeric():
    with pytest.raises(TypeError):
        Thresholds(
            help_enter="bad",
            help_exit=0.4,
            rest_enter=0.3,
            rest_exit=0.2,
            visual_min_stable=0.5,
        )


def test_visual_min_stable_out_of_bounds_low():
    with pytest.raises(ValueError):
        Thresholds(
            help_enter=0.6,
            help_exit=0.4,
            rest_enter=0.3,
            rest_exit=0.2,
            visual_min_stable=-0.1,
        )


def test_visual_min_stable_out_of_bounds_high():
    with pytest.raises(ValueError):
        Thresholds(
            help_enter=0.6,
            help_exit=0.4,
            rest_enter=0.3,
            rest_exit=0.2,
            visual_min_stable=1.5,
        )
