# Behavior note: organic, fish-like motion; loops emerge; energy changes compound with dwell time.


import math
import random
from dataclasses import dataclass, field
import pygame


# ============================================================
# ORPIN / MOS Sandbox Town v1.1.7  (Soft Edges + dt + hysteresis SAFE
#                                 + commit + edge-pause + REST zone)
# ============================================================

W, H = 900, 520
FPS = 60

# --- Soft-edge settings ---
SOFT_EDGE_MARGIN = 35           # "edge" thickness inside each zone where behavior can shift
EDGE_PAUSE_MIN = 0.06           # seconds
EDGE_PAUSE_MAX = 0.22           # seconds

# --- Commit behavior ---
COMMIT_MIN = 40                 # ticks
COMMIT_MAX = 90                 # ticks
COMMIT_COOLDOWN_MIN = 25        # ticks before we can re-commit
COMMIT_COOLDOWN_MAX = 60

# --- Hysteresis safe ---
MIN_DWELL_TICKS = 18            # minimum dwell before reconsidering leaving zone
EXIT_HYSTERESIS_TICKS = 14      # once we "decide to leave", hold that decision briefly

# --- Movement ---
BASE_SPEED = 160.0              # pixels/sec
TURN_RATE = 10.0                # smoothing


def clamp(x, a, b):
    return max(a, min(b, x))


def lerp(a, b, t):
    return a + (b - a) * t


def vec_lerp(v1: pygame.Vector2, v2: pygame.Vector2, t: float) -> pygame.Vector2:
    return pygame.Vector2(lerp(v1.x, v2.x, t), lerp(v1.y, v2.y, t))


@dataclass
class Zone:
    name: str
    rect: pygame.Rect
    effects: dict  # per second deltas: energy/load/coherence/curiosity
    pause_bias: float = 1.0
    commit_bias: float = 1.0

    def contains(self, p: pygame.Vector2) -> bool:
        return self.rect.collidepoint(p.x, p.y)

    def inner_rect(self, margin: int) -> pygame.Rect:
        return self.rect.inflate(-2 * margin, -2 * margin)

    def near_edge(self, p: pygame.Vector2, margin: int) -> bool:
        """True when inside zone but near its boundary (within margin)."""
        if not self.contains(p):
            return False
        inner = self.inner_rect(margin)
        return not inner.collidepoint(p.x, p.y)

    def center(self) -> pygame.Vector2:
        return pygame.Vector2(self.rect.centerx, self.rect.centery)


@dataclass
class AgentState:
    energy: float = 0.70
    load: float = 0.20
    coherence: float = 0.60
    curiosity: float = 0.70


@dataclass
class Agent:
    pos: pygame.Vector2
    vel: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0, 0))
    target: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0, 0))
    state: AgentState = field(default_factory=AgentState)

    current_zone: str = "None"
    dwell_ticks: int = 0

    # pause mechanics (seconds)
    paused: bool = False
    pause_hold_s: float = 0.0
    pause_cooldown_s: float = 0.0

    # leaving hysteresis
    leaving_lock_ticks: int = 0

    # commit mechanics
    commit_zone: str | None = None
    commit_ticks_left: int = 0
    commit_cooldown_ticks: int = 0

    # one-time "edge pause" latch so it doesn't spam each frame
    edge_pause_latch: bool = False


def build_zones():
    # Left: Library (blue), Right: Park (green), Middle: Transition (grey)
    library = Zone(
        "Library",
        pygame.Rect(90, 170, 280, 220),
        {"energy": -0.030, "load": +0.020, "coherence": +0.015, "curiosity": +0.020},
        pause_bias=1.15,
        commit_bias=1.25,
    )

    park = Zone(
        "Park",
        pygame.Rect(530, 170, 280, 220),
        {"energy": +0.050, "load": -0.020, "coherence": +0.012, "curiosity": -0.005},
        pause_bias=1.05,
        commit_bias=1.05,
    )

    transition = Zone(
        "Transition",
        pygame.Rect(390, 250, 120, 60),
        {"energy": -0.010, "load": -0.010, "coherence": +0.006, "curiosity": +0.002},
        pause_bias=1.30,
        commit_bias=0.60,
    )

    # ✅ NEW ZONE: Rest (small, below Transition)
    rest = Zone(
        "Rest",
        pygame.Rect(390, 330, 120, 50),
        {"energy": +0.012, "load": -0.018, "coherence": +0.020, "curiosity": -0.004},
        pause_bias=1.55,     # more likely to pause
        commit_bias=0.55     # easy to leave (won't trap)
    )

    return [library, park, transition, rest]


