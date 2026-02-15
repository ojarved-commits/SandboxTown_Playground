# ORPIN / MOS Sandbox Town v1.1.11
# Profiles split to src/profiles.py (Fish / Ant) + Telemetry + CrawlTrail

import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List, Tuple

import pygame

from profiles import get_profile, PROFILES, MotionProfile

W, H = 980, 560
FPS = 60

BG = (16, 16, 18)
TXT = (235, 235, 235)
SUBTXT = (190, 190, 195)

COLOR_LIBRARY = (45, 140, 215)
COLOR_PARK = (85, 190, 105)
COLOR_TRANSITION = (175, 175, 180)
COLOR_REST = (205, 195, 160)

AGENT_COLOR = (210, 255, 230)


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


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
class Agent:
    pos: pygame.Vector2
    vel: pygame.Vector2
    target: pygame.Vector2
    state: AgentState = field(default_factory=AgentState)

    current_zone: str = "None"
    dwell_ticks: int = 0

    pause_hold: int = 0
    pause_cooldown: int = 0

    commit_zone: Optional[Zone] = None
    commit_ticks: int = 0

    last_choice: str = "None"


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


def dwell_ramp(agent: Agent, p: MotionProfile) -> float:
    return min(p.dwell_ramp_cap, 1.0 + agent.dwell_ticks * p.dwell_ramp_rate)


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
    if z.name not in ("Transition", "Rest"):
        return 1.0
    cx, cy = z.rect.center
    dx = (pos.x - cx) / max(1.0, z.rect.width / 2)
    dy = (pos.y - cy) / max(1.0, z.rect.height / 2)
    d = math.sqrt(dx * dx + dy * dy)
    return max(0.35, 1.15 - d)


def decide_target_zone(agent: Agent, zones: List[Zone], p: MotionProfile) -> Zone:
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

    scores = {"Park": score_park, "Library": score_lib, "Transition": score_trans, "Rest": score_rest}

    best_name = max(scores.keys(), key=lambda k: scores[k])
    best_score = scores[best_name]

    if agent.last_choice in scores and agent.last_choice in zmap:
        last_score = scores[agent.last_choice]
        if best_name != agent.last_choice and (best_score - last_score) < p.hysteresis_eps:
            best_name = agent.last_choice

    return zmap.get(best_name, trans)


def edge_pause_check(agent: Agent, prev_zone: Optional[Zone], now_zone: Optional[Zone], p: MotionProfile):
    if agent.pause_cooldown > 0:
        agent.pause_cooldown -= 1
        return

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

    if prev_zone.contains(agent.pos) and not prev_zone.soft_contains(agent.pos, p.soft_edge_margin):
        agent.pause_hold = p.edge_pause_ticks
        agent.pause_cooldown = p.edge_pause_cooldown


def update_agent(agent: Agent, zones: List[Zone], dt: float, p: MotionProfile):
    if agent.pause_hold > 0:
        agent.pause_hold -= 1
        agent.vel *= 0.88
        return

    prev_zone = next((z for z in zones if z.name == agent.current_zone), None) if agent.current_zone != "None" else None
    now_zone = zone_at(zones, agent.pos)
    now_name = now_zone.name if now_zone else "None"

    if now_name == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = now_name
        agent.dwell_ticks = 0

    edge_pause_check(agent, prev_zone, now_zone, p)

    if now_zone:
        ramp = dwell_ramp(agent, p)
        soft = soft_edge_factor(now_zone, agent.pos, p.soft_edge_margin)
        expo = exposure_factor(now_zone, agent.pos)
        strength = ramp * soft * expo

        st = agent.state
        st.energy = clamp01(st.energy + now_zone.deltas.get("energy", 0.0) * strength * dt * 60.0)
        st.load = clamp01(st.load + now_zone.deltas.get("load", 0.0) * strength * dt * 60.0)
        st.coherence = clamp01(st.coherence + now_zone.deltas.get("coherence", 0.0) * strength * dt * 60.0)
        st.curiosity = clamp01(st.curiosity + now_zone.deltas.get("curiosity", 0.0) * strength * dt * 60.0)

    # Commit
    if agent.commit_ticks <= 0 or agent.commit_zone is None:
        chosen = decide_target_zone(agent, zones, p)
        agent.last_choice = chosen.name
        agent.commit_zone = chosen
        agent.commit_ticks = random.randint(p.commit_min, p.commit_max)
        agent.target = pick_point_in_zone(chosen, pad=55)
    else:
        agent.commit_ticks -= 1

    # Fish-like retarget + orbit impulse (profile-controlled)
    if agent.commit_zone and agent.commit_zone.contains(agent.pos):
        if random.random() < p.inside_zone_retarget_p:
            agent.target = pick_point_in_zone(agent.commit_zone, pad=55)
        if random.random() < p.orbit_impulse_p:
            agent.target += v2(random.randint(-90, 90), random.randint(-60, 60))

    to_target = agent.target - agent.pos
    desired = safe_normalize(to_target)

    ang = random.random() * math.tau
    wander = v2(math.cos(ang), math.sin(ang))
    desired = safe_normalize(desired + p.wander_mix * wander)

    # speed with crawl minimum
    speed = p.base_speed * (0.35 + 1.05 * agent.state.energy)
    speed = max(p.crawl_speed_min, speed)

    steer = desired * speed
    agent.vel = agent.vel.lerp(steer, 0.08)
    agent.pos += agent.vel * dt

    agent.pos.x = max(20, min(W - 20, agent.pos.x))
    agent.pos.y = max(20, min(H - 20, agent.pos.y))


