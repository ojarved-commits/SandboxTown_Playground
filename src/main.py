# BASE_v1 (policy passive baseline) — updated with batch runs + policy args
# VERSION: v0.4-stable (policy passive baseline)

# src/main.py
# ORPIN / MOS Sandbox Town — Ecosystem
# Agents:
#   A = Fantail (fish engine)
#   B = Kiwi fast (ant engine)
#   C = Kiwi slow (ant engine)
#   D = Sparrow (bird profile; engine determined by profile.model)

import math
import os
import csv
import random
import argparse
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple, Set, Any

import pygame

from policy_engine import make_policy
from profiles import get_profile, MotionProfile


# =========================
# VARIANT SWITCH (edit this)
# =========================
# "BASE"
# "B1_NO_TRANSITION"
# "B2_MORE_PARK"
# "B3_FISH_NO_REST"
# "P1_REST_SCARCITY"
# "P2A_SPARROW_ANT_COG"  (environment same; sparrow cognition seeded toward Park)
VARIANT = "BASE"


# =========================
# Display / Timing
# =========================
W, H = 980, 560
FPS = 60

BG = (16, 16, 18)
TXT = (235, 235, 235)
SUBTXT = (190, 190, 195)


# =========================
# Colors
# =========================
COLOR_LIBRARY = (45, 140, 215)
COLOR_PARK = (85, 190, 105)
COLOR_TRANSITION = (175, 175, 180)
COLOR_REST = (205, 195, 160)

AGENT_A_COLOR = (210, 255, 230)  # Fantail
AGENT_B_COLOR = (255, 230, 210)  # Kiwi fast
AGENT_C_COLOR = (200, 220, 255)  # Kiwi slow
AGENT_D_COLOR = (255, 255, 200)  # Sparrow


# =========================
# Helpers
# =========================
def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


def safe_normalize(vec: pygame.Vector2) -> pygame.Vector2:
    if vec.length_squared() <= 1e-9:
        return pygame.Vector2(0, 0)
    return vec.normalize()


def v2(x: float, y: float) -> pygame.Vector2:
    return pygame.Vector2(float(x), float(y))


def rounded_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color: Tuple[int, int, int],
    radius: int,
    width: int = 0,
):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


def inner_rect(rect: pygame.Rect, margin: int) -> pygame.Rect:
    r = rect.inflate(-2 * margin, -2 * margin)
    if r.width < 2:
        r.width = 2
    if r.height < 2:
        r.height = 2
    return r