ZONE_COLORS = {
    "Library": (60, 140, 210),
    "Park": (130, 210, 130),
    "Transition": (210, 210, 210),
    "Rest": (185, 180, 160),
}


def zone_at(zones: list[Zone], pos: pygame.Vector2) -> Zone | None:
    for z in zones:
        if z.contains(pos):
            return z
    return None


def apply_zone_effects(agent: Agent, z: Zone | None, dt: float):
    if z is None:
        # outside zones: mild drift toward neutral
        s = agent.state
        s.energy = clamp(s.energy + (-0.006) * dt, 0.0, 1.0)
        s.load = clamp(s.load + (-0.004) * dt, 0.0, 1.0)
        s.coherence = clamp(s.coherence + (+0.002) * dt, 0.0, 1.0)
        s.curiosity = clamp(s.curiosity + (+0.001) * dt, 0.0, 1.0)
        return

    s = agent.state
    s.energy = clamp(s.energy + z.effects.get("energy", 0.0) * dt, 0.0, 1.0)
    s.load = clamp(s.load + z.effects.get("load", 0.0) * dt, 0.0, 1.0)
    s.coherence = clamp(s.coherence + z.effects.get("coherence", 0.0) * dt, 0.0, 1.0)
    s.curiosity = clamp(s.curiosity + z.effects.get("curiosity", 0.0) * dt, 0.0, 1.0)


def maybe_edge_pause(agent: Agent, z: Zone | None, margin: int):
    """Edge-pause: when near the boundary of a zone, pause once, then latch until we move away."""
    if z is None:
        agent.edge_pause_latch = False
        return

    near = z.near_edge(agent.pos, margin)
    if near and not agent.edge_pause_latch and agent.pause_cooldown_s <= 0:
        # pause a little like "checking traffic"
        hold = random.uniform(EDGE_PAUSE_MIN, EDGE_PAUSE_MAX) * z.pause_bias
        agent.pause_hold_s = max(agent.pause_hold_s, hold)
        agent.edge_pause_latch = True
    elif not near:
        agent.edge_pause_latch = False


def pick_commit_zone(agent: Agent, zones: list[Zone]) -> str | None:
    """Occasionally commit to a zone for longer, biased by current state."""
    if agent.commit_cooldown_ticks > 0:
        return None

    s = agent.state

    # Regulation priorities:
    # - High load / low energy -> Park or Rest
    # - High curiosity + stable -> Library
    # - Low coherence -> Rest or Transition
    weights = {}
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

    # Small chance per tick
    if random.random() < 0.012:
        total = sum(weights.values())
        r = random.random() * total
        acc = 0.0
        for name, w in weights.items():
            acc += w
            if r <= acc:
                return name
    return None


