import math
import os
import csv
import random
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

import pygame

from profiles import get_profile, PROFILES, MotionProfile

# -------------------------
# Window
# -------------------------
W, H = 980, 560
FPS = 60

# Colors
BG = (16, 16, 18)
TXT = (235, 235, 235)
SUBTXT = (190, 190, 195)

COLOR_LIBRARY = (45, 140, 215)
COLOR_PARK = (85, 190, 105)
COLOR_TRANSITION = (175, 175, 180)
COLOR_REST = (205, 195, 160)

AGENT_COLOR = (210, 255, 230)

# Zones
ZONE_COLORS = {
    "Library": COLOR_LIBRARY,
    "Park": COLOR_PARK,
    "Transition": COLOR_TRANSITION,
    "Rest": COLOR_REST,
}


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


def rounded_rect(surface: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int], radius: int, width: int = 0):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


def inner_rect(rect: pygame.Rect, margin: int) -> pygame.Rect:
    r = rect.inflate(-2 * margin, -2 * margin)
    if r.width < 2:
        r.width = 2
    if r.height < 2:
        r.height = 2
    return r


def ensure_telemetry_paths() -> str:
    out_dir = os.path.join("telemetry", "runs")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(out_dir, f"run_{ts}.csv")


# -------------------------
# Data Models
# -------------------------
@dataclass
class Zone:
    name: str
    rect: pygame.Rect
    deltas: Dict[str, float]  # per-second deltas
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
    pos: pygame.Vector2
    vel: pygame.Vector2
    target: pygame.Vector2
    state: AgentState = field(default_factory=AgentState)

    current_zone: str = "None"
    dwell_ticks: int = 0

    # ---------- shared pause ----------
    paused: bool = False

    # ---------- ANT pause ----------
    pause_hold_ticks: int = 0
    pause_cooldown_ticks: int = 0

    # ---------- ANT commit ----------
    commit_zone: Optional[Zone] = None
    commit_ticks: int = 0
    last_choice: str = "None"

    # ---------- FISH pause (seconds) ----------
    fish_pause_hold_s: float = 0.0
    fish_pause_cooldown_s: float = 0.0
    fish_edge_pause_latch: bool = False

    # ---------- FISH leaving lock ----------
    fish_leaving_lock_ticks: int = 0

    # ---------- FISH commit ----------
    fish_commit_zone: Optional[str] = None
    fish_commit_ticks_left: int = 0
    fish_commit_cooldown_ticks: int = 0


# -------------------------
# World Build
# -------------------------
def build_zones() -> List[Zone]:
    library = Zone(
        "Library",
        pygame.Rect(110, 190, 280, 260),
        {"energy": -0.030, "load": +0.020, "coherence": +0.015, "curiosity": +0.020},
        COLOR_LIBRARY,
        pause_bias=1.15,
        commit_bias=1.25,
    )
    park = Zone(
        "Park",
        pygame.Rect(590, 190, 280, 260),
        {"energy": +0.050, "load": -0.020, "coherence": +0.012, "curiosity": -0.005},
        COLOR_PARK,
        pause_bias=1.05,
        commit_bias=1.05,
    )
    transition = Zone(
        "Transition",
        pygame.Rect(420, 285, 160, 90),
        {"energy": -0.010, "load": -0.010, "coherence": +0.006, "curiosity": +0.002},
        COLOR_TRANSITION,
        pause_bias=1.30,
        commit_bias=0.60,
    )
    rest = Zone(
        "Rest",
        pygame.Rect(430, 395, 140, 70),
        {"energy": +0.012, "load": -0.018, "coherence": +0.020, "curiosity": -0.004},
        COLOR_REST,
        pause_bias=1.55,
        commit_bias=0.55,
    )
    return [library, park, transition, rest]


def zone_at(zones: List[Zone], pos: pygame.Vector2) -> Optional[Zone]:
    for z in zones:
        if z.contains(pos):
            return z
    return None


