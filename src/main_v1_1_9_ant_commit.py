import os
import csv
import math
import random
from dataclasses import dataclass, field
from datetime import datetime

import pygame


# =========================================================
# Telemetry
# =========================================================

class TelemetryLogger:
    def __init__(self, base_dir: str = "telemetry/runs", enabled: bool = True):
        self.enabled = enabled
        self.base_dir = base_dir
        self.fp = None
        self.writer = None
        self.path = None

        if not self.enabled:
            return

        os.makedirs(self.base_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(self.base_dir, f"run_{ts}.csv")
        self.fp = open(self.path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.fp)

        self.writer.writerow([
            "tick",
            "t_sec",
            "zone",
            "commit_zone",
            "commit_left",
            "paused",
            "energy",
            "load",
            "coherence",
            "curiosity",
            "x",
            "y",
            "vx",
            "vy",
            "speed",
            "dwell_ticks",
        ])
        self.fp.flush()

    def log(self, tick: int, t_sec: float, agent, zone_name: str):
        if not self.enabled or self.writer is None:
            return

        vx, vy = agent.vel.x, agent.vel.y
        speed = math.hypot(vx, vy)

        self.writer.writerow([
            tick,
            round(t_sec, 4),
            zone_name,
            agent.commit_zone or "",
            int(agent.commit_left),
            int(agent.paused),
            round(agent.state.energy, 4),
            round(agent.state.load, 4),
            round(agent.state.coherence, 4),
            round(agent.state.curiosity, 4),
            round(agent.pos.x, 3),
            round(agent.pos.y, 3),
            round(vx, 4),
            round(vy, 4),
            round(speed, 4),
            int(agent.dwell_ticks),
        ])

        # Keep writes reliable on Windows (still fast enough at this scale)
        if tick % 30 == 0:
            self.fp.flush()

    def close(self):
        if self.fp:
            try:
                self.fp.flush()
            except Exception:
                pass
            try:
                self.fp.close()
            except Exception:
                pass
        self.fp = None
        self.writer = None


# =========================================================
# World / Agent
# =========================================================

WIDTH, HEIGHT = 980, 560
FPS = 60

SOFT_EDGE_MARGIN = 35  # tweak: 25 = deeper entries, 70 = shallower entries
HYSTERESIS_BAND = 18   # extra stability band to prevent edge flicker/ping-pong

# Commit logic
COMMIT_MIN = 45
COMMIT_MAX = 95
COMMIT_TRIGGER_DWELL = 18  # must dwell this long before committing

# Movement feel
BASE_SPEED = 160.0
WANDER_STRENGTH = 0.60     # how “fish/ant-ish” the curvature is
RETURN_STRENGTH = 0.06     # pull toward target
ORBIT_STRENGTH = 0.03      # adds gentle side-curvature
CRAWL_PULSE = 32.0         # stop-go cadence when low energy

# Trail scaling
TRAIL_MIN = 8
TRAIL_MAX = 46


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def rect_inflate(r: pygame.Rect, margin: int) -> pygame.Rect:
    rr = r.copy()
    rr.inflate_ip(-margin * 2, -margin * 2)
    return rr


@dataclass
class Zone:
    name: str
    rect: pygame.Rect
    # per-second effects (scaled by dt)
    d_energy: float = 0.0
    d_load: float = 0.0
    d_coherence: float = 0.0
    d_curiosity: float = 0.0


@dataclass
class AgentState:
    energy: float = 0.65     # 0..1
    load: float = 0.30       # 0..1
    coherence: float = 1.00  # 0..1
    curiosity: float = 0.85  # 0..1


@dataclass
class Agent:
    pos: pygame.Vector2
    vel: pygame.Vector2
    target: pygame.Vector2
    state: AgentState = field(default_factory=AgentState)

    current_zone: str = "None"
    dwell_ticks: int = 0

    paused: bool = False
    pause_hold: int = 0
    pause_cooldown: int = 0

    commit_zone: str | None = None
    commit_left: int = 0

    # internal motion phase
    wander_phase: float = 0.0
    crawl_phase: float = 0.0

    trail: list = field(default_factory=list)


def build_zones() -> list[Zone]:
    # Layout: Blue (Library) left, Green (Park) right, Grey (Transition) center
    library = Zone(
        "Library",
        pygame.Rect(90, 150, 330, 300),
        d_energy=-0.16,
        d_load=+0.10,
        d_coherence=+0.02,
        d_curiosity=+0.03,
    )
    park = Zone(
        "Park",
        pygame.Rect(560, 150, 330, 300),
        d_energy=+0.22,
        d_load=-0.10,
        d_coherence=+0.02,
        d_curiosity=-0.01,
    )
    transition = Zone(
        "Transition",
        pygame.Rect(440, 250, 140, 100),
        d_energy=-0.02,
        d_load=-0.02,
        d_coherence=+0.01,
        d_curiosity=+0.00,
    )
    # Optional extra: a “Rest Stop” small pill under transition (already in your visuals sometimes)
    rest = Zone(
        "Rest",
        pygame.Rect(458, 372, 104, 70),
        d_energy=+0.10,
        d_load=-0.06,
        d_coherence=+0.03,
        d_curiosity=-0.02,
    )
    return [library, park, transition, rest]


def zone_at(pos: pygame.Vector2, zones: list[Zone], margin: int) -> Zone | None:
    for z in zones:
        inner = rect_inflate(z.rect, margin)
        if inner.width <= 0 or inner.height <= 0:
            inner = z.rect
        if inner.collidepoint(pos.x, pos.y):
            return z
    return None


def stable_zone(agent: Agent, zones: list[Zone], margin: int) -> Zone | None:
    """
    Soft edges + hysteresis:
    - If we have a current zone, we keep it until we are clearly out of it
      (using a slightly smaller inflate to create a band).
    """
    # If currently in a zone, keep it unless we exit a smaller "stay" region
    if agent.current_zone and agent.current_zone != "None":
        z_cur = next((z for z in zones if z.name == agent.current_zone), None)
        if z_cur:
            stay_margin = margin + HYSTERESIS_BAND
            stay_rect = rect_inflate(z_cur.rect, stay_margin)
            if stay_rect.width <= 0 or stay_rect.height <= 0:
                stay_rect = z_cur.rect
            if stay_rect.collidepoint(agent.pos.x, agent.pos.y):
                return z_cur

    # Otherwise choose zone normally
    return zone_at(agent.pos, zones, margin)


def rand_point_in_zone(z: Zone, margin: int) -> pygame.Vector2:
    inner = rect_inflate(z.rect, margin)
    if inner.width <= 10 or inner.height <= 10:
        inner = z.rect
    x = random.uniform(inner.left + 10, inner.right - 10)
    y = random.uniform(inner.top + 10, inner.bottom - 10)
    return pygame.Vector2(x, y)


def decide_target(agent: Agent, zones: list[Zone], margin: int) -> tuple[pygame.Vector2, Zone | None]:
    """
    Decide next target point.
    Returns (target_point, chosen_zone_or_None)
    """
    # If committed, wander within commit zone
    if agent.commit_zone and agent.commit_left > 0:
        z = next((zz for zz in zones if zz.name == agent.commit_zone), None)
        if z:
            return rand_point_in_zone(z, margin), z
        # If commit zone missing, drop commit safely
        agent.commit_zone = None
        agent.commit_left = 0

    # Not committed: pick based on state bias
    # Bias: if energy low -> prefer Park/Rest, if load high -> prefer Park/Rest, else explore Library/Transition
    park = next((z for z in zones if z.name == "Park"), None)
    library = next((z for z in zones if z.name == "Library"), None)
    rest = next((z for z in zones if z.name == "Rest"), None)
    transition = next((z for z in zones if z.name == "Transition"), None)

    e = agent.state.energy
    l = agent.state.load

    wants_recover = (e < 0.45) or (l > 0.55)
    wants_explore = (e > 0.55) and (l < 0.55)

    choices: list[Zone] = []
    if wants_recover:
        if park: choices.extend([park, park])
        if rest: choices.append(rest)
        if transition: choices.append(transition)
        if library: choices.append(library)
    elif wants_explore:
        if library: choices.extend([library, library])
        if transition: choices.append(transition)
        if park: choices.append(park)
        if rest: choices.append(rest)
    else:
        # balanced
        for z in [library, transition, park, rest]:
            if z: choices.append(z)

    if not choices:
        return agent.target, None

    z_pick = random.choice(choices)
    return rand_point_in_zone(z_pick, margin), z_pick


def update_agent(agent: Agent, zones: list[Zone], dt: float, margin: int):
    # Update zone + dwell
    z = stable_zone(agent, zones, margin)
    zone_name = z.name if z else "None"

    if zone_name == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = zone_name
        agent.dwell_ticks = 0

    # Effects
    if z:
        agent.state.energy = clamp(agent.state.energy + z.d_energy * dt, 0.0, 1.0)
        agent.state.load = clamp(agent.state.load + z.d_load * dt, 0.0, 1.0)
        agent.state.coherence = clamp(agent.state.coherence + z.d_coherence * dt, 0.0, 1.0)
        agent.state.curiosity = clamp(agent.state.curiosity + z.d_curiosity * dt, 0.0, 1.0)

    # Commit trigger
    if agent.commit_left <= 0 and agent.dwell_ticks >= COMMIT_TRIGGER_DWELL and z and z.name in ("Library", "Park"):
        # Probabilistic commit (more likely as dwell increases)
        p = clamp(0.25 + (agent.dwell_ticks - COMMIT_TRIGGER_DWELL) * 0.02, 0.25, 0.85)
        if random.random() < p:
            agent.commit_zone = z.name
            agent.commit_left = random.randint(COMMIT_MIN, COMMIT_MAX)

    # Commit countdown
    if agent.commit_left > 0:
        agent.commit_left -= 1
        if agent.commit_left <= 0:
            agent.commit_left = 0
            agent.commit_zone = None

    # Pause-like “traffic check” at boundaries (lightweight)
    # When changing zones: brief hold, scaled by load and low energy
    if agent.dwell_ticks == 0 and agent.current_zone != "None":
        if agent.pause_cooldown <= 0:
            base = 6
            extra = int(10 * clamp(agent.state.load, 0.0, 1.0)) + int(10 * (1.0 - agent.state.energy))
            agent.pause_hold = base + random.randint(0, extra)
            agent.pause_cooldown = 25  # prevents constant pausing

    if agent.pause_cooldown > 0:
        agent.pause_cooldown -= 1

    # Select / refresh target
    # If close to target, pick new target
    if agent.pos.distance_to(agent.target) < 18:
        agent.target, _zpick = decide_target(agent, zones, margin)

    # Movement: energy scales speed + wander
    e = agent.state.energy
    speed = BASE_SPEED * lerp(0.35, 1.15, e)  # low energy = slower crawl

    # Crawl pulse when very low energy
    agent.crawl_phase += dt * CRAWL_PULSE
    crawl_gate = 1.0
    if e < 0.28:
        crawl_gate = 0.35 + 0.65 * max(0.0, math.sin(agent.crawl_phase))

    # Wander phase
    agent.wander_phase += dt * (0.9 + 1.6 * e)
    wander = WANDER_STRENGTH * (0.35 + 0.65 * e)
    orbit = ORBIT_STRENGTH * (0.35 + 0.65 * e)

    # Steering
    to_t = (agent.target - agent.pos)
    dist = max(1.0, to_t.length())
    dir_to = to_t / dist

    # add a gentle perpendicular “orbit” (fish/ant curve)
    perp = pygame.Vector2(-dir_to.y, dir_to.x)

    # noise-ish wander (sine/cos)
    w = pygame.Vector2(math.cos(agent.wander_phase), math.sin(agent.wander_phase))

    desired = dir_to * RETURN_STRENGTH + perp * orbit + w * wander
    if desired.length() > 0:
        desired = desired.normalize()

    desired_vel = desired * speed * crawl_gate

    # Edge pause hold overrides movement briefly
    if agent.pause_hold > 0:
        agent.pause_hold -= 1
        desired_vel *= 0.15  # still drifts slightly (feels alive)

    # Smooth velocity (dt-stable)
    alpha = clamp(dt * 6.5, 0.0, 1.0)
    agent.vel.x = lerp(agent.vel.x, desired_vel.x, alpha)
    agent.vel.y = lerp(agent.vel.y, desired_vel.y, alpha)

    # Integrate
    agent.pos += agent.vel * dt

    # Keep inside window
    agent.pos.x = clamp(agent.pos.x, 10, WIDTH - 10)
    agent.pos.y = clamp(agent.pos.y, 10, HEIGHT - 10)

    # Trail length scales with energy
    trail_len = int(lerp(TRAIL_MIN, TRAIL_MAX, e))
    agent.trail.append((agent.pos.x, agent.pos.y))
    if len(agent.trail) > trail_len:
        agent.trail = agent.trail[-trail_len:]


# =========================================================
# Render
# =========================================================

def draw_round_rect(surf: pygame.Surface, rect: pygame.Rect, color, radius: int):
    pygame.draw.rect(surf, color, rect, border_radius=radius)

def draw_zone_visuals(surf: pygame.Surface, zones: list[Zone]):
    for z in zones:
        if z.name == "Library":
            draw_round_rect(surf, z.rect, (30, 125, 190), 28)
            inner = z.rect.inflate(-70, -70)
            pygame.draw.rect(surf, (240, 240, 240), inner, width=2, border_radius=22)
        elif z.name == "Park":
            draw_round_rect(surf, z.rect, (90, 170, 90), 28)
            inner = z.rect.inflate(-70, -70)
            pygame.draw.rect(surf, (240, 240, 240), inner, width=2, border_radius=22)
        elif z.name == "Transition":
            draw_round_rect(surf, z.rect, (205, 210, 220), 26)
            inner = z.rect.inflate(-46, -46)
            pygame.draw.rect(surf, (230, 230, 230), inner, width=2, border_radius=18)
        elif z.name == "Rest":
            draw_round_rect(surf, z.rect, (225, 210, 160), 22)
            inner = z.rect.inflate(-46, -46)
            pygame.draw.rect(surf, (245, 245, 245), inner, width=2, border_radius=16)

def draw_agent(surf: pygame.Surface, agent: Agent):
    # Trail (older -> newer)
    if len(agent.trail) >= 2:
        for i in range(1, len(agent.trail)):
            a = i / len(agent.trail)
            x1, y1 = agent.trail[i - 1]
            x2, y2 = agent.trail[i]
            col = (int(140 + 80 * a), int(220 + 10 * a), int(200 + 20 * a))
            pygame.draw.line(surf, col, (x1, y1), (x2, y2), width=2)

    # Agent body
    pygame.draw.circle(surf, (180, 255, 235), (int(agent.pos.x), int(agent.pos.y)), 8)
    pygame.draw.circle(surf, (90, 200, 160), (int(agent.pos.x), int(agent.pos.y)), 8, width=2)

def draw_hud(surf: pygame.Surface, font, agent: Agent, margin: int, title: str):
    z = agent.current_zone
    commit = f"{agent.commit_zone}({agent.commit_left})" if agent.commit_zone else "-"
    lines = [
        "SPACE Play/Pause | N Step | O HUD | WASD/Arrows Move",
        f"RUNNING   Z:{z:<10}  commit:{commit:<14}  D:{agent.dwell_ticks}",
        f"E:{agent.state.energy:0.2f}  L:{agent.state.load:0.2f}  C:{agent.state.coherence:0.2f}  Q:{agent.state.curiosity:0.2f}",
        f"{title}   margin:{margin}  wander:{WANDER_STRENGTH:0.2f}  ret:{RETURN_STRENGTH:0.2f}  orbit:{ORBIT_STRENGTH:0.2f}",
    ]
    y = 14
    for s in lines:
        img = font.render(s, True, (235, 235, 235))
        surf.blit(img, (14, y))
        y += 22


# =========================================================
# Main
# =========================================================

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("ORPIN / MOS Sandbox Town v1.1.9 (Ant Commit + Telemetry)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 18)

    zones = build_zones()

    agent = Agent(
        pos=pygame.Vector2(300, 300),
        vel=pygame.Vector2(0, 0),
        target=pygame.Vector2(300, 300),
    )

    # Start with a target
    agent.target, _ = decide_target(agent, zones, SOFT_EDGE_MARGIN)

    hud_on = True
    paused = False
    step_one = False

    # Telemetry: writes to telemetry/runs/...
    telemetry = TelemetryLogger(base_dir="telemetry/runs", enabled=True)
    tick = 0
    t_sec = 0.0

    try:
        running = True
        while running:
            dt = clock.tick(FPS) / 1000.0
            t_sec += dt
            tick += 1

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        paused = not paused
                    elif event.key == pygame.K_o:
                        hud_on = not hud_on
                    elif event.key == pygame.K_n:
                        step_one = True
                    elif event.key == pygame.K_ESCAPE:
                        running = False

            # Update
            do_update = (not paused) or step_one
            if do_update:
                update_agent(agent, zones, dt, SOFT_EDGE_MARGIN)
                step_one = False

            # Render
            screen.fill((16, 16, 18))
            draw_zone_visuals(screen, zones)
            draw_agent(screen, agent)

            if hud_on:
                draw_hud(
                    screen,
                    font,
                    agent,
                    SOFT_EDGE_MARGIN,
                    "v1.1.9 Ant Commit + TELEMETRY",
                )

            pygame.display.flip()

            # Telemetry log (always logs, even if paused — useful)
            telemetry.log(tick, t_sec, agent, agent.current_zone)

    finally:
        telemetry.close()
        pygame.quit()


if __name__ == "__main__":
    main()
