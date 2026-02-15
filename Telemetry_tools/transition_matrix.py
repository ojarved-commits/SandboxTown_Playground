# Telemetry_tools/transition_matrix.py
import csv, sys, os
from collections import defaultdict, Counter

def is_csv(p): return p.lower().endswith(".csv") and os.path.exists(p)

def main():
    if len(sys.argv) < 2:
        print("Usage: python Telemetry_tools/transition_matrix.py telemetry\\runs\\run_*.csv")
        sys.exit(1)

    path = sys.argv[1]
    if not is_csv(path):
        raise FileNotFoundError(f"Could not find CSV: {path}")

    prev_zone = {}
    trans = defaultdict(Counter)   # (agent_id) -> Counter("A->B")
    trans_counts = defaultdict(int)

    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            aid = row.get("agent_id", "?")
            z = row.get("zone", "None")
            if aid in prev_zone:
                pz = prev_zone[aid]
                if pz != z:
                    key = f"{pz}->{z}"
                    trans[aid][key] += 1
                    trans_counts[aid] += 1
            prev_zone[aid] = z

    print("\nTransition Matrix (zone changes only)\n")
    for aid, c in trans.items():
        total = trans_counts[aid]
        print(f"- Agent {aid} | transitions={total}")
        for k, v in c.most_common():
            pct = (v / total * 100.0) if total else 0.0
            print(f"  {k:<20} {v:>6}  ({pct:>5.1f}%)")
        print()

if __name__ == "__main__":
    main()