def pick_point_in_zone(z: Zone, pad: int = 55) -> pygame.Vector2:
    r = z.rect
    x = random.randint(r.left + pad, r.right - pad)
    y = random.randint(r.top + pad, r.bottom - pad)
    return v2(x, y)


# -------------------------
# Shared state effects
# -------------------------
def apply_zone_effects(agent: Agent, z: Optional[Zone], dt: float):
    s = agent.state
    if z is None:
        # mild drift toward neutral
        s.energy = clamp01(s.energy + (-0.006) * dt)
        s.load = clamp01(s.load + (-0.004) * dt)
        s.coherence = clamp01(s.coherence + (+0.002) * dt)
        s.curiosity = clamp01(s.curiosity + (+0.001) * dt)
        return

    s.energy = clamp01(s.energy + z.deltas.get("energy", 0.0) * dt)
    s.load = clamp01(s.load + z.deltas.get("load", 0.0) * dt)
    s.coherence = clamp01(s.coherence + z.deltas.get("coherence", 0.0) * dt)
    s.curiosity = clamp01(s.curiosity + z.deltas.get("curiosity", 0.0) * dt)


# ============================================================
# ANT MODEL (steer + commit + tick-pause + crawl + trail)
# ============================================================
def dwell_ramp_ant(agent: Agent, p: MotionProfile) -> float:
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

    t = max(0.0, min(1.0, 1.0 - (d / max(1.0, float(margin)))))
    return t


def exposure_factor_ant(z: Zone, pos: pygame.Vector2) -> float:
    if z.name not in ("Transition", "Rest"):
        return 1.0
    cx, cy = z.rect.center
    dx = (pos.x - cx) / max(1.0, z.rect.width / 2)
    dy = (pos.y - cy) / max(1.0, z.rect.height / 2)
    d = math.sqrt(dx * dx + dy * dy)
    return max(0.35, 1.15 - d)


def decide_target_zone_ant(agent: Agent, zones: List[Zone], p: MotionProfile) -> Zone:
    zmap = {z.name: z for z in zones}
    park = zmap["Park"]
    lib = zmap["Library"]
    trans = zmap["Transition"]
    rest = zmap["Rest"]

    s = agent.state
    score_park = (1.0 - s.energy) * 1.25 + s.load * 1.20 + (1.0 - s.coherence) * 0.15
    score_lib = s.curiosity * 1.10 + s.coherence * 0.75 - s.load * 0.30
    score_trans = (1.0 - s.coherence) * 1.25 + s.load * 0.35
    score_rest = (1.0 - s.energy) * 0.55 + s.load * 0.85 + (1.0 - s.coherence) * 0.25

    scores = {
        "Park": score_park,
        "Library": score_lib,
        "Transition": score_trans,
        "Rest": score_rest,
    }

    best_name = max(scores.keys(), key=lambda k: scores[k])
    best_score = scores[best_name]

    if agent.last_choice in scores and agent.last_choice in zmap:
        last_score = scores[agent.last_choice]
        if best_name != agent.last_choice and (best_score - last_score) < p.hysteresis_eps:
            best_name = agent.last_choice

    return zmap.get(best_name, trans)


def edge_pause_check_ant(agent: Agent, prev_zone: Optional[Zone], now_zone: Optional[Zone], p: MotionProfile):
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


