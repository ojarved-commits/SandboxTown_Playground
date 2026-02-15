# src/run_batch.py
# Headless batch runner for ORPIN/MOS SandboxTown
# - No window rendering
# - Runs same engine code from src/main.py
# - Writes telemetry into telemetry/runs/
# - Optionally runs summarize_run.py after each run

import os
import sys
import csv
import random
import argparse
import subprocess
from datetime import datetime

# --- make sure we can import src/main.py as a module ---
HERE = os.path.dirname(os.path.abspath(__file__))          # .../src
REPO = os.path.abspath(os.path.join(HERE, ".."))           # repo root
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import main as sim  # <-- imports your existing src/main.py (safe because main() is guarded)


def ensure_runs_dir() -> str:
    out_dir = os.path.join(REPO, "telemetry", "runs")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def make_run_path(variant: str, seed: int) -> str:
    out_dir = ensure_runs_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(out_dir, f"run_{ts}_{variant.lower()}_seed{seed}.csv")


def build_agents(zmap):
    """
    Mirrors src/main.py agent spawning (same profiles, same starting zones).
    """
    fantail = sim.get_profile("fish")
    kiwi_fast = sim.get_profile("ant_fast")
    kiwi_slow = sim.get_profile("ant_slow")
    sparrow = sim.get_profile("bird")  # whatever model bird is set to in profiles.py

    any_center = list(zmap.values())[0].center()
    lib_center = zmap.get("Library", None).center() if "Library" in zmap else any_center
    park_center = zmap.get("Park", None).center() if "Park" in zmap else any_center
    trans_center = zmap.get("Transition", None).center() if "Transition" in zmap else any_center

    A = sim.Agent("A", fantail, sim.v2(250, 310), sim.v2(0, 0), lib_center)
    B = sim.Agent("B", kiwi_fast, sim.v2(720, 310), sim.v2(0, 0), park_center)
    C = sim.Agent("C", kiwi_slow, sim.v2(700, 360), sim.v2(0, 0), park_center)
    D = sim.Agent("D", sparrow, sim.v2(500, 240), sim.v2(0, 0), park_center)

    # Optional: keep your Sparrow “seed” exactly like your visual file did
    # (comment out if you don’t want it in batch)
    D.state.energy = 0.55
    D.state.load = 0.65
    D.state.coherence = 0.55
    D.state.curiosity = 0.75

    agents = [A, B, C, D]

    # init commits/trails for ANT agents only (same as visual main)
    for ag in agents:
        if ag.profile.model == "ant":
            start_zone = zmap.get("Library", list(zmap.values())[0])
            ag.commit_zone = start_zone
            ag.commit_ticks = random.randint(ag.profile.commit_min, ag.profile.commit_max)
            ag.last_choice = ag.commit_zone.name
            ag.target = sim.pick_point_in_zone(ag.commit_zone, pad=55)
            ag.trail = [ag.pos.copy()]

    return agents


def run_one(variant: str, seconds: float, seed: int, fps: int, summarize: bool) -> str:
    random.seed(seed)

    # Use the same VARIANT switch your main.py uses
    sim.VARIANT = variant

    zones = sim.build_zones()
    zmap = {z.name: z for z in zones}
    agents = build_agents(zmap)

    # Fixed timestep headless loop (stable + reproducible)
    dt = 1.0 / float(fps)
    # Respect dt clamps (match visual behavior)
    dt = min(dt, min(a.profile.dt_clamp for a in agents))

    steps = int(seconds / dt)

    run_csv_path = make_run_path(variant, seed)

    with open(run_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "t_sec","dt","agent_id",
            "x","y","vx","vy","speed",
            "zone","commit_zone","commit_left","dwell_ticks","work_units","output_score",
            "energy","load","coherence","curiosity",
            "profile","model"
        ])

        t_sec = 0.0
        for _ in range(steps):
            t_sec += dt
            for ag in agents:
                before = ag.pos.copy()

                if ag.profile.model == "fish":
                    sim.update_agent_fish(ag, zones, dt)
                else:
                    sim.update_agent_ant(ag, zones, dt)
                    # trails not needed for headless, but harmless if you want parity
                    if (ag.pos - before).length() >= ag.profile.trail_move_eps:
                        ag.trail.append(ag.pos.copy())

                s = ag.state
                speed = ag.vel.length()

                if ag.profile.model == "fish":
                    commit_zone = ag.fish_commit_zone if getattr(ag, "fish_commit_zone", None) else "-"
                    commit_left = getattr(ag, "fish_commit_ticks_left", 0)
                else:
                    commit_zone = ag.commit_zone.name if ag.commit_zone else "-"
                    commit_left = ag.commit_ticks

                w.writerow([
                    round(t_sec, 4), round(dt, 4), ag.agent_id,
                    round(ag.pos.x, 2), round(ag.pos.y, 2),
                    round(ag.vel.x, 2), round(ag.vel.y, 2),
                    round(speed, 2),
                    ag.current_zone, commit_zone, commit_left, ag.dwell_ticks,
                    getattr(ag, "work_units", 0),
                    round(getattr(ag, "output_score", 0.0), 4),
                    round(s.energy, 4), round(s.load, 4), round(s.coherence, 4), round(s.curiosity, 4),
                    ag.profile.name, ag.profile.model
                ])

    # Optional: auto-run summary tool after each batch run
    if summarize:
        tool = os.path.join(REPO, "telemetry_tools", "summarize_run.py")
        if os.path.isfile(tool):
            subprocess.run([sys.executable, tool, run_csv_path], cwd=REPO)
        else:
            print(f"[warn] summarize_run.py not found at: {tool}")

    return run_csv_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="BASE", help="e.g. BASE, B1_NO_TRANSITION, P1_REST_SCARCITY")
    ap.add_argument("--seconds", type=float, default=180.0, help="run length in seconds")
    ap.add_argument("--runs", type=int, default=1, help="number of runs")
    ap.add_argument("--seed", type=int, default=123, help="base seed (seed+i per run)")
    ap.add_argument("--fps", type=int, default=60, help="fixed timestep fps")
    ap.add_argument("--summarize", action="store_true", help="auto-run telemetry_tools/summarize_run.py")
    args = ap.parse_args()

    for i in range(args.runs):
        run_seed = args.seed + i
        out = run_one(args.variant, args.seconds, run_seed, args.fps, args.summarize)
        print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