def draw_hud(screen: pygame.Surface, font: pygame.font.Font, agent: Agent, hud_on: bool, p: MotionProfile, csv_path: str):
    if not hud_on:
        return

    s = agent.state
    zone = agent.current_zone
    commit = agent.commit_zone.name if agent.commit_zone else "-"
    d = agent.dwell_ticks

    lines = [
        "SPACE Play/Pause | N Step | O HUD | 1 Fish | 2 Ant",
        f"RUNNING   Z:{zone:<10}   commit:{commit}({agent.commit_ticks:>2})   D:{d}   profile:{p.key}",
        f"E:{s.energy:.2f}  L:{s.load:.2f}  C:{s.coherence:.2f}  Q:{s.curiosity:.2f}",
        f"{p.title}  margin:{p.soft_edge_margin}  crawl:{p.crawl_speed_min}  wander:{p.wander_mix:.2f}",
        f"telemetry: ON  ->  {csv_path}",
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

    # trail length scales with energy
    max_len = int(18 + 90 * agent.state.energy)
    if len(trail) > max_len:
        del trail[:-max_len]

    for i in range(1, len(trail)):
        a = trail[i - 1]
        b = trail[i]
        pygame.draw.line(screen, (175, 255, 220), a, b, width=2)

    pygame.draw.circle(screen, AGENT_COLOR, (int(agent.pos.x), int(agent.pos.y)), 8)

    spd = agent.vel.length()
    nose_len = max(8.0, min(18.0, spd * 0.15))
    if spd > 0.5:
        n = safe_normalize(agent.vel)
        tip = agent.pos + n * nose_len
        pygame.draw.line(screen, (160, 255, 210), agent.pos, tip, width=3)


def ensure_telemetry_paths() -> str:
    # Keeps it simple and avoids the double-telemetry folder confusion.
    # Output: <project>/telemetry/runs/run_YYYYMMDD_HHMMSS.csv
    out_dir = os.path.join("telemetry", "runs")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(out_dir, f"run_{ts}.csv")


def main():
    pygame.init()

    # start profile
    active_key = "fish"
    p = get_profile(active_key)

    pygame.display.set_caption(f"ORPIN / MOS Sandbox Town v1.1.11 ({p.title}) + Telemetry")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 18)

    zones = build_zones()
    zmap = {z.name: z for z in zones}

    agent = Agent(pos=v2(250, 310), vel=v2(0, 0), target=v2(250, 310))
    agent.commit_zone = zmap["Library"]
    agent.commit_ticks = random.randint(p.commit_min, p.commit_max)
    agent.last_choice = "Library"
    agent.target = pick_point_in_zone(agent.commit_zone, pad=60)

    hud_on = True
    running = True
    sim_running = True
    step_once = False

    trail: List[pygame.Vector2] = [agent.pos.copy()]

    # Telemetry
    csv_path = ensure_telemetry_paths()
    f = open(csv_path, "w", encoding="utf-8")
    f.write("t_sec,dt,x,y,vx,vy,speed,zone,commit_zone,commit_ticks,dwell_ticks,energy,load,coherence,curiosity,profile\n")
    t = 0.0

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
                        sim_running = not sim_running
                    elif event.key == pygame.K_n:
                        step_once = True
                    elif event.key == pygame.K_o:
                        hud_on = not hud_on

                    # profile switching
                    elif event.key == pygame.K_1:
                        active_key = "fish"
                        p = get_profile(active_key)
                        pygame.display.set_caption(f"ORPIN / MOS Sandbox Town v1.1.11 ({p.title}) + Telemetry")
                    elif event.key == pygame.K_2:
                        active_key = "ant"
                        p = get_profile(active_key)
                        pygame.display.set_caption(f"ORPIN / MOS Sandbox Town v1.1.11 ({p.title}) + Telemetry")

            if sim_running or step_once:
                before = agent.pos.copy()
                update_agent(agent, zones, dt, p)

                if (agent.pos - before).length() >= p.trail_move_eps:
                    trail.append(agent.pos.copy())

                # telemetry row
                t += dt
                s = agent.state
                cz = agent.current_zone
                commit = agent.commit_zone.name if agent.commit_zone else "None"
                spd = agent.vel.length()
                f.write(
                    f"{t:.4f},{dt:.4f},{agent.pos.x:.2f},{agent.pos.y:.2f},"
                    f"{agent.vel.x:.2f},{agent.vel.y:.2f},{spd:.2f},"
                    f"{cz},{commit},{agent.commit_ticks},{agent.dwell_ticks},"
                    f"{s.energy:.4f},{s.load:.4f},{s.coherence:.4f},{s.curiosity:.4f},"
                    f"{p.key}\n"
                )

                step_once = False

            draw_world(screen, zones, agent, trail, p)
            draw_hud(screen, font, agent, hud_on, p, csv_path)
            pygame.display.flip()

    finally:
        f.close()
        pygame.quit()


if __name__ == "__main__":
    main()
