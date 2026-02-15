from dataclasses import dataclass
from typing import Dict


@dataclass
class MotionProfile:
    name: str
    model: str  # "ant" or "fish"

    # --- shared ---
    base_speed: float
    crawl_speed_min: float
    lerp_alpha: float
    dt_clamp: float = 0.045
    soft_edge_margin: int = 35

    # --- ant-style (also used by bird) ---
    wander_mix: float = 0.0
    inside_zone_retarget_p: float = 0.0
    orbit_impulse_p: float = 0.0
    orbit_strength_x: int = 0
    orbit_strength_y: int = 0

    commit_min: int = 40
    commit_max: int = 90

    edge_pause_ticks: int = 10
    edge_pause_cooldown: int = 18

    dwell_ramp_rate: float = 1 / 240.0
    dwell_ramp_cap: float = 2.5
    hysteresis_eps: float = 0.12
    trail_move_eps: float = 2.5

    # --- fish only ---
    fish_base_speed: float = 160.0
    fish_turn_rate: float = 10.0

    fish_pause_min_s: float = 0.06
    fish_pause_max_s: float = 0.22

    fish_min_dwell_ticks: int = 18
    fish_exit_lock_ticks: int = 14

    fish_commit_p: float = 0.012
    fish_commit_min: int = 40
    fish_commit_max: int = 90
    fish_commit_cooldown_min: int = 25
    fish_commit_cooldown_max: int = 60


# =========================
# ANT PROFILES
# =========================
ANT_FAST = MotionProfile(
    name="ANT_FAST",
    model="ant",
    base_speed=110.0,
    crawl_speed_min=32.0,
    lerp_alpha=0.10,
    wander_mix=0.45,
    inside_zone_retarget_p=0.08,
    orbit_impulse_p=0.05,
    orbit_strength_x=90,
    orbit_strength_y=60,
    commit_min=40,
    commit_max=85,
    edge_pause_ticks=8,
    edge_pause_cooldown=16,
    dwell_ramp_rate=1 / 220.0,
    dwell_ramp_cap=2.6,
    hysteresis_eps=0.10,
)

ANT_SLOW = MotionProfile(
    name="ANT_SLOW",
    model="ant",
    base_speed=70.0,
    crawl_speed_min=28.0,
    lerp_alpha=0.06,
    wander_mix=0.65,
    inside_zone_retarget_p=0.04,
    orbit_impulse_p=0.02,
    orbit_strength_x=70,
    orbit_strength_y=45,
    commit_min=65,
    commit_max=110,
    edge_pause_ticks=14,
    edge_pause_cooldown=28,
    dwell_ramp_rate=1 / 320.0,
    dwell_ramp_cap=2.0,
    hysteresis_eps=0.14,
)

# =========================
# FISH PROFILE
# =========================
FISH_AQUARIUM = MotionProfile(
    name="FISH_AQUARIUM",
    model="fish",
    base_speed=0.0,
    crawl_speed_min=0.0,
    lerp_alpha=0.0,
    fish_base_speed=160.0,
    fish_turn_rate=10.0,
    fish_pause_min_s=0.06,
    fish_pause_max_s=0.22,
    fish_min_dwell_ticks=18,
    fish_exit_lock_ticks=14,
    fish_commit_p=0.012,
    fish_commit_min=40,
    fish_commit_max=90,
    fish_commit_cooldown_min=25,
    fish_commit_cooldown_max=60,
)

# =========================
# 🕊️ BIRD (fish-like glide, still ant engine)
# =========================
BIRD_GLIDE = MotionProfile(
    name="BIRD_GLIDE",
    model="ant",                # IMPORTANT: stays on ant engine
    base_speed=135.0,
    crawl_speed_min=42.0,

    # fish-like smoothness
    lerp_alpha=0.028,           # key: glide turns
    wander_mix=0.55,            # drift (not twitch)
    inside_zone_retarget_p=0.02,

    # low orbit jitter (no ant jitter)
    orbit_impulse_p=0.018,
    orbit_strength_x=110,
    orbit_strength_y=80,

    # longer commits = calmer “swim/soar”
    commit_min=120,
    commit_max=220,

    # perching/observing pauses
    edge_pause_ticks=26,
    edge_pause_cooldown=55,

    # gentle dwell ramp
    dwell_ramp_rate=1 / 520.0,
    dwell_ramp_cap=1.7,
    hysteresis_eps=0.20,
    trail_move_eps=2.8,
)

# =========================
# REGISTRY
# =========================
PROFILES: Dict[str, MotionProfile] = {
    "ant_fast": ANT_FAST,
    "ant_slow": ANT_SLOW,
    "fish": FISH_AQUARIUM,
    "bird": BIRD_GLIDE,
}


def get_profile(name: str) -> MotionProfile:
    return PROFILES[name]