def update_agent_ant(agent: Agent, zones: List[Zone], dt: float, p: MotionProfile):
    # pause
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

    edge_pause_check_ant(agent, prev_zone, now_zone, p)

    if now_zone:
        ramp = dwell_ramp_ant(agent, p)
        soft = soft_edge_factor_ant(now_zone, agent.pos, p.soft_edge_margin)
        expo = exposure_factor_ant(now_zone, agent.pos)
        strength = ramp * soft * expo
        # dt * 60 matches prior ant builds
        st = agent.state
        st.energy = clamp01(st.energy + now_zone.deltas.get("energy", 0.0) * strength * dt * 60.0)
        st.load = clamp01(st.load + now_zone.deltas.get("load", 0.0) * strength * dt * 60.0)
        st.coherence = clamp01(st.coherence + now_zone.deltas.get("coherence", 0.0) * strength * dt * 60.0)
        st.curiosity = clamp01(st.curiosity + now_zone.deltas.get("curiosity", 0.0) * strength * dt * 60.0)

    # Commit
    if agent.commit_ticks <= 0 or agent.commit_zone is None:
        chosen = decide_target_zone_ant(agent, zones, p)
        agent.last_choice = chosen.name
        agent.commit_zone = chosen
        agent.commit_ticks = random.randint(p.commit_min, p.commit_max)
        agent.target = pick_point_in_zone(chosen, pad=55)
    else:
        agent.commit_ticks -= 1

    # Retarget + orbit impulse
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

    # wander blend
    ang = random.random() * math.tau
    wander = v2(math.cos(ang), math.sin(ang))
    desired = safe_normalize(desired + p.wander_mix * wander)

    # speed with crawl minimum
    speed = p.base_speed * (0.35 + 1.05 * agent.state.energy)
    speed = max(p.crawl_speed_min, speed)

    steer = desired * speed
    agent.vel = agent.vel.lerp(steer, p.lerp_alpha)
    agent.pos += agent.vel * dt

    agent.pos.x = max(20, min(W - 20, agent.pos.x))
    agent.pos.y = max(20, min(H - 20, agent.pos.y))


# ============================================================
# FISH MODEL (ported from v1.1.7: glide + seconds-pauses + centers)
# ============================================================
def maybe_edge_pause_fish(agent: Agent, z: Optional[Zone], p: MotionProfile):
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


def pick_commit_zone_fish(agent: Agent, zones: List[Zone], p: MotionProfile) -> Optional[str]:
    if agent.fish_commit_cooldown_ticks > 0:
        return None

    s = agent.state
    weights: Dict[str, float] = {}

    for z in zones:
        w = 1.0 * z.commit_bias
        if z.name == "Park":
            w *= (1.0 + 1.6 * s.load + 1.2 * (1.0 - s.energy))
        elif z.name == "Library":
            w *= (1.0 + 1.4 * s.curiosity + 0.8 * s.coherence)
        elif z.name == "Rest":
            w *= (1.0 + 1.6 * (1.0 - s.coherence) + 0.8 * s.load)
        elif z.name == "Transition":
            w *= 0.55
        weights[z.name] = w

    if random.random() < p.fish_commit_p:
        total = sum(weights.values())
        r = random.random() * total
        acc = 0.0
        for name, w in weights.items():
            acc += w
            if r <= acc:
                return name
    return None


def decide_target_fish(agent: Agent, zones: List[Zone], p: MotionProfile) -> pygame.Vector2:
    s = agent.state

    # honor commit: aim for committed zone center
    if agent.fish_commit_ticks_left > 0 and agent.fish_commit_zone is not None:
        for z in zones:
            if z.name == agent.fish_commit_zone:
                return z.center()

    # leaving lock: keep current target briefly
    if agent.fish_leaving_lock_ticks > 0:
        return agent.target

    current = zone_at(zones, agent.pos)
    if current is not None and agent.dwell_ticks < p.fish_min_dwell_ticks:
        return current.center()

    scores: Dict[str, float] = {}
    current_name = current.name if current else "None"

    for z in zones:
        score = 0.0
        if z.name == "Park":
            score += 2.0 * (1.0 - s.energy)
            score += 1.5 * s.load
            score += 0.3 * (1.0 - s.coherence)
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


