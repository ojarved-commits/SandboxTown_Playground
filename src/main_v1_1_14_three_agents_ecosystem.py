# ORPIN / MOS Sandbox Town
# v1.1.14 — Three Agents Ecosystem (Standalone, no engine_* imports)
# Agents: FAST ANT + SLOW ANT + FISH
# Zones: Library, Park, Transition, Rest
# Telemetry: writes telemetry/runs/run_YYYYMMDD_HHMMSS.csv (default ON)

import math
import os
import csv
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List, Tuple

import pygame

# -------------------------
# Display / Timing
# -------------------------
W, H = 980, 560
FPS = 60
DT_CLAMP = 0.045

BG = (16, 16, 18)
TXT = (235, 235, 235)
SUBTXT = (190, 190, 195)

COLOR_LIBRARY = (45, 140, 215)
COLOR_PARK = (85, 190, 105)
COLOR_TRANSITION = (175, 175, 180)
COLOR_REST = (205, 195, 160)

# Visual palette per agent
AGENT_COLORS = {
    "FAST_ANT": (220, 255, 235),
    "SLOW_ANT": (180, 245, 220),
    "FISH":     (170, 245, 255),
}
TRAIL_COLORS = {
    "FAST_ANT": (175, 255, 220),
    "SLOW_ANT": (155, 240, 210),
    "FISH":     (160, 235, 255),
}

# -------------------------
# World / Zones
# -------------------------
SOFT_EDGE_MARGIN = 35

# Exposure / dwell dynamics (how effects intensify while staying)
DWELL_RAMP_CAP = 2.5
DWELL_RAMP_RATE = 1 / 240.0

# Hysteresis (prevents flip-flop in target selection)
HYSTERESIS_EPS = 0.12

# -------------------------
# Common helper
# -------------------------
def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

def v2(x: float, y: float) -> pygame.Vector2:
    return pygame.Vector2(float(x), float(y))

def safe_normalize(vec: pygame.Vector2) -> pygame.Vector2:
    if vec.length_squared() <= 1e-9:
        return pygame.Vector2(0, 0)
    return vec.normalize()

def rounded_rect(surface: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int], radius: int, width: int = 0):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)

def inner_rect(rect: pygame.Rect, margin: int) -> pygame.Rect:
    r = rect.inflate(-2 * margin, -2 * margin)
    if r.width < 2:
        r.width = 2
    if r.height < 2:
        r.height = 2
    return r

# -------------------------
# Data models
# -------------------------
@dataclass
class Zone:
    name: str
    rect: pygame.Rect
    deltas: Dict[str, float]
    color: Tuple[int, int, int]

    def contains(self, pos: pygame.Vector2) -> bool:
        return self.rect.collidepoint(pos.x, pos.y)

    def soft_contains(self, pos: pygame.Vector2, margin: int) -> bool:
        return inner_rect(self.rect, margin).collidepoint(pos.x, pos.y)

@dataclass
class AgentState:
    energy: float = 0.70
    load: float = 0.20
    coherence: float = 0.60
    curiosity: float = 0.70

@dataclass
class Profile:
    name: str

    # motion character
    base_speed: float
    crawl_speed_min: float
    wander_mix: float
    steer_lerp: float

    # zone commit behavior
    commit_min: int
    commit_max: int
    inside_zone_retarget_p: float
    orbit_impulse_p: float

    # edge-pause behavior (fishy "observe")
    edge_pause_ticks: int
    edge_pause_cooldown: int

    # trail shaping
    trail_move_eps: float

@dataclass
class Agent:
    agent_id: str
    profile: Profile
    pos: pygame.Vector2
    vel: pygame.Vector2
    target: pygame.Vector2
    state: AgentState = field(default_factory=AgentState)

    current_zone: str = "None"
    dwell_ticks: int = 0

    # pause controls
    pause_hold: int = 0
    pause_cooldown: int = 0

    # commit controls
    commit_zone: Optional[Zone] = None
    commit_ticks: int = 0
    last_choice: str = "None"

    # visuals
    trail: List[pygame.Vector2] = field(default_factory=list)

