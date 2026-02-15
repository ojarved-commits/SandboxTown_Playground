# src/policy.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class VariantPolicy:
    # --- Environment knobs ---
    enable_transition: bool = True
    park_delta_scale: float = 1.0
    rest_delta_scale: float = 1.0

    # --- Species rest rules ---
    fantail_allow_rest: bool = True   # Agent A (Fantail)
    sparrow_allow_rest: bool = True   # Agent D (Sparrow)

    # --- Profile IDs (inputs to get_profile()) ---
    A_profile_id: str = "fish"       # Fantail
    B_profile_id: str = "ant_fast"   # Kiwi fast
    C_profile_id: str = "ant_slow"   # Kiwi slow
    D_profile_id: str = "bird"       # Sparrow

    # Optional run tag for telemetry filename
    run_tag: Optional[str] = None


def get_policy(variant: str) -> VariantPolicy:
    v = (variant or "BASE").strip().upper()

    # BASE
    if v == "BASE":
        return VariantPolicy(run_tag="base")

    # B1: remove transition zone
    if v == "B1_NO_TRANSITION":
        return VariantPolicy(enable_transition=False, run_tag="b1_no_transition")

    # B2: stronger park effects (environment only)
    if v == "B2_MORE_PARK":
        return VariantPolicy(park_delta_scale=1.25, run_tag="b2_more_park")

    # B3: Fantail cannot rest
    if v == "B3_FISH_NO_REST":
        return VariantPolicy(fantail_allow_rest=False, run_tag="b3_fish_no_rest")

    # P1: Rest scarcity (rest exists but weaker)
    if v == "P1_REST_SCARCITY":
        return VariantPolicy(rest_delta_scale=0.40, run_tag="p1_rest_scarcity")

    # P2A: Sparrow runs ant engine (ant_fast), keeps Sparrow identity (ID/color)
    if v == "P2A_SPARROW_ANT_ENGINE":
        return VariantPolicy(D_profile_id="ant_fast", run_tag="p2a_sparrow_ant_engine")

    # P2B: Fantail runs ant engine (ant_slow)
    if v == "P2B_FANTAIL_ANT_ENGINE":
        return VariantPolicy(A_profile_id="ant_slow", run_tag="p2b_fantail_ant_engine")

    # Unknown variant: safe fallback (still tagged)
    return VariantPolicy(run_tag=v.lower())
