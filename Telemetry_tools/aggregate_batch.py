import argparse
import csv
import glob
import os
from collections import defaultdict
from statistics import mean

METRIC_FIELDS = [
    "rows",
    "total_time",
    "avg_dt",
    "avg_speed",
    "std_speed",
    "pause_ratio",
    "transitions",
    "work_units",
    "work_efficiency",
]

def to_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", required=True, help=r'Glob pattern, e.g. C:\SandboxTown_Data\telemetry\runs\run_300runs_*_base_summary.csv')
    ap.add_argument("--out", required=True, help=r'Output CSV path, e.g. C:\SandboxTown_Data\telemetry\runs\BATCH_300runs_summary.csv')
    args = ap.parse_args()

    files = sorted(glob.glob(args.pattern))
    if not files:
        raise FileNotFoundError(f"No files matched pattern: {args.pattern}")

    # agent_name -> metric -> list(values)
    acc = defaultdict(lambda: defaultdict(list))
    # agent_name -> zone_name -> list(pct)
    zone_acc = defaultdict(lambda: defaultdict(list))

    seen_any = 0

    for fp in files:
        with open(fp, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            continue

        # Each summary csv should be "per agent" (one row per agent)
        for r in rows:
            agent = (r.get("agent") or r.get("Agent") or r.get("name") or r.get("Name") or "").strip()
            if not agent:
                # fallback: try model/profile label fields
                agent = (r.get("profile") or r.get("Profile") or r.get("id") or r.get("ID") or "").strip()
            if not agent:
                continue

            for m in METRIC_FIELDS:
                if m in r:
                    v = to_float(r.get(m))
                    if v is not None:
                        acc[agent][m].append(v)

            # zones are often stored as columns like zone_Library, zone_Park etc OR as a 'zones' string.
            # Handle both:
            for k, v in r.items():
                if k.lower().startswith("zone_"):
                    pct = to_float(v)
                    if pct is not None:
                        zone_name = k[5:]  # after "zone_"
                        zone_acc[agent][zone_name].append(pct)

            zones_str = r.get("zones") or r.get("Zones")
            if zones_str:
                # parse "Library 41.1%, Park 33.2%, ..."
                parts = [p.strip() for p in zones_str.split(",")]
                for p in parts:
                    if not p:
                        continue
                    # split last token as percent
                    toks = p.replace("%", "").split()
                    if len(toks) < 2:
                        continue
                    try:
                        pct = float(toks[-1])
                        zone_name = " ".join(toks[:-1])
                        zone_acc[agent][zone_name].append(pct)
                    except Exception:
                        pass

            seen_any += 1

    if not acc:
        raise RuntimeError("No usable rows found in summary CSVs.")

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Build output rows: mean + stdev-ish not needed right now; we’ll do mean only
    agents_sorted = sorted(acc.keys())

    # union of zone names
    all_zones = set()
    for a in agents_sorted:
        all_zones |= set(zone_acc[a].keys())
    zones_sorted = sorted(all_zones)

    fieldnames = ["agent", "n_files"] + [f"mean_{m}" for m in METRIC_FIELDS] + [f"mean_zone_{z}" for z in zones_sorted]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for a in agents_sorted:
            row = {"agent": a, "n_files": len(files)}
            for m in METRIC_FIELDS:
                vals = acc[a].get(m, [])
                row[f"mean_{m}"] = mean(vals) if vals else ""
            for z in zones_sorted:
                vals = zone_acc[a].get(z, [])
                row[f"mean_zone_{z}"] = mean(vals) if vals else ""
            w.writerow(row)

    print(f"Matched {len(files)} files")
    print(f"Wrote batch summary -> {args.out}")

if __name__ == "__main__":
    main()