# -------------------------
# Profiles (FAST ANT + SLOW ANT + FISH)
# -------------------------
PROFILES: Dict[str, Profile] = {
    "FAST_ANT": Profile(
        name="FAST_ANT",
        base_speed=115.0,
        crawl_speed_min=42.0,
        wander_mix=0.42,
        steer_lerp=0.10,
        commit_min=55,
        commit_max=95,
        inside_zone_retarget_p=0.03,
        orbit_impulse_p=0.01,
        edge_pause_ticks=6,
        edge_pause_cooldown=16,
        trail_move_eps=2.2,
    ),
    "SLOW_ANT": Profile(
        name="SLOW_ANT",
        base_speed=78.0,
        crawl_speed_min=28.0,
        wander_mix=0.35,
        steer_lerp=0.085,
        commit_min=55,
        commit_max=105,
        inside_zone_retarget_p=0.025,
        orbit_impulse_p=0.008,
        edge_pause_ticks=8,
        edge_pause_cooldown=18,
        trail_move_eps=2.0,
    ),
    "FISH": Profile(
        name="FISH",
        base_speed=140.0,
        crawl_speed_min=36.0,
        wander_mix=0.72,
        steer_lerp=0.075,
        commit_min=45,
        commit_max=80,
        inside_zone_retarget_p=0.07,
        orbit_impulse_p=0.045,
        edge_pause_ticks=14,
        edge_pause_cooldown=22,
        trail_move_eps=2.8,
    ),
}

# -------------------------
# Zones
# -------------------------
def build_zones() -> List[Zone]:
    library = Zone(
        "Library",
        pygame.Rect(110, 190, 280, 260),
        {"energy": -0.0028, "load": +0.0035, "coherence": +0.0050, "curiosity": +0.0065},
        COLOR_LIBRARY,
    )
    park = Zone(
        "Park",
        pygame.Rect(590, 190, 280, 260),
        {"energy": +0.0065, "load": -0.0060, "coherence": +0.0030, "curiosity": -0.0015},
        COLOR_PARK,
    )
    transition = Zone(
        "Transition",
        pygame.Rect(420, 285, 160, 90),
        {"energy": +0.0010, "load": -0.0010, "coherence": +0.0015, "curiosity": +0.0008},
        COLOR_TRANSITION,
    )
    rest = Zone(
        "Rest",
        pygame.Rect(430, 395, 140, 70),
        {"energy": +0.0040, "load": -0.0042, "coherence": +0.0040, "curiosity": -0.0005},
        COLOR_REST,
    )
    return [library, park, transition, rest]

def zone_at(zones: List[Zone], pos: pygame.Vector2) -> Optional[Zone]:
    for z in zones:
        if z.contains(pos):
            return z
    return None

def pick_point_in_zone(z: Zone, pad: int = 45) -> pygame.Vector2:
    r = z.rect
    x = random.randint(r.left + pad, r.right - pad)
    y = random.randint(r.top + pad, r.bottom - pad)
    return v2(x, y)

# -------------------------
# Dwell / Soft-edge / Exposure shaping
# -------------------------
def dwell_ramp(agent: Agent) -> float:
    return min(DWELL_RAMP_CAP, 1.0 + agent.dwell_ticks * DWELL_RAMP_RATE)

def soft_edge_factor(z: Zone, pos: pygame.Vector2, margin: int) -> float:
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

def exposure_factor(z: Zone, pos: pygame.Vector2) -> float:
    # Transition/Rest: stronger effects when centered (feels like "settling in")
    if z.name not in ("Transition", "Rest"):
        return 1.0
    cx, cy = z.rect.center
    dx = (pos.x - cx) / max(1.0, z.rect.width / 2)
    dy = (pos.y - cy) / max(1.0, z.rect.height / 2)
    d = math.sqrt(dx * dx + dy * dy)
    return max(0.35, 1.15 - d)

