# telemetry_tools/summarize_run.py
# Summarize latest telemetry run (or a provided CSV path)
# Outputs:
#  - prints per-agent summary
#  - writes *_summary.csv alongside the run file

import csv
import glob
import os
import sys
from collections import defaultdict, Counter
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Dict, List, Tuple

PAUSE_SPEED_THRESHOLD = 2.0  # px/sec: treat speeds below this as "paused/near-still"


@dataclass
class AgentSummary:
    agent_id: str
    profile: str
    model: str
    rows: int
    total_time_s: float
    avg_dt: float
    avg_speed: float
    std_speed: float
    pause_ratio: float
    transitions: int
    zone_counts: Dict[str, int]
    zone_time_ratio: Dict[str, float]
    # A1/A2
    work_units: int = 0
    work_efficiency: float = 0.0  # work_units per second


def find_latest_run_csv() -> str:
    # assumes repo layout:
    # telemetry_tools/summarize_run.py
    # ../telemetry/runs/*.csv
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    runs_dir = os.path.join(base_dir, "telemetry", "runs")
    pattern = os.path.join(runs_dir, "*.csv")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No CSV runs found in: {runs_dir}")

    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def safe_float(x: str, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def safe_int(x: str, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def load_rows(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = [row for row in reader]
    return header, rows


def summarize(path: str) -> List[AgentSummary]:
    header, rows = load_rows(path)

    by_agent: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        aid = r.get("agent_id", "UNKNOWN")
        by_agent[aid].append(r)

    summaries: List[AgentSummary] = []

    for aid, rlist in by_agent.items():
        # sort by t_sec if present to make transitions consistent
        if "t_sec" in header:
            rlist.sort(key=lambda rr: safe_float(rr.get("t_sec", "0")))

        dts = [safe_float(rr.get("dt", "0")) for rr in rlist]
        speeds = [safe_float(rr.get("speed", "0")) for rr in rlist]
        zones = [rr.get("zone", "None") or "None" for rr in rlist]

        profile = rlist[-1].get("profile", "") if rlist else ""
        model = rlist[-1].get("model", "") if rlist else ""

        total_time = sum(dts)
        avg_dt = mean(dts) if dts else 0.0
        avg_speed = mean(speeds) if speeds else 0.0
        std_speed = pstdev(speeds) if len(speeds) > 1 else 0.0

        # pause ratio: proportion of samples below threshold
        pauses = sum(1 for s in speeds if s < PAUSE_SPEED_THRESHOLD)
        pause_ratio = (pauses / len(speeds)) if speeds else 0.0

        # transitions: count zone changes (A->B->C)
        transitions = 0
        for i in range(1, len(zones)):
            if zones[i] != zones[i - 1]:
                transitions += 1

        zone_counts = Counter(zones)
        total_counts = sum(zone_counts.values()) if zone_counts else 0
        zone_time_ratio: Dict[str, float] = {}
        for zname, cnt in zone_counts.items():
            zone_time_ratio[zname] = (cnt / total_counts) if total_counts else 0.0

        # A1/A2: work units + normalized efficiency
        work_units = sum(safe_int(rr.get("work_units", "0")) for rr in rlist)
        work_efficiency = (work_units / total_time) if total_time > 0 else 0.0

        summaries.append(
            AgentSummary(
                agent_id=aid,
                profile=profile,
                model=model,
                rows=len(rlist),
                total_time_s=total_time,
                avg_dt=avg_dt,
                avg_speed=avg_speed,
                std_speed=std_speed,
                pause_ratio=pause_ratio,
                transitions=transitions,
                zone_counts=dict(zone_counts),
                zone_time_ratio=zone_time_ratio,
                work_units=work_units,
                work_efficiency=work_efficiency,
            )
        )

    # stable ordering: A, B, C... then others
    summaries.sort(key=lambda s: s.agent_id)
    return summaries


def write_summary_csv(run_csv_path: str, summaries: List[AgentSummary]) -> str:
    base, ext = os.path.splitext(run_csv_path)
    out_path = base + "_summary.csv"

    # collect all zones seen across agents to make consistent columns
    all_zones = set()
    for s in summaries:
        all_zones.update(s.zone_time_ratio.keys())
    zone_cols = sorted(all_zones)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "agent_id",
            "profile",
            "model",
            "rows",
            "total_time_s",
            "avg_dt",
            "avg_speed",
            "std_speed",
            "pause_ratio",
            "transitions",
            # A1/A2
            "work_units",
            "work_efficiency",
            *[f"zone_pct_{z}" for z in zone_cols],
        ])

        for s in summaries:
            w.writerow([
                s.agent_id,
                s.profile,
                s.model,
                s.rows,
                f"{s.total_time_s:.4f}",
                f"{s.avg_dt:.6f}",
                f"{s.avg_speed:.3f}",
                f"{s.std_speed:.3f}",
                f"{s.pause_ratio:.3f}",
                s.transitions,
                # A1/A2
                s.work_units,
                f"{s.work_efficiency:.4f}",
                *[f"{(s.zone_time_ratio.get(z, 0.0) * 100.0):.2f}" for z in zone_cols],
            ])

    return out_path


def print_summary(run_csv_path: str, summaries: List[AgentSummary]) -> None:
    print("\n=== ORPIN / MOS Telemetry Summary ===")
    print(f"Run: {run_csv_path}")
    print(f"Pause threshold: speed < {PAUSE_SPEED_THRESHOLD} px/s\n")

    for s in summaries:
        print(f"- Agent {s.agent_id} | {s.profile} | model={s.model}")
        print(f"  rows={s.rows}  total_time={s.total_time_s:.2f}s  avg_dt={s.avg_dt:.4f}")
        print(f"  avg_speed={s.avg_speed:.2f}  std_speed={s.std_speed:.2f}  pause_ratio={s.pause_ratio:.2f}")
        print(f"  transitions={s.transitions}")
        print(f"  work_units={s.work_units}  work_efficiency={s.work_efficiency:.3f}/s")

        # show top zones by %
        z_sorted = sorted(s.zone_time_ratio.items(), key=lambda kv: kv[1], reverse=True)
        z_line = "  zones: " + ", ".join([f"{z} {pct*100:.1f}%" for z, pct in z_sorted])
        print(z_line)
        print("")


def main():
    # Usage:
    #   python telemetry_tools/summarize_run.py
    #   python telemetry_tools/summarize_run.py telemetry/runs/run_*.csv
    if len(sys.argv) > 1:
        run_csv = sys.argv[1]
        if not os.path.isfile(run_csv):
            # allow relative paths from repo root
            alt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", run_csv))
            if os.path.isfile(alt):
                run_csv = alt
            else:
                raise FileNotFoundError(f"Could not find CSV: {sys.argv[1]}")
    else:
        run_csv = find_latest_run_csv()

    summaries = summarize(run_csv)
    print_summary(run_csv, summaries)

    out_path = write_summary_csv(run_csv, summaries)
    print(f"Saved summary CSV -> {out_path}\n")


if __name__ == "__main__":
    main()
