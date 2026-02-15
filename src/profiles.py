# src/profiles.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MotionProfile:
    name: str
    model: str  # "fish" or "ant"

    # common
    dt_clamp: float = 0.05
    soft_edge_margin: int = 35

    # ant params
    base_speed: float = 70.0
    crawl_speed_min: float = 12.0
    lerp_alpha: float = 0.08
    wander_mix: float = 0.25

    commit_min: int = 120
    commit_max: int = 260
    inside_zone_retarget_p: float = 0.035
    orbit_impulse_p: float = 0.020
    orbit_strength_x: int = 30
    orbit_strength_y: int = 16

    dwell_ramp_rate: float = 0.0035
    dwell_ramp_cap: float = 2.0
    hysteresis_eps: float = 0.08

    edge_pause_ticks: int = 14
    edge_pause_cooldown: int = 22
    trail_move_eps: float = 2.5

    # fish params
    fish_base_speed: float = 95.0
    fish_turn_rate: float = 6.5
    fish_pause_min_s: float = 0.10
    fish_pause_max_s: float = 0.55
    fish_commit_p: float = 0.035
    fish_commit_min: int = 180
    fish_commit_max: int = 360
    fish_commit_cooldown_min: int = 90
    fish_commit_cooldown_max: int = 200
    fish_min_dwell_ticks: int = 45
    fish_exit_lock_ticks: int = 18


# ---- Default profiles (IDs you already use) ----
FISH_PROFILE = MotionProfile(
    name="FANTAIL",
    model="fish",
    dt_clamp=0.05,
    soft_edge_margin=35,
    fish_base_speed=105.0,
    fish_turn_rate=6.5,
    fish_pause_min_s=0.12,
    fish_pause_max_s=0.60,
    fish_commit_p=0.040,
    fish_commit_min=180,
    fish_commit_max=380,
    fish_commit_cooldown_min=90,
    fish_commit_cooldown_max=220,
    fish_min_dwell_ticks=45,
    fish_exit_lock_ticks=18,
)
BIRD_PROFILE = MotionProfile(
    name="SPARROW",
    model="fish",
    dt_clamp=0.05,
    soft_edge_margin=35,

    fish_base_speed=90.0,
    fish_turn_rate=7.0,

    # curious sampler: less dwell lock + more commits
    fish_pause_min_s=0.04,
    fish_pause_max_s=0.20,

    fish_commit_p=0.055,         # more commits = more “missions”
    fish_commit_min=80,
    fish_commit_max=180,
    fish_commit_cooldown_min=30,
    fish_commit_cooldown_max=80,

    fish_min_dwell_ticks=16,     # key: leaves sooner = more exploration
    fish_exit_lock_ticks=10,
)
ANT_FAST_PROFILE = MotionProfile(
    name="KIWI_FAST",
    model="ant",
    dt_clamp=0.05,
    soft_edge_margin=35,
    base_speed=90.0,
    crawl_speed_min=14.0,
    lerp_alpha=0.10,
    wander_mix=0.28,
    commit_min=90,
    commit_max=180,
    inside_zone_retarget_p=0.050,
    orbit_impulse_p=0.022,
    orbit_strength_x=34,
    orbit_strength_y=18,
    dwell_ramp_rate=0.0045,
    dwell_ramp_cap=2.2,
    hysteresis_eps=0.08,
    edge_pause_ticks=12,
    edge_pause_cooldown=18,
    trail_move_eps=2.4,
)

ANT_SLOW_PROFILE = MotionProfile(
    name="KIWI_SLOW",
    model="ant",
    dt_clamp=0.05,
    soft_edge_margin=35,
    base_speed=60.0,
    crawl_speed_min=10.0,
    lerp_alpha=0.08,
    wander_mix=0.24,
    commit_min=120,
    commit_max=260,
    inside_zone_retarget_p=0.040,
    orbit_impulse_p=0.018,
    orbit_strength_x=28,
    orbit_strength_y=14,
    dwell_ramp_rate=0.0035,
    dwell_ramp_cap=2.0,
    hysteresis_eps=0.08,
    edge_pause_ticks=14,
    edge_pause_cooldown=22,
    trail_move_eps=2.6,
)


def get_profile(profile_id: str) -> MotionProfile:
    pid = (profile_id or "").strip().lower()
    if pid == "fish":
        return FISH_PROFILE
    if pid == "bird":
        return BIRD_PROFILE
    if pid == "ant_fast":
        return ANT_FAST_PROFILE
    if pid == "ant_slow":
        return ANT_SLOW_PROFILE
    raise ValueError(f"Unknown profile id: {profile_id!r}")