# -------------------------
# Target selection (shared)
# -------------------------
def decide_target_zone(agent: Agent, zones: List[Zone]) -> Zone:
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

    # hysteresis: stick with last choice unless clearly better
    if agent.last_choice in scores and agent.last_choice in zmap:
        last_score = scores[agent.last_choice]
        if best_name != agent.last_choice and (best_score - last_score) < HYSTERESIS_EPS:
            best_name = agent.last_choice

    return zmap.get(best_name, trans)

# -------------------------
# Edge pause (per-agent profile)
# -------------------------
def edge_pause_check(agent: Agent, prev_zone: Optional[Zone], now_zone: Optional[Zone]):
    p = agent.profile
    if agent.pause_cooldown > 0:
        agent.pause_cooldown -= 1
        return

    # boundary cross or near soft edge triggers a brief pause
    if (prev_zone is None and now_zone is not None) or (prev_zone is not None and now_zone is None):
        agent.pause_hold = p.edge_pause_ticks
        agent.pause_cooldown = p.edge_pause_cooldown
        return

    if prev_zone is None or now_zone is None:
        return

    if prev_zone.name != now_zone.name:
        agent.pause_hold = p.edge_pause_ticks
        agent.pause_cooldown = p.edge_pause_cooldown
        return

    # near boundary inside zone
    if prev_zone.contains(agent.pos) and not prev_zone.soft_contains(agent.pos, SOFT_EDGE_MARGIN):
        agent.pause_hold = p.edge_pause_ticks
        agent.pause_cooldown = p.edge_pause_cooldown

# -------------------------
# Agent update (shared engine, shaped by profile)
# -------------------------
def update_agent(agent: Agent, zones: List[Zone], dt: float):
    p = agent.profile

    # pause handling
    if agent.pause_hold > 0:
        agent.pause_hold -= 1
        agent.vel *= 0.88
        return

    prev_zone = next((z for z in zones if z.name == agent.current_zone), None) if agent.current_zone != "None" else None
    now_zone = zone_at(zones, agent.pos)
    now_name = now_zone.name if now_zone else "None"

    # dwell tracking
    if now_name == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = now_name
        agent.dwell_ticks = 0

    # edge pause trigger
    edge_pause_check(agent, prev_zone, now_zone)

    # apply zone effects
    if now_zone:
        ramp = dwell_ramp(agent)
        soft = soft_edge_factor(now_zone, agent.pos, SOFT_EDGE_MARGIN)
        expo = exposure_factor(now_zone, agent.pos)
        strength = ramp * soft * expo

        st = agent.state
        st.energy = clamp01(st.energy + now_zone.deltas.get("energy", 0.0) * strength * dt * 60.0)
        st.load = clamp01(st.load + now_zone.deltas.get("load", 0.0) * strength * dt * 60.0)
        st.coherence = clamp01(st.coherence + now_zone.deltas.get("coherence", 0.0) * strength * dt * 60.0)
        st.curiosity = clamp01(st.curiosity + now_zone.deltas.get("curiosity", 0.0) * strength * dt * 60.0)

    # commit selection
    if agent.commit_ticks <= 0 or agent.commit_zone is None:
        chosen = decide_target_zone(agent, zones)
        agent.last_choice = chosen.name
        agent.commit_zone = chosen
        agent.commit_ticks = random.randint(p.commit_min, p.commit_max)
        agent.target = pick_point_in_zone(chosen, pad=55)
    else:
        agent.commit_ticks -= 1

    # inside-zone micro retarget (fish stronger than ant)
    if agent.commit_zone and agent.commit_zone.contains(agent.pos):
        if random.random() < p.inside_zone_retarget_p:
            agent.target = pick_point_in_zone(agent.commit_zone, pad=55)
        if random.random() < p.orbit_impulse_p:
            agent.target += v2(random.randint(-90, 90), random.randint(-60, 60))

    # motion: target + wander blend
    to_target = agent.target - agent.pos
    desired = safe_normalize(to_target)

    ang = random.random() * math.tau
    wander = v2(math.cos(ang), math.sin(ang))
    desired = safe_normalize(desired + p.wander_mix * wander)

    # energy-dependent speed with crawl minimum
    speed = p.base_speed * (0.35 + 1.05 * agent.state.energy)
    speed = max(p.crawl_speed_min, speed)

    steer = desired * speed
    agent.vel = agent.vel.lerp(steer, p.steer_lerp)
    agent.pos += agent.vel * dt

    # clamp to screen
    agent.pos.x = max(20, min(W - 20, agent.pos.x))
    agent.pos.y = max(20, min(H - 20, agent.pos.y))