def ensure_telemetry_paths(variant: str, runs: int | None = None) -> str:
    base_dir = r"C:\SandboxTown_Data\telemetry\runs"
    os.makedirs(base_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if runs and runs > 0:
        filename = f"run_{runs}runs_{ts}_{variant.lower()}.csv"
    else:
        filename = f"run_single_{ts}_{variant.lower()}.csv"

    return os.path.join(base_dir, filename)


# =========================
# Data Models
# =========================
@dataclass
class Zone:
    name: str
    rect: pygame.Rect
    deltas: Dict[str, float]
    color: Tuple[int, int, int]
    pause_bias: float = 1.0
    commit_bias: float = 1.0

    def contains(self, pos: pygame.Vector2) -> bool:
        return self.rect.collidepoint(pos.x, pos.y)

    def center(self) -> pygame.Vector2:
        return pygame.Vector2(self.rect.centerx, self.rect.centery)

    def soft_contains(self, pos: pygame.Vector2, margin: int) -> bool:
        return inner_rect(self.rect, margin).collidepoint(pos.x, pos.y)

    def near_edge(self, pos: pygame.Vector2, margin: int) -> bool:
        if not self.contains(pos):
            return False
        return not self.soft_contains(pos, margin)


@dataclass
class AgentState:
    energy: float = 0.70
    load: float = 0.20
    coherence: float = 0.60
    curiosity: float = 0.70


@dataclass
class Agent:
    agent_id: str
    profile: MotionProfile
    pos: pygame.Vector2
    vel: pygame.Vector2
    target: pygame.Vector2

    state: AgentState = field(default_factory=AgentState)

    # --- zone tracking ---
    current_zone: str = "None"
    dwell_ticks: int = 0
    paused: bool = False

    # --- productivity (logged) ---
    work_units: int = 0
    output_score: float = 0.0  # generic “productivity/exploration” scalar

    # policy bundle (attached in run_sim)
    policy: Any = None

    # =====================================
    # ANT FIELDS
    # =====================================
    pause_hold_ticks: int = 0
    pause_cooldown_ticks: int = 0
    commit_zone: Optional[Zone] = None
    commit_ticks: int = 0
    last_choice: str = "None"
    trail: List[pygame.Vector2] = field(default_factory=list)

    # --- exploration metrics (ants) ---
    last_zone_for_metrics: str = "None"
    zone_switches: int = 0
    unique_zone_entries: int = 0
    visited_zones: Set[str] = field(default_factory=set)

    # =====================================
    # FISH FIELDS
    # =====================================
    fish_pause_hold_s: float = 0.0
    fish_pause_cooldown_s: float = 0.0
    fish_edge_pause_latch: bool = False
    fish_leaving_lock_ticks: int = 0

    fish_commit_zone: Optional[str] = None
    fish_commit_ticks_left: int = 0
    fish_commit_cooldown_ticks: int = 0


# =========================
# Zones (variant-safe)
# =========================
def build_zones(variant: str) -> List[Zone]:
    lib_d = {"energy": -0.030, "load": +0.020, "coherence": +0.015, "curiosity": +0.020}
    park_d = {"energy": +0.050, "load": -0.020, "coherence": +0.012, "curiosity": -0.005}
    trans_d = {"energy": -0.010, "load": -0.010, "coherence": +0.006, "curiosity": +0.002}
    rest_d = {"energy": +0.012, "load": -0.018, "coherence": +0.020, "curiosity": -0.004}

    if variant == "B2_MORE_PARK":
        park_d = dict(park_d)
        park_d["energy"] *= 1.25
        park_d["load"] *= 1.15

    if variant == "P1_REST_SCARCITY":
        rest_d = dict(rest_d)
        for k in rest_d:
            rest_d[k] *= 0.40  # rest exists, weaker

    library = Zone("Library", pygame.Rect(110, 190, 280, 260), lib_d, COLOR_LIBRARY, pause_bias=1.15, commit_bias=1.25)
    park = Zone("Park", pygame.Rect(590, 190, 280, 260), park_d, COLOR_PARK, pause_bias=1.05, commit_bias=1.05)
    transition = Zone("Transition", pygame.Rect(420, 285, 160, 90), trans_d, COLOR_TRANSITION, pause_bias=1.30, commit_bias=0.60)
    rest = Zone("Rest", pygame.Rect(430, 395, 140, 70), rest_d, COLOR_REST, pause_bias=1.55, commit_bias=0.55)

    zones = [library, park, transition, rest]

    if variant == "B1_NO_TRANSITION":
        zones = [z for z in zones if z.name != "Transition"]

    return zones


def zone_at(zones: List[Zone], pos: pygame.Vector2) -> Optional[Zone]:
    for z in zones:
        if z.contains(pos):
            return z
    return None


# ✅ pad auto-shrinks for small zones
def pick_point_in_zone(z: Zone, pad: int = 55) -> pygame.Vector2:
    r = z.rect
    max_pad_x = max(2, min(pad, (r.width // 2) - 2))
    max_pad_y = max(2, min(pad, (r.height // 2) - 2))
    x = random.randint(r.left + max_pad_x, r.right - max_pad_x)
    y = random.randint(r.top + max_pad_y, r.bottom - max_pad_y)
    return v2(x, y)


def apply_zone_effects(agent: Agent, z: Optional[Zone], dt: float):
    s = agent.state
    if z is None:
        s.energy = clamp01(s.energy + (-0.006) * dt)
        s.load = clamp01(s.load + (-0.004) * dt)
        s.coherence = clamp01(s.coherence + (+0.002) * dt)
        s.curiosity = clamp01(s.curiosity + (+0.001) * dt)
        return

    s.energy = clamp01(s.energy + z.deltas.get("energy", 0.0) * dt)
    s.load = clamp01(s.load + z.deltas.get("load", 0.0) * dt)
    s.coherence = clamp01(s.coherence + z.deltas.get("coherence", 0.0) * dt)
    s.curiosity = clamp01(s.curiosity + z.deltas.get("curiosity", 0.0) * dt)


# =========================
# ANT ENGINE
# =========================
def dwell_ramp_ant(agent: Agent) -> float:
    p = agent.profile
    return min(p.dwell_ramp_cap, 1.0 + agent.dwell_ticks * p.dwell_ramp_rate)


def soft_edge_factor_ant(z: Zone, pos: pygame.Vector2, margin: int) -> float:
    inner = inner_rect(z.rect, margin)
    if inner.collidepoint(pos.x, pos.y):
        return 1.0

    dx = 0.0
    if pos.x < inner.left:
        dx = inner.left - pos.x
    elif pos.x > inner.right:
        dx = pos.x - inner.right

    dy = 0.0
    if pos.y < inner.top:
        dy = inner.top - pos.y
    elif pos.y > inner.bottom:
        dy = pos.y - inner.bottom

    d = math.hypot(dx, dy)
    if d <= 0:
        return 1.0

    return max(0.0, min(1.0, 1.0 - (d / max(1.0, float(margin)))))


def exposure_factor_ant(z: Zone, pos: pygame.Vector2) -> float:
    if z.name not in ("Transition", "Rest"):
        return 1.0
    cx, cy = z.rect.center
    dx = (pos.x - cx) / max(1.0, z.rect.width / 2)
    dy = (pos.y - cy) / max(1.0, z.rect.height / 2)
    d = math.sqrt(dx * dx + dy * dy)
    return max(0.35, 1.15 - d)


def decide_target_zone_ant(agent: Agent, zones: List[Zone]) -> Zone:
    p = agent.profile
    zmap = {z.name: z for z in zones}
    s = agent.state

    score_park = (1.0 - s.energy) * 1.25 + s.load * 1.20 + (1.0 - s.coherence) * 0.15
    score_lib = s.curiosity * 1.10 + s.coherence * 0.75 - s.load * 0.30
    score_trans = (1.0 - s.coherence) * 1.25 + s.load * 0.35
    score_rest = (1.0 - s.energy) * 0.55 + s.load * 0.85 + (1.0 - s.coherence) * 0.25

    scores: Dict[str, float] = {}
    if "Park" in zmap:
        scores["Park"] = score_park
    if "Library" in zmap:
        scores["Library"] = score_lib
    if "Transition" in zmap:
        scores["Transition"] = score_trans
    if "Rest" in zmap:
        scores["Rest"] = score_rest

    best_name = max(scores.keys(), key=lambda k: scores[k])
    best_score = scores[best_name]

    if agent.last_choice in scores and agent.last_choice in zmap:
        last_score = scores[agent.last_choice]
        if best_name != agent.last_choice and (best_score - last_score) < p.hysteresis_eps:
            best_name = agent.last_choice

    return zmap[best_name]


def edge_pause_check_ant(agent: Agent, prev_zone: Optional[Zone], now_zone: Optional[Zone]):
    p = agent.profile
    if agent.pause_cooldown_ticks > 0:
        agent.pause_cooldown_ticks -= 1
        return

    if (prev_zone is None and now_zone is not None) or (prev_zone is not None and now_zone is None):
        agent.pause_hold_ticks = p.edge_pause_ticks
        agent.pause_cooldown_ticks = p.edge_pause_cooldown
        return

    if prev_zone is None or now_zone is None:
        return

    if prev_zone.name != now_zone.name:
        agent.pause_hold_ticks = p.edge_pause_ticks
        agent.pause_cooldown_ticks = p.edge_pause_cooldown
        return

    if prev_zone.contains(agent.pos) and not prev_zone.soft_contains(agent.pos, p.soft_edge_margin):
        agent.pause_hold_ticks = p.edge_pause_ticks
        agent.pause_cooldown_ticks = p.edge_pause_cooldown


def update_agent_ant(agent: Agent, zones: List[Zone], dt: float):
    p = agent.profile

    if agent.pause_hold_ticks > 0:
        agent.pause_hold_ticks -= 1
        agent.vel *= 0.88
        agent.paused = True
        return
    agent.paused = False

    prev_zone = next((z for z in zones if z.name == agent.current_zone), None) if agent.current_zone != "None" else None
    now_zone = zone_at(zones, agent.pos)
    now_name = now_zone.name if now_zone else "None"

    if now_name == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = now_name
        agent.dwell_ticks = 0

    # --- exploration metrics (ants) ---
    if agent.current_zone != agent.last_zone_for_metrics:
        agent.zone_switches += 1
        if agent.current_zone not in agent.visited_zones:
            agent.visited_zones.add(agent.current_zone)
            agent.unique_zone_entries += 1
        agent.last_zone_for_metrics = agent.current_zone

    # simple exploration score (ant-side)
    agent.output_score = agent.unique_zone_entries * 10 + agent.zone_switches * 2

    edge_pause_check_ant(agent, prev_zone, now_zone)

    if now_zone:
        ramp = dwell_ramp_ant(agent)
        soft = soft_edge_factor_ant(now_zone, agent.pos, p.soft_edge_margin)
        expo = exposure_factor_ant(now_zone, agent.pos)
        strength = ramp * soft * expo
        st = agent.state
        st.energy = clamp01(st.energy + now_zone.deltas.get("energy", 0.0) * strength * dt * 60.0)
        st.load = clamp01(st.load + now_zone.deltas.get("load", 0.0) * strength * dt * 60.0)
        st.coherence = clamp01(st.coherence + now_zone.deltas.get("coherence", 0.0) * strength * dt * 60.0)
        st.curiosity = clamp01(st.curiosity + now_zone.deltas.get("curiosity", 0.0) * strength * dt * 60.0)

    if agent.commit_ticks <= 0 or agent.commit_zone is None:
        chosen = decide_target_zone_ant(agent, zones)
        agent.last_choice = chosen.name
        agent.commit_zone = chosen
        agent.commit_ticks = random.randint(p.commit_min, p.commit_max)
        agent.target = pick_point_in_zone(chosen, pad=55)
    else:
        agent.commit_ticks -= 1

    if agent.commit_zone and agent.commit_zone.contains(agent.pos):
        if random.random() < p.inside_zone_retarget_p:
            agent.target = pick_point_in_zone(agent.commit_zone, pad=55)
        if random.random() < p.orbit_impulse_p:
            agent.target += v2(
                random.randint(-p.orbit_strength_x, p.orbit_strength_x),
                random.randint(-p.orbit_strength_y, p.orbit_strength_y),
            )

    to_target = agent.target - agent.pos
    desired = safe_normalize(to_target)

    ang = random.random() * math.tau
    wander = v2(math.cos(ang), math.sin(ang))
    desired = safe_normalize(desired + p.wander_mix * wander)

    speed = p.base_speed * (0.35 + 1.05 * agent.state.energy)
    speed = max(p.crawl_speed_min, speed)

    steer = desired * speed
    agent.vel = agent.vel.lerp(steer, p.lerp_alpha)
    agent.pos += agent.vel * dt

    agent.pos.x = max(20, min(W - 20, agent.pos.x))
    agent.pos.y = max(20, min(H - 20, agent.pos.y))


# =========================
# FISH ENGINE
# =========================
def maybe_edge_pause_fish(agent: Agent, z: Optional[Zone]):
    p = agent.profile
    if z is None:
        agent.fish_edge_pause_latch = False
        return

    near = z.near_edge(agent.pos, p.soft_edge_margin)
    if near and not agent.fish_edge_pause_latch and agent.fish_pause_cooldown_s <= 0.0:
        hold = random.uniform(p.fish_pause_min_s, p.fish_pause_max_s) * z.pause_bias
        agent.fish_pause_hold_s = max(agent.fish_pause_hold_s, hold)
        agent.fish_edge_pause_latch = True
    elif not near:
        agent.fish_edge_pause_latch = False


def pick_commit_zone_fish(agent: Agent, zones: List[Zone], variant: str) -> Optional[str]:
    p = agent.profile
    if agent.fish_commit_cooldown_ticks > 0:
        return None

    s = agent.state
    weights: Dict[str, float] = {}
    for z in zones:
        if variant == "B3_FISH_NO_REST" and z.name == "Rest":
            continue

        w = 1.0 * z.commit_bias

        if z.name == "Park":
            w *= (1.0 + 1.6 * s.load + 1.2 * (1.0 - s.energy))
        elif z.name == "Library":
            w *= (1.0 + 1.4 * s.curiosity + 0.8 * s.coherence)
        elif z.name == "Rest":
            w *= (1.0 + 1.6 * (1.0 - s.coherence) + 0.8 * s.load)
        elif z.name == "Transition":
            w *= 0.55

        # P2A: sparrow (D) nudged toward Park/curiosity while keeping fish locomotion
        if variant == "P2A_SPARROW_ANT_COG" and agent.agent_id == "D":
            if z.name == "Park":
                w *= 2.0
            elif z.name == "Library":
                w *= 1.2

        weights[z.name] = w

    if not weights:
        return None

    if random.random() < p.fish_commit_p:
        total = sum(weights.values())
        r = random.random() * total
        acc = 0.0
        for name, wv in weights.items():
            acc += wv
            if r <= acc:
                return name
    return None


def decide_target_fish(agent: Agent, zones: List[Zone], variant: str) -> pygame.Vector2:
    p = agent.profile
    s = agent.state

    if agent.fish_commit_ticks_left > 0 and agent.fish_commit_zone is not None:
        for z in zones:
            if z.name == agent.fish_commit_zone:
                return z.center()

    if agent.fish_leaving_lock_ticks > 0:
        return agent.target

    current = zone_at(zones, agent.pos)
    if current is not None and agent.dwell_ticks < p.fish_min_dwell_ticks:
        return current.center()

    scores: Dict[str, float] = {}
    current_name = current.name if current else "None"

    for z in zones:
        if variant == "B3_FISH_NO_REST" and z.name == "Rest":
            continue

        score = 0.0
        if z.name == "Park":
            score += 2.0 * (1.0 - s.energy)
            score += 1.5 * s.load
            score += 0.3 * (1.0 - s.coherence)
            if variant == "P2A_SPARROW_ANT_COG" and agent.agent_id == "D":
                score += 0.35  # mild extra pull
        if z.name == "Library":
            score += 2.0 * s.curiosity
            score += 1.2 * s.coherence
            score -= 1.2 * s.load
        if z.name == "Rest":
            score += 1.6 * (1.0 - s.coherence)
            score += 1.0 * s.load
            score += 0.6 * (1.0 - s.energy)
        if z.name == "Transition":
            score += 0.25
            score += 0.6 * (1.0 - s.coherence)

        if current is not None and current.name == z.name and current.near_edge(agent.pos, p.soft_edge_margin):
            score -= 0.35

        score += random.uniform(-0.08, 0.08)
        scores[z.name] = score

    if not scores:
        return pygame.Vector2(W / 2, H / 2)

    best_name = max(scores, key=scores.get)

    if current is not None and best_name != current_name:
        if not current.near_edge(agent.pos, p.soft_edge_margin):
            return current.center()
        else:
            agent.fish_leaving_lock_ticks = p.fish_exit_lock_ticks

    for z in zones:
        if z.name == best_name:
            return z.center()

    return pygame.Vector2(W / 2, H / 2)


def update_agent_fish(agent: Agent, zones: List[Zone], dt: float, variant: str):
    p = agent.profile

    agent.fish_pause_cooldown_s = max(0.0, agent.fish_pause_cooldown_s - dt)
    agent.fish_pause_hold_s = max(0.0, agent.fish_pause_hold_s - dt)

    if agent.fish_leaving_lock_ticks > 0:
        agent.fish_leaving_lock_ticks -= 1

    if agent.fish_commit_cooldown_ticks > 0:
        agent.fish_commit_cooldown_ticks -= 1
    if agent.fish_commit_ticks_left > 0:
        agent.fish_commit_ticks_left -= 1
        if agent.fish_commit_ticks_left <= 0:
            agent.fish_commit_zone = None
            agent.fish_commit_cooldown_ticks = random.randint(
                p.fish_commit_cooldown_min, p.fish_commit_cooldown_max
            )

    z = zone_at(zones, agent.pos)
    zname = z.name if z else "None"
    if zname == agent.current_zone:
        agent.dwell_ticks += 1
        # work units (fish-side): only count in Library/Park
        if zname in ("Library", "Park"):
            agent.work_units += 1
            agent.output_score = agent.work_units * agent.state.coherence
    else:
        agent.current_zone = zname
        agent.dwell_ticks = 0

    apply_zone_effects(agent, z, dt)
    maybe_edge_pause_fish(agent, z)

    if agent.fish_commit_zone is None and agent.fish_commit_ticks_left <= 0:
        cz = pick_commit_zone_fish(agent, zones, variant)
        if cz is not None:
            agent.fish_commit_zone = cz
            agent.fish_commit_ticks_left = random.randint(p.fish_commit_min, p.fish_commit_max)

    if (agent.dwell_ticks % 8 == 0 or agent.target.length_squared() == 0):
        agent.target = decide_target_fish(agent, zones, variant)

    if agent.fish_pause_hold_s > 0.0:
        agent.paused = True
    else:
        agent.paused = False
        agent.fish_pause_cooldown_s = max(agent.fish_pause_cooldown_s, 0.10)

    if not agent.paused:
        to = (agent.target - agent.pos)
        dist = to.length()
        if dist > 1.0:
            desired = to.normalize() * p.fish_base_speed
            t = clamp(dt * p.fish_turn_rate, 0.0, 1.0)
            agent.vel = agent.vel.lerp(desired, t)
            agent.pos += agent.vel * dt
        else:
            agent.vel *= 0.85
    else:
        agent.vel *= 0.85


# =========================
# Draw
# =========================
def draw_world(screen: pygame.Surface, zones: List[Zone], agents: List[Agent]):
    screen.fill(BG)
    margin = agents[0].profile.soft_edge_margin if agents else 35

    for z in zones:
        rounded_rect(screen, z.rect, z.color, radius=26, width=0)
        r_in = inner_rect(z.rect, margin)
        rounded_rect(screen, r_in, (245, 245, 248), radius=20, width=2)

    for a in agents:
        if a.agent_id == "A":
            col = AGENT_A_COLOR
        elif a.agent_id == "B":
            col = AGENT_B_COLOR
        elif a.agent_id == "C":
            col = AGENT_C_COLOR
        else:
            col = AGENT_D_COLOR

        if a.profile.model == "ant":
            max_len = int(18 + 90 * a.state.energy)
            if len(a.trail) > max_len:
                del a.trail[:-max_len]
            for i in range(1, len(a.trail)):
                pygame.draw.line(screen, col, a.trail[i - 1], a.trail[i], width=2)
        else:
            streak_len = 22
            dirv = a.vel.normalize() if a.vel.length() > 0.5 else pygame.Vector2(1, 0)
            start = a.pos - dirv * streak_len
            end = a.pos
            pygame.draw.line(screen, col, start, end, width=3)

        pygame.draw.circle(screen, col, (int(a.pos.x), int(a.pos.y)), 8)


def draw_hud(screen: pygame.Surface, font: pygame.font.Font, agents: List[Agent], csv_path: str, variant: str):
    lines = [
        "SPACE Play/Pause | N Step | O HUD | ESC Quit",
        f"VARIANT: {variant}   telemetry: {csv_path}",
        "A=Fantail(FISH)  D=Sparrow(BIRD-profile)  B,C=Kiwi(ANT)",
    ]
    y = 12
    for ln in lines:
        screen.blit(font.render(ln, True, TXT), (12, y))
        y += 22

    for a in agents:
        s = a.state
        line = (
            f"{a.agent_id} {a.profile.name:<12} "
            f"Z:{a.current_zone:<10} "
            f"D:{a.dwell_ticks:>3} "
            f"paused:{'1' if a.paused else '0'} "
            f"E:{s.energy:.2f} "
            f"L:{s.load:.2f} "
            f"C:{s.coherence:.2f} "
            f"Q:{s.curiosity:.2f} "
            f"W:{a.work_units:<5} "
            f"O:{a.output_score:.2f}"
        )
        screen.blit(font.render(line, True, SUBTXT), (12, y))
        y += 20


# =========================
# Simulation runner
# =========================
def run_sim(
    variant: str,
    seed: Optional[int],
    seconds: float,
    *,
    runs: Optional[int] = None,
    headless: bool,
    summarize: bool,
    policy_name: str,
    trace_strength: float,
) -> str:
    if seed is not None:
        random.seed(seed)

    zones = build_zones(variant)
    zmap = {z.name: z for z in zones}
    any_center = list(zmap.values())[0].center()

    # Profiles
    fantail = get_profile("fish")
    kiwi_fast = get_profile("ant_fast")
    kiwi_slow = get_profile("ant_slow")
    sparrow = get_profile("bird")  # engine determined by profiles.py (model="ant" or "fish")

    lib_center = zmap.get("Library", None).center() if "Library" in zmap else any_center
    park_center = zmap.get("Park", None).center() if "Park" in zmap else any_center
    trans_center = zmap.get("Transition", None).center() if "Transition" in zmap else any_center

    # Agents
    A = Agent("A", fantail, v2(250, 310), v2(0, 0), lib_center)     # Fantail
    B = Agent("B", kiwi_fast, v2(720, 310), v2(0, 0), park_center)  # Kiwi fast
    C = Agent("C", kiwi_slow, v2(700, 360), v2(0, 0), park_center)  # Kiwi slow
    D = Agent("D", sparrow, v2(500, 240), v2(0, 0), trans_center)   # Sparrow (profile decides engine)

    # P2A seed (spawn-only cognition nudge)
    if variant == "P2A_SPARROW_ANT_COG":
        D.target = park_center
        D.state.energy = 0.55
        D.state.load = 0.65
        D.state.coherence = 0.55
        D.state.curiosity = 0.75

    agents = [A, B, C, D]

    # Policy bundle (passive unless enabled)
    # make_policy may or may not accept trace_strength — support both safely.
    try:
        policy_bundle = make_policy(policy_name, trace_strength=trace_strength)
    except TypeError:
        policy_bundle = make_policy(policy_name)

    for ag in agents:
        ag.policy = policy_bundle

    # init trails/commit for ANT agents only
    for ag in agents:
        if ag.profile.model == "ant":
            start_zone = zmap.get("Library", list(zmap.values())[0])
            ag.commit_zone = start_zone
            ag.commit_ticks = random.randint(ag.profile.commit_min, ag.profile.commit_max)
            ag.last_choice = ag.commit_zone.name
            ag.target = pick_point_in_zone(ag.commit_zone, pad=55)
            ag.trail = [ag.pos.copy()]

    # Telemetry
    csv_path = ensure_telemetry_paths(variant, runs)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    f = open(csv_path, "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow([
        "t_sec","dt","agent_id",
        "x","y","vx","vy","speed",
        "zone","commit_zone","commit_left","dwell_ticks","work_units","output_score",
        "energy","load","coherence","curiosity",
        "profile","model",
        "variant","seed","policy","trace_strength"
    ])

    # Pygame only if not headless
    screen = None
    clock = None
    font = None
    tick_running = True
    step_once = False
    hud_on = True

    if not headless:
        pygame.init()
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption(f"ORPIN / MOS Sandbox Town — Ecosystem ({variant})")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("consolas", 18)

    t_sec = 0.0
    running = True

    try:
        while running:
            # dt selection
            if headless:
                dt = 1.0 / float(FPS)
            else:
                dt = (clock.tick(FPS) / 1000.0) if clock else (1.0 / float(FPS))

            # clamp dt by profiles
            dt = min(dt, min(a.profile.dt_clamp for a in agents))

            # events only when visual
            if not headless:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_SPACE:
                            tick_running = not tick_running
                        elif event.key == pygame.K_n:
                            step_once = True
                        elif event.key == pygame.K_o:
                            hud_on = not hud_on

            ran = True if headless else (tick_running or step_once)
            if ran:
                t_sec += dt

                ctx = {
                    "zones": zones,
                    "dt": dt,
                    "variant": variant,
                    "policy_name": policy_name,
                    "trace_strength": trace_strength,
                }

                for ag in agents:
                    before = ag.pos.copy()

                    # --- policy pre-step (PASSIVE unless enabled) ---
                    if policy_name != "none" and ag.policy is not None:
                        ag.policy.before_step(ag, ctx)

                    # --- model update ---
                    if ag.profile.model == "fish":
                        update_agent_fish(ag, zones, dt, variant)
                    else:
                        update_agent_ant(ag, zones, dt)

                    if (ag.pos - before).length() >= ag.profile.trail_move_eps:
                        ag.trail.append(ag.pos.copy())

                    # --- policy post-step ---
                    if policy_name != "none" and ag.policy is not None:
                        ag.policy.after_step(ag, ctx)

                    s = ag.state
                    speed = ag.vel.length()

                    if ag.profile.model == "fish":
                        commit_zone = ag.fish_commit_zone if ag.fish_commit_zone else "-"
                        commit_left = ag.fish_commit_ticks_left
                    else:
                        commit_zone = ag.commit_zone.name if ag.commit_zone else "-"
                        commit_left = ag.commit_ticks

                    w.writerow([
                        round(t_sec, 4), round(dt, 4), ag.agent_id,
                        round(ag.pos.x, 2), round(ag.pos.y, 2),
                        round(ag.vel.x, 2), round(ag.vel.y, 2),
                        round(speed, 2),
                        ag.current_zone, commit_zone, commit_left, ag.dwell_ticks, ag.work_units, round(ag.output_score, 4),
                        round(s.energy, 4), round(s.load, 4), round(s.coherence, 4), round(s.curiosity, 4),
                        ag.profile.name, ag.profile.model,
                        variant, (seed if seed is not None else ""), policy_name, round(trace_strength, 4)
                    ])

                step_once = False

            # headless auto-stop
            if headless and t_sec >= seconds:
                running = False

            # draw only when visual
            if not headless and screen is not None:
                draw_world(screen, zones, agents)
                if hud_on and font is not None:
                    draw_hud(screen, font, agents, csv_path, variant)
                pygame.display.flip()

    finally:
        f.close()
        if not headless:
            pygame.quit()

    if summarize:
        print(f"\nRun saved -> {csv_path}")
        print("Next CMD (from repo root):")
        print(f"  python telemetry_tools/summarize_run.py \"{csv_path}\"")
        print("This will print + save *_summary.csv next to the run.\n")

    return csv_path


# =========================
# CLI entry
# =========================
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=0, help="Number of headless runs to execute (batch mode).")
    parser.add_argument("--seconds", type=float, default=180.0, help="Seconds per run (headless).")
    parser.add_argument("--seed", type=int, default=None, help="Seed base (batch uses seed+i).")
    parser.add_argument("--headless", action="store_true", help="Run without opening a window (no rendering).")
    parser.add_argument("--summarize", action="store_true", help="Print the summarize_run.py command at the end.")
    parser.add_argument("--policy", type=str, default="none", help="Policy mode: none | trace")
    parser.add_argument("--trace-strength", type=float, default=1.0, help="Trace intensity (0 disables trace, 1 default, >1 stronger).")
    args = parser.parse_args()

    # Headless is forced for batch runs (low load, no visuals)
    headless = args.headless or (args.runs is not None and args.runs > 0)

    if args.runs and args.runs > 0:
        for i in range(args.runs):
            seed_i = (args.seed + i) if (args.seed is not None) else None
            run_sim(
                VARIANT,
                seed_i,
                float(args.seconds),
                runs=args.runs,
                headless=True,
                summarize=bool(args.summarize),
                policy_name=str(args.policy),
                trace_strength=float(args.trace_strength),
            )
        return

    # Single run (interactive unless headless flag is set)
    run_sim(
        VARIANT,
        args.seed,
        float(args.seconds),
        headless=bool(headless),
        summarize=bool(args.summarize),
        policy_name=str(args.policy),
        trace_strength=float(args.trace_strength),
    )


if __name__ == "__main__":
    main()
