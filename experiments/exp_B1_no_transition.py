import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import math
import os
import csv
import random
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

import pygame

from profiles import get_profile, MotionProfile

W, H = 980, 560
FPS = 60

BG = (16, 16, 18)
TXT = (235, 235, 235)
SUBTXT = (190, 190, 195)

COLOR_LIBRARY = (45, 140, 215)
COLOR_PARK = (85, 190, 105)
COLOR_TRANSITION = (175, 175, 180)
COLOR_REST = (205, 195, 160)

AGENT_A_COLOR = (210, 255, 230)  # fish
AGENT_B_COLOR = (255, 230, 210)  # ant (fast)
AGENT_C_COLOR = (200, 220, 255)  # ant (slow)
AGENT_D_COLOR = (255, 255, 200)  # bird


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
    return os.path.join(out_dir, f"run_{ts}_ecosystem.csv")


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

    current_zone: str = "None"
    dwell_ticks: int = 0
    paused: bool = False

    # ANT pause
    pause_hold_ticks: int = 0
    pause_cooldown_ticks: int = 0

    # ANT commit
    commit_zone: Optional[Zone] = None
    commit_ticks: int = 0
    last_choice: str = "None"

    # FISH pause (seconds)
    fish_pause_hold_s: float = 0.0
    fish_pause_cooldown_s: float = 0.0
    fish_edge_pause_latch: bool = False

    # FISH leaving lock
    fish_leaving_lock_ticks: int = 0

    # FISH commit
    fish_commit_zone: Optional[str] = None
    fish_commit_ticks_left: int = 0
    fish_commit_cooldown_ticks: int = 0

    # Trails (each agent owns its trail)
    trail: List[pygame.Vector2] = field(default_factory=list)


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
 #  transition = Zone(
 #      "Transition",
 #      pygame.Rect(420, 285, 160, 90),
 #       {"energy": -0.010, "load": -0.010, "coherence": +0.006, "curiosity": +0.002},
 #      COLOR_TRANSITION,
 #      pause_bias=1.30,
 #      commit_bias=0.60,
 #  )
    rest = Zone(
        "Rest",
        pygame.Rect(430, 395, 140, 70),
        {"energy": +0.012, "load": -0.018, "coherence": +0.020, "curiosity": -0.004},
        COLOR_REST,
        pause_bias=1.55,
        commit_bias=0.55,
    )
    return [library, park, rest]


def zone_at(zones: List[Zone], pos: pygame.Vector2) -> Optional[Zone]:
    for z in zones:
        if z.contains(pos):
            return z
    return None


# ✅ pad auto-shrinks for small zones (Transition/Rest safe)
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


# -------------------------
# ANT model
# -------------------------
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


def decide_target_zone_ant(agent: Agent, zones: List[Zone]) -> Zone:
    p = agent.profile
    zmap = {z.name: z for z in zones}

    s = agent.state
    score_park = (1.0 - s.energy) * 1.25 + s.load * 1.20 + (1.0 - s.coherence) * 0.15
    score_lib = s.curiosity * 1.10 + s.coherence * 0.75 - s.load * 0.30
    score_trans = (1.0 - s.coherence) * 1.25 + s.load * 0.35
    score_rest = (1.0 - s.energy) * 0.55 + s.load * 0.85 + (1.0 - s.coherence) * 0.25

    scores = {"Park": score_park, "Library": score_lib, "Transition": score_trans, "Rest": score_rest}

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


# -------------------------
# FISH model (v1.1.7 port)
# -------------------------
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


def pick_commit_zone_fish(agent: Agent, zones: List[Zone]) -> Optional[str]:
    p = agent.profile
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
        for name, wv in weights.items():
            acc += wv
            if r <= acc:
                return name
    return None


def decide_target_fish(agent: Agent, zones: List[Zone]) -> pygame.Vector2:
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


def update_agent_fish(agent: Agent, zones: List[Zone], dt: float):
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
            agent.fish_commit_cooldown_ticks = random.randint(p.fish_commit_cooldown_min, p.fish_commit_cooldown_max)

    z = zone_at(zones, agent.pos)
    zname = z.name if z else "None"
    if zname == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = zname
        agent.dwell_ticks = 0

    apply_zone_effects(agent, z, dt)
    maybe_edge_pause_fish(agent, z)

    if agent.fish_commit_zone is None and agent.fish_commit_ticks_left <= 0:
        cz = pick_commit_zone_fish(agent, zones)
        if cz is not None:
            agent.fish_commit_zone = cz
            agent.fish_commit_ticks_left = random.randint(p.fish_commit_min, p.fish_commit_max)

    if (agent.dwell_ticks % 8 == 0 or agent.target.length_squared() == 0):
        agent.target = decide_target_fish(agent, zones)

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