# -------------------------
# Telemetry
# -------------------------
class TelemetryWriter:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.fp = None
        self.writer = None
        self.path = None
        self.t0 = pygame.time.get_ticks() / 1000.0

    def start(self):
        if not self.enabled:
            return
        os.makedirs(os.path.join("telemetry", "runs"), exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join("telemetry", "runs", f"run_{stamp}.csv")
        self.fp = open(self.path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.fp)
        self.writer.writerow([
            "t_sec","dt",
            "agent_id","profile",
            "x","y","vx","vy","speed",
            "zone","commit_zone","commit_ticks","dwell_ticks",
            "energy","load","coherence","curiosity"
        ])

    def log(self, dt: float, agent: Agent):
        if not self.enabled or self.writer is None:
            return
        t = (pygame.time.get_ticks() / 1000.0) - self.t0
        spd = agent.vel.length()
        cz = agent.current_zone
        commit = agent.commit_zone.name if agent.commit_zone else "None"
        s = agent.state
        self.writer.writerow([
            f"{t:.4f}", f"{dt:.4f}",
            agent.agent_id, agent.profile.name,
            f"{agent.pos.x:.2f}", f"{agent.pos.y:.2f}",
            f"{agent.vel.x:.2f}", f"{agent.vel.y:.2f}",
            f"{spd:.2f}",
            cz, commit, agent.commit_ticks, agent.dwell_ticks,
            f"{s.energy:.4f}", f"{s.load:.4f}", f"{s.coherence:.4f}", f"{s.curiosity:.4f}"
        ])

    def close(self):
        if self.fp:
            try:
                self.fp.flush()
                self.fp.close()
            except Exception:
                pass
        self.fp = None
        self.writer = None

# -------------------------
# Drawing
# -------------------------
def draw_hud(screen: pygame.Surface, font: pygame.font.Font, agents: List[Agent], hud_on: bool, telemetry: TelemetryWriter):
    if not hud_on:
        return

    lines = [
        "SPACE Play/Pause | N Step | O HUD | T Telemetry | R Reset",
        f"Agents: {', '.join([a.profile.name for a in agents])}",
    ]
    if telemetry.enabled and telemetry.path:
        lines.append(f"telemetry: ON -> {telemetry.path}")
    else:
        lines.append("telemetry: OFF")

    y = 12
    for i, t in enumerate(lines):
        col = TXT if i < 2 else SUBTXT
        surf = font.render(t, True, col)
        screen.blit(surf, (12, y))
        y += 22

    # small per-agent readout (compact)
    y += 6
    for a in agents:
        s = a.state
        commit = a.commit_zone.name if a.commit_zone else "-"
        t = f"{a.profile.name:<8} Z:{a.current_zone:<10} commit:{commit}({a.commit_ticks:>2}) D:{a.dwell_ticks:>3}  E:{s.energy:.2f} L:{s.load:.2f} C:{s.coherence:.2f} Q:{s.curiosity:.2f}"
        screen.blit(font.render(t, True, SUBTXT), (12, y))
        y += 20

def draw_world(screen: pygame.Surface, zones: List[Zone], agents: List[Agent]):
    screen.fill(BG)

    # zones
    for z in zones:
        rounded_rect(screen, z.rect, z.color, radius=26, width=0)
        r_in = inner_rect(z.rect, SOFT_EDGE_MARGIN)
        rounded_rect(screen, r_in, (245, 245, 248), radius=20, width=2)

    # draw trails then agents
    for a in agents:
        # trail length scales with energy (fish longer when energetic)
        max_len = int(14 + 95 * a.state.energy)
        if len(a.trail) > max_len:
            del a.trail[:-max_len]

        c = TRAIL_COLORS.get(a.profile.name, (175, 255, 220))
        for i in range(1, len(a.trail)):
            pygame.draw.line(screen, c, a.trail[i - 1], a.trail[i], width=2)

    for a in agents:
        col = AGENT_COLORS.get(a.profile.name, (210, 255, 230))
        pygame.draw.circle(screen, col, (int(a.pos.x), int(a.pos.y)), 8)

        # "nose" direction hint (short when slow)
        spd = a.vel.length()
        nose_len = max(7.0, min(18.0, spd * 0.14))
        if spd > 0.5:
            n = safe_normalize(a.vel)
            tip = a.pos + n * nose_len
            pygame.draw.line(screen, col, a.pos, tip, width=3)

# -------------------------
# Reset helper
# -------------------------
def spawn_agents(zones: List[Zone]) -> List[Agent]:
    zmap = {z.name: z for z in zones}

    # start all near Library-ish but separated
    a_fast = Agent(
        agent_id="A1",
        profile=PROFILES["FAST_ANT"],
        pos=v2(235, 310),
        vel=v2(0, 0),
        target=v2(235, 310),
    )
    a_slow = Agent(
        agent_id="A2",
        profile=PROFILES["SLOW_ANT"],
        pos=v2(280, 340),
        vel=v2(0, 0),
        target=v2(280, 340),
    )
    fish = Agent(
        agent_id="F1",
        profile=PROFILES["FISH"],
        pos=v2(255, 270),
        vel=v2(0, 0),
        target=v2(255, 270),
    )

    # initial commits
    for a in (a_fast, a_slow, fish):
        a.commit_zone = zmap["Library"]
        a.commit_ticks = random.randint(a.profile.commit_min, a.profile.commit_max)
        a.last_choice = "Library"
        a.target = pick_point_in_zone(a.commit_zone, pad=60)
        a.trail = [a.pos.copy()]

    return [a_fast, a_slow, fish]

# -------------------------
# Main
# -------------------------
def main():
    pygame.init()
    pygame.display.set_caption("ORPIN / MOS Sandbox Town v1.1.14 — Three Agents Ecosystem (Standalone)")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 18)

    zones = build_zones()
    agents = spawn_agents(zones)

    hud_on = True
    running = True
    sim_running = True
    step_once = False

    telemetry = TelemetryWriter(enabled=True)
    telemetry.start()

    while running:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, DT_CLAMP)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    sim_running = not sim_running
                elif event.key == pygame.K_n:
                    step_once = True
                elif event.key == pygame.K_o:
                    hud_on = not hud_on
                elif event.key == pygame.K_r:
                    agents = spawn_agents(zones)
                elif event.key == pygame.K_t:
                    # toggle telemetry
                    telemetry.close()
                    telemetry.enabled = not telemetry.enabled
                    if telemetry.enabled:
                        telemetry = TelemetryWriter(enabled=True)
                        telemetry.start()
                    else:
                        telemetry = TelemetryWriter(enabled=False)

        if sim_running or step_once:
            for a in agents:
                before = a.pos.copy()
                update_agent(a, zones, dt)

                # only add to trail if moved enough
                if (a.pos - before).length() >= a.profile.trail_move_eps:
                    a.trail.append(a.pos.copy())

                telemetry.log(dt, a)

            step_once = False

        draw_world(screen, zones, agents)
        draw_hud(screen, font, agents, hud_on, telemetry)
        pygame.display.flip()

    telemetry.close()
    pygame.quit()

if __name__ == "__main__":
    main()
