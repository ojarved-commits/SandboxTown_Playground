# Telemetry_tools/speed_histogram.py
import csv, sys, os, math
from collections import defaultdict

def is_csv(p): return p.lower().endswith(".csv") and os.path.exists(p)

def main():
    if len(sys.argv) < 2:
        print("Usage: python Telemetry_tools/speed_histogram.py telemetry\\runs\\run_*.csv")
        sys.exit(1)

    path = sys.argv[1]
    if not is_csv(path):
        raise FileNotFoundError(f"Could not find CSV: {path}")

    speeds = defaultdict(list)

    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            aid = row.get("agent_id", "?")
            try:
                sp = float(row.get("speed", "0"))
            except ValueError:
                sp = 0.0
            speeds[aid].append(max(0.0, sp))

    # histogram settings
    BIN = 10.0   # px/s
    MAXB = 200.0 # cap for display
    WIDTH = 40

    print("\nSpeed Histogram (ASCII)\n")
    for aid, arr in speeds.items():
        if not arr:
            continue
        arr2 = [min(a, MAXB) for a in arr]
        bins = int(MAXB // BIN)
        counts = [0] * (bins + 1)

        for a in arr2:
            i = int(a // BIN)
            counts[i] += 1

        peak = max(counts) if counts else 1
        avg = sum(arr) / len(arr)
        print(f"- Agent {aid} | samples={len(arr)} | avg_speed={avg:.2f}px/s")

        for i, c in enumerate(counts):
            lo = i * BIN
            hi = lo + BIN
            bar = "#" * int((c / peak) * WIDTH)
            print(f"  {lo:>4.0f}-{hi:>4.0f}: {bar} {c}")
        print()

if __name__ == "__main__":
    main()