def decide_target(agent: Agent, zones: list[Zone], margin: int) -> pygame.Vector2:
    """SAFE hysteresis decision: don't flip-flop, honor minimum dwell, and respect commits."""
    s = agent.state

    # If we're currently committed, just aim for that zone's center
    if agent.commit_ticks_left > 0 and agent.commit_zone is not None:
        for z in zones:
            if z.name == agent.commit_zone:
                return z.center()

    # If we recently "locked leaving", keep moving toward current target briefly
    if agent.leaving_lock_ticks > 0:
        return agent.target

    # Identify current zone by position (truth)
    current = zone_at(zones, agent.pos)
    current_name = current.name if current else "None"

    # Minimum dwell: don't reconsider instantly
    if agent.dwell_ticks < MIN_DWELL_TICKS and current is not None:
        return current.center()

    # Regulation-first attraction scores
    # Higher score = more attractive
    scores = {}
    for z in zones:
        score = 0.0

        # Park: replenish energy / reduce load
        if z.name == "Park":
            score += 2.0 * (1.0 - s.energy)
            score += 1.5 * s.load
            score += 0.3 * (1.0 - s.coherence)

        # Library: curiosity + coherence
        if z.name == "Library":
            score += 2.0 * s.curiosity
            score += 1.2 * s.coherence
            score -= 1.2 * s.load  # if load high, less attractive

        # Rest: coherence repair / load shed
        if z.name == "Rest":
            score += 1.6 * (1.0 - s.coherence)
            score += 1.0 * s.load
            score += 0.6 * (1.0 - s.energy)

        # Transition: neutral buffer, mild preference when leaving edges
        if z.name == "Transition":
            score += 0.25
            score += 0.6 * (1.0 - s.coherence)

        # Soft edge influence: if you're near edge, slightly increase desire to go somewhere else
        if current is not None and current.name == z.name and current.near_edge(agent.pos, margin):
            score -= 0.35

        # Mild randomness so it's not robotic
        score += random.uniform(-0.08, 0.08)

        scores[z.name] = score

    # Choose best
    best_name = max(scores, key=scores.get)

    # SAFE hysteresis: if best is different, don't change unless you're truly leaving current zone
    if current is not None and best_name != current_name:
        # only allow switching if agent is close to the edge (natural exit condition)
        if not current.near_edge(agent.pos, margin):
            # stay in current zone center
            return current.center()
        else:
            # lock leaving for a short burst to avoid flip-flop
            agent.leaving_lock_ticks = EXIT_HYSTERESIS_TICKS

    # Return chosen zone center
    for z in zones:
        if z.name == best_name:
            return z.center()

    # Fallback
    return pygame.Vector2(W / 2, H / 2)


def update_agent(agent: Agent, zones: list[Zone], dt: float, tick_running: bool, margin: int):
    # Cooldowns
    agent.pause_cooldown_s = max(0.0, agent.pause_cooldown_s - dt)
    agent.pause_hold_s = max(0.0, agent.pause_hold_s - dt)

    if agent.leaving_lock_ticks > 0:
        agent.leaving_lock_ticks -= 1

    if agent.commit_cooldown_ticks > 0:
        agent.commit_cooldown_ticks -= 1
    if agent.commit_ticks_left > 0:
        agent.commit_ticks_left -= 1
        if agent.commit_ticks_left <= 0:
            agent.commit_zone = None
            agent.commit_cooldown_ticks = random.randint(COMMIT_COOLDOWN_MIN, COMMIT_COOLDOWN_MAX)

    # Determine zone and dwell
    z = zone_at(zones, agent.pos)
    zname = z.name if z else "None"
    if zname == agent.current_zone:
        agent.dwell_ticks += 1
    else:
        agent.current_zone = zname
        agent.dwell_ticks = 0

    # Apply zone effects only when running
    if tick_running:
        apply_zone_effects(agent, z, dt)

    # Edge pause behavior
    maybe_edge_pause(agent, z, margin)

    # Possibly start a commit (only when running)
    if tick_running and agent.commit_zone is None and agent.commit_ticks_left <= 0:
        cz = pick_commit_zone(agent, zones)
        if cz is not None:
            agent.commit_zone = cz
            agent.commit_ticks_left = random.randint(COMMIT_MIN, COMMIT_MAX)

    # Decide a target occasionally
    if tick_running and (agent.dwell_ticks % 8 == 0 or agent.target.length_squared() == 0):
        agent.target = decide_target(agent, zones, margin)

    # Pausing: if we have a hold, stop moving
    if agent.pause_hold_s > 0.0:
        agent.paused = True
    else:
        agent.paused = False
        agent.pause_cooldown_s = max(agent.pause_cooldown_s, 0.10)  # prevents spam pauses

    # Movement (dt scaled)
    if tick_running and not agent.paused:
        to = (agent.target - agent.pos)
        dist = to.length()
        if dist > 1.0:
            desired = to.normalize() * BASE_SPEED
            # Smooth turn
            agent.vel = vec_lerp(agent.vel, desired, clamp(dt * TURN_RATE, 0.0, 1.0))
            agent.pos += agent.vel * dt
        else:
            agent.vel *= 0.85
    else:
        agent.vel *= 0.85