def update_agent_fish(agent: Agent, zones: List[Zone], dt: float, tick_running: bool, p: MotionProfile):
    # seconds pause timers
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
            agent.fish_commit_cooldown_ticks = random.randint(p.fish_commit_cooldown_min, p.fish_commit_cooldown_max)

    # zone + dwell
    z = zone_at(zones, agent.pos)
    zname = z.name if z else "None"
    if zname == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = zname
        agent.dwell_ticks = 0

    if tick_running:
        apply_zone_effects(agent, z, dt)

    maybe_edge_pause_fish(agent, z, p)

    # commit start
    if tick_running and agent.fish_commit_zone is None and agent.fish_commit_ticks_left <= 0:
        cz = pick_commit_zone_fish(agent, zones, p)
        if cz is not None:
            agent.fish_commit_zone = cz
            agent.fish_commit_ticks_left = random.randint(p.fish_commit_min, p.fish_commit_max)

    # decide target occasionally
    if tick_running and (agent.dwell_ticks % 8 == 0 or agent.target.length_squared() == 0):
        agent.target = decide_target_fish(agent, zones, p)

    # pause
    if agent.fish_pause_hold_s > 0.0:
        agent.paused = True
    else:
        agent.paused = False
        agent.fish_pause_cooldown_s = max(agent.fish_pause_cooldown_s, 0.10)

    # movement
    if tick_running and not agent.paused:
        to = (agent.target - agent.pos)
        dist = to.length()
        if dist > 1.0:
            desired = to.normalize() * p.fish_base_speed
            # glide smoothing
            t = clamp(dt * p.fish_turn_rate, 0.0, 1.0)
            agent.vel = agent.vel.lerp(desired, t)
            agent.pos += agent.vel * dt
        else:
            agent.vel *= 0.85
    else:
        agent.vel *= 0.85


# -------------------------
# Rendering
# -------------------------
def draw_hud(screen: pygame.Surface, font: pygame.font.Font, agent: Agent, hud_on: bool, p: MotionProfile, csv_path: str):
    if not hud_on:
        return

    s = agent.state
    zone = agent.current_zone
    model = p.model
    commit_label = "-"
    commit_left = 0

    if model == "fish":
        commit_label = agent.fish_commit_zone if agent.fish_commit_zone else "-"
        commit_left = agent.fish_commit_ticks_left
    else:
        commit_label = agent.commit_zone.name if agent.commit_zone else "-"
        commit_left = agent.commit_ticks

    lines = [
        "SPACE Play/Pause | N Step | O HUD | 1 Fish | 2 AntSlow | 3 AntFast | ESC Quit",
        f"profile:{p.name:<12} model:{model:<4}  Z:{zone:<10}  paused:{'1' if agent.paused else '0'}  D:{agent.dwell_ticks:>3}",
        f"E:{s.energy:.2f}  L:{s.load:.2f}  C:{s.coherence:.2f}  Q:{s.curiosity:.2f}",
        f"commit:{commit_label}({commit_left})  margin:{p.soft_edge_margin}",
        f"telemetry: {csv_path}",
    ]

    y = 12
    for i, t in enumerate(lines):
        col = TXT if i < 2 else SUBTXT
        surf = font.render(t, True, col)
        screen.blit(surf, (12, y))
        y += 22


def draw_world(screen: pygame.Surface, zones: List[Zone], agent: Agent, trail: List[pygame.Vector2], p: MotionProfile):
    screen.fill(BG)

    for z in zones:
        rounded_rect(screen, z.rect, z.color, radius=26, width=0)
        r_in = inner_rect(z.rect, p.soft_edge_margin)
        rounded_rect(screen, r_in, (245, 245, 248), radius=20, width=2)

    # trail length scales with energy (only for ant model; fish uses streak)
    if p.model == "ant":
        max_len = int(18 + 90 * agent.state.energy)
        if len(trail) > max_len:
            del trail[:-max_len]
        for i in range(1, len(trail)):
            a = trail[i - 1]
            b = trail[i]
            pygame.draw.line(screen, (175, 255, 220), a, b, width=2)
    else:
        # fish streak (like v1.1.7)
        streak_len = 22
        if agent.vel.length() > 0.5:
            dirv = agent.vel.normalize()
        else:
            dirv = pygame.Vector2(1, 0)
        start = agent.pos - dirv * streak_len
        end = agent.pos
        pygame.draw.line(screen, (120, 255, 210), start, end, width=3)

    # agent
    pygame.draw.circle(screen, AGENT_COLOR, (int(agent.pos.x), int(agent.pos.y)), 8)

    # ant nose indicator
    if p.model == "ant":
        spd = agent.vel.length()
        nose_len = max(8.0, min(18.0, spd * 0.15))
        if spd > 0.5:
            n = safe_normalize(agent.vel)
            tip = agent.pos + n * nose_len
            pygame.draw.line(screen, (160, 255, 210), agent.pos, tip, width=3)