# -------------------------
# Draw
# -------------------------
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

        # Trails for all non-fish
        if a.profile.model != "fish":
            max_len = int(18 + 90 * a.state.energy)
            if len(a.trail) > max_len:
                del a.trail[:-max_len]
            for i in range(1, len(a.trail)):
                pygame.draw.line(screen, col, a.trail[i - 1], a.trail[i], width=2)
        else:
            streak_len = 22
            if a.vel.length() > 0.5:
                dirv = a.vel.normalize()
            else:
                dirv = pygame.Vector2(1, 0)
            start = a.pos - dirv * streak_len
            end = a.pos
            pygame.draw.line(screen, col, start, end, width=3)

        pygame.draw.circle(screen, col, (int(a.pos.x), int(a.pos.y)), 8)


def draw_hud(screen: pygame.Surface, font: pygame.font.Font, hud_on: bool, agents: List[Agent], csv_path: str):
    if not hud_on:
        return

    lines = [
        "SPACE Play/Pause | N Step | O HUD | ESC Quit",
        f"telemetry: {csv_path}",
        "Agents: A=FISH  B=ANT_FAST  C=ANT_SLOW  D=BIRD_GLIDE",
    ]

    y = 12
    for ln in lines:
        screen.blit(font.render(ln, True, TXT), (12, y))
        y += 22

    for a in agents:
        s = a.state
        line = f"{a.agent_id}  {a.profile.name:<12}  Z:{a.current_zone:<10}  D:{a.dwell_ticks:>3}  paused:{'1' if a.paused else '0'}  E:{s.energy:.2f} L:{s.load:.2f} C:{s.coherence:.2f} Q:{s.curiosity:.2f}"
        screen.blit(font.render(line, True, SUBTXT), (12, y))
        y += 20


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("ORPIN / MOS Sandbox Town — Ecosystem (Fish + Ants + Bird)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 18)

    zones = [z for z in build_zones() if z.name != "Transition"]
    zmap = {z.name: z for z in zones}

    # Profiles
    fish_profile = get_profile("fish")
    ant_fast_profile = get_profile("ant_fast")
    ant_slow_profile = get_profile("ant_slow")
    bird_profile = get_profile("bird")  # fish-like bird but ant engine

    # Agents
    fish = Agent(agent_id="A", profile=fish_profile, pos=v2(250, 310), vel=v2(0, 0), target=zmap["Library"].center())
    ant_fast = Agent(agent_id="B", profile=ant_fast_profile, pos=v2(720, 310), vel=v2(0, 0), target=zmap["Park"].center())
    ant_slow = Agent(agent_id="C", profile=ant_slow_profile, pos=v2(700, 360), vel=v2(0, 0), target=zmap["Park"].center())
    bird = Agent(agent_id="D", profile=bird_profile, pos=v2(500, 240), vel=v2(0, 0), target=zmap["Library"].center())

    # init ant commits + trails (includes bird because it is ant model)
    for ant in (ant_fast, ant_slow, bird):
        ant.commit_zone = zmap["Library"]
        ant.commit_ticks = random.randint(ant.profile.commit_min, ant.profile.commit_max)
        ant.last_choice = "Library"
        ant.target = pick_point_in_zone(ant.commit_zone, pad=55)
        ant.trail = [ant.pos.copy()]

    fish.trail = []

    agents = [fish, ant_fast, ant_slow, bird]

    running = True
    tick_running = True
    step_once = False
    hud_on = True

    csv_path = ensure_telemetry_paths()
    f = open(csv_path, "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow([
        "t_sec","dt","agent_id",
        "x","y","vx","vy","speed",
        "zone","commit_zone","commit_left","dwell_ticks",
        "energy","load","coherence","curiosity",
        "profile","model"
    ])

    t_sec = 0.0

    try:
        while running:
            dt = clock.tick(FPS) / 1000.0
            dt = min(dt, min(a.profile.dt_clamp for a in agents))

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

            ran = tick_running or step_once
            if ran:
                t_sec += dt
                for agent in agents:
                    before = agent.pos.copy()

                    if agent.profile.model == "fish":
                        update_agent_fish(agent, zones, dt)
                    else:
                        update_agent_ant(agent, zones, dt)
                        if (agent.pos - before).length() >= agent.profile.trail_move_eps:
                            agent.trail.append(agent.pos.copy())

                    s = agent.state
                    speed = agent.vel.length()

                    if agent.profile.model == "fish":
                        commit_zone = agent.fish_commit_zone if agent.fish_commit_zone else "-"
                        commit_left = agent.fish_commit_ticks_left
                    else:
                        commit_zone = agent.commit_zone.name if agent.commit_zone else "-"
                        commit_left = agent.commit_ticks

                    w.writerow([
                        round(t_sec, 4), round(dt, 4), agent.agent_id,
                        round(agent.pos.x, 2), round(agent.pos.y, 2),
                        round(agent.vel.x, 2), round(agent.vel.y, 2),
                        round(speed, 2),
                        agent.current_zone, commit_zone, commit_left, agent.dwell_ticks,
                        round(s.energy, 4), round(s.load, 4), round(s.coherence, 4), round(s.curiosity, 4),
                        agent.profile.name, agent.profile.model
                    ])

                step_once = False

            draw_world(screen, zones, agents)
            draw_hud(screen, font, hud_on, agents, csv_path)
            pygame.display.flip()

    finally:
        f.close()
        pygame.quit()


if __name__ == "__main__":
    main()