def draw_world(screen: pygame.Surface, zones: list[Zone], agent: Agent, show_hud: bool, margin: int):
    screen.fill((20, 20, 24))

    # Draw zones
    for z in zones:
        color = ZONE_COLORS.get(z.name, (200, 200, 200))
        pygame.draw.rect(screen, color, z.rect, border_radius=22)

        # Draw inner rect (soft-edge guide) lightly
        inner = z.inner_rect(margin)
        pygame.draw.rect(screen, (255, 255, 255), inner, width=1, border_radius=18)

    # Agent trail (subtle)
    # (Keeping minimal: just one streak based on velocity)
    streak_len = 22
    if agent.vel.length() > 0.5:
        dirv = agent.vel.normalize()
    else:
        dirv = pygame.Vector2(1, 0)
    start = agent.pos - dirv * streak_len
    end = agent.pos
    pygame.draw.line(screen, (120, 255, 210), start, end, width=3)

    # Agent dot
    pygame.draw.circle(screen, (160, 255, 220), (int(agent.pos.x), int(agent.pos.y)), 8)

    if show_hud:
        font = pygame.font.SysFont("consolas", 18)
        font2 = pygame.font.SysFont("consolas", 16)

        s = agent.state
        zone_label = agent.current_zone

        # Clean, fixed HUD lines (prevents "glitchy" overlay impressions)
        line1 = "SPACE Play/Pause | N Step | O HUD | WASD/Arrows Move"
        line2 = f"RUNNING  Z:{zone_label:<10}  P:{'1' if agent.paused else '0'}  D:{agent.dwell_ticks:>3}"
        line3 = f"E:{s.energy:0.2f}  L:{s.load:0.2f}  C:{s.coherence:0.2f}  Q:{s.curiosity:0.2f}"
        commit_text = agent.commit_zone if agent.commit_zone else "-"
        line4 = f"v1.1.7 Soft Edges + dt + hysteresis SAFE + commit + edge-pause + REST   commit:{commit_text}({agent.commit_ticks_left})  margin:{margin}"

        y = 10
        for ln in (line1, line2, line3, line4):
            surf = font.render(ln, True, (230, 230, 230))
            screen.blit(surf, (14, y))
            y += 22

        goal = "Goal: calm oscillation + natural pauses + smooth shifts (no reward/pressure)."
        screen.blit(font2.render(goal, True, (210, 210, 210)), (14, y + 4))


def handle_observer_move(keys, dz: pygame.Vector2):
    speed = 260.0
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        dz.x -= speed
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        dz.x += speed
    if keys[pygame.K_UP] or keys[pygame.K_w]:
        dz.y -= speed
    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        dz.y += speed


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("ORPIN / MOS Sandbox Town v1.1.7 (Rest zone)")
    clock = pygame.time.Clock()

    zones = build_zones()

    # Start inside Library-ish
    agent = Agent(pos=pygame.Vector2(230, 280))
    agent.target = pygame.Vector2(230, 280)

    running = True
    tick_running = True
    show_hud = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        dt = clamp(dt, 0.0, 0.05)  # SAFE dt clamp

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    tick_running = not tick_running
                elif event.key == pygame.K_o:
                    show_hud = not show_hud
                elif event.key == pygame.K_n:
                    # single-step: run one tick of logic even if paused
                    update_agent(agent, zones, dt, True, SOFT_EDGE_MARGIN)

        # Observer move (optional “camera” idea, currently moves agent directly)
        keys = pygame.key.get_pressed()
        dz = pygame.Vector2(0, 0)
        handle_observer_move(keys, dz)
        if dz.length_squared() > 0:
            agent.pos += dz * dt
            agent.target = agent.pos

        # Normal update
        update_agent(agent, zones, dt, tick_running, SOFT_EDGE_MARGIN)

        draw_world(screen, zones, agent, show_hud, SOFT_EDGE_MARGIN)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