# -------------------------
# Main
# -------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 18)

    zones = build_zones()
    zmap = {z.name: z for z in zones}

    # default profile
    p = get_profile("fish")

    # agent start
    agent = Agent(pos=v2(250, 310), vel=v2(0, 0), target=v2(250, 310))

    # init ANT commit data (safe even if fish)
    agent.commit_zone = zmap["Library"]
    agent.commit_ticks = random.randint(p.commit_min, p.commit_max)
    agent.last_choice = "Library"
    agent.target = zmap["Library"].center()

    # init FISH target
    agent.target = zmap["Library"].center()

    hud_on = True
    running = True
    tick_running = True
    step_once = False

    # trail list for ant model
    trail: List[pygame.Vector2] = [agent.pos.copy()]

    # telemetry
    csv_path = ensure_telemetry_paths()
    f = open(csv_path, "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow([
        "t_sec","dt","x","y","vx","vy","speed",
        "zone","commit_zone","commit_left","dwell_ticks",
        "energy","load","coherence","curiosity",
        "profile","model"
    ])
    t_sec = 0.0

    try:
        while running:
            dt = clock.tick(FPS) / 1000.0
            dt = min(dt, p.dt_clamp)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        tick_running = not tick_running
                    elif event.key == pygame.K_o:
                        hud_on = not hud_on
                    elif event.key == pygame.K_n:
                        step_once = True

                    # switch profiles
                    elif event.key == pygame.K_1:
                        p = get_profile("fish")
                        pygame.display.set_caption(f"SandboxTown v1.1.12 — {p.name}")
                    elif event.key == pygame.K_2:
                        p = get_profile("ant_slow")
                        pygame.display.set_caption(f"SandboxTown v1.1.12 — {p.name}")
                    elif event.key == pygame.K_3:
                        p = get_profile("ant_fast")
                        pygame.display.set_caption(f"SandboxTown v1.1.12 — {p.name}")

            ran = tick_running or step_once

            if ran:
                before = agent.pos.copy()

                if p.model == "fish":
                    update_agent_fish(agent, zones, dt, True, p)
                else:
                    update_agent_ant(agent, zones, dt, p)

                    # ant trail update (only if moved enough)
                    if (agent.pos - before).length() >= p.trail_move_eps:
                        trail.append(agent.pos.copy())

                # telemetry row
                t_sec += dt
                s = agent.state
                zone = agent.current_zone
                speed = agent.vel.length()

                if p.model == "fish":
                    commit_zone = agent.fish_commit_zone if agent.fish_commit_zone else "-"
                    commit_left = agent.fish_commit_ticks_left
                else:
                    commit_zone = agent.commit_zone.name if agent.commit_zone else "-"
                    commit_left = agent.commit_ticks

                w.writerow([
                    round(t_sec, 4), round(dt, 4),
                    round(agent.pos.x, 2), round(agent.pos.y, 2),
                    round(agent.vel.x, 2), round(agent.vel.y, 2),
                    round(speed, 2),
                    zone, commit_zone, commit_left, agent.dwell_ticks,
                    round(s.energy, 4), round(s.load, 4), round(s.coherence, 4), round(s.curiosity, 4),
                    p.name, p.model
                ])

                step_once = False

            draw_world(screen, zones, agent, trail, p)
            draw_hud(screen, font, agent, hud_on, p, csv_path)
            pygame.display.flip()

    finally:
        f.close()
        pygame.quit()


if __name__ == "__main__":
    main()
