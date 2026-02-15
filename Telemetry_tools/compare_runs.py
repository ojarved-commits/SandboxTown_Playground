#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd


def _norm_col(s: str) -> str:
    return str(s).strip().lower().replace(" ", "_")


def _find_agent_col(df: pd.DataFrame) -> str:
    # Prefer exact known columns
    candidates = ["agent", "agent_id", "id", "name", "profile"]
    cols_norm = {_norm_col(c): c for c in df.columns}
    for k in candidates:
        if k in cols_norm:
            return cols_norm[k]

    # Fallback: anything containing "agent"
    for c in df.columns:
        if "agent" in _norm_col(c):
            return c

    raise ValueError("Could not identify an agent column")


def _coerce_numeric_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    If the CSV is already 'one row per agent', keep it.
    Otherwise, group by agent and aggregate numeric columns.
    """
    agent_col = _find_agent_col(df)

    # If it looks like one row per agent already, keep as-is.
    if df[agent_col].nunique(dropna=False) == len(df):
        return df

    # Raw log aggregation (if ever used):
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    grp = df.groupby(agent_col, dropna=False)

    agg = {}
    for c in numeric_cols:
        cl = _norm_col(c)
        if "work_units" in cl:
            agg[c] = "sum"
        elif "total_time" in cl or "rows" in cl:
            agg[c] = "max"
        else:
            agg[c] = "mean"

    out = grp.agg(agg).reset_index()
    return out


def _percent_delta(a: pd.Series, b: pd.Series) -> pd.Series:
    """
    Percent change relative to A: (B-A)/abs(A)*100
    Avoid divide-by-zero → NaN when A==0.
    """
    a_num = pd.to_numeric(a, errors="coerce")
    b_num = pd.to_numeric(b, errors="coerce")
    denom = a_num.abs()
    pct = (b_num - a_num) / denom * 100.0
    pct[denom == 0] = float("nan")
    return pct


def _build_delta_table(a: pd.DataFrame, b: pd.DataFrame, label_a: str, label_b: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      delta_df: per-agent deltas (B - A) + pct deltas
      merged_df: aligned A, B, delta side-by-side (optional export)
    """
    a = _coerce_numeric_summary_table(a).copy()
    b = _coerce_numeric_summary_table(b).copy()

    agent_a = _find_agent_col(a)
    agent_b = _find_agent_col(b)

    # Align agent column name
    if agent_a != agent_b:
        b = b.rename(columns={agent_b: agent_a})
    agent_col = agent_a

    # Set index for clean alignment
    a_idx = a.set_index(agent_col, drop=False)
    b_idx = b.set_index(agent_col, drop=False)

    # Union of agents (handles missing agents gracefully)
    all_agents = sorted(set(a_idx.index.tolist()) | set(b_idx.index.tolist()))
    a_idx = a_idx.reindex(all_agents)
    b_idx = b_idx.reindex(all_agents)

    # Separate numeric vs non-numeric
    numeric_cols = sorted(set(
        [c for c in a_idx.columns if pd.api.types.is_numeric_dtype(a_idx[c])] +
        [c for c in b_idx.columns if pd.api.types.is_numeric_dtype(b_idx[c])]
    ))
    non_numeric_cols = sorted(set(a_idx.columns.tolist()) | set(b_idx.columns.tolist()) - set(numeric_cols))

    # Build delta (B-A) for numeric cols
    delta = pd.DataFrame(index=all_agents)
    for c in numeric_cols:
        a_c = pd.to_numeric(a_idx[c], errors="coerce")
        b_c = pd.to_numeric(b_idx[c], errors="coerce")
        delta[f"{c}_delta"] = b_c - a_c
        delta[f"{c}_pct_delta"] = _percent_delta(a_idx[c], b_idx[c])

    # Add agent id column (clean)
    delta.insert(0, agent_col, all_agents)

    # Helpful: preserve key identity columns from either side
    # (profile/model/etc) by taking A then filling missing with B.
    id_cols = []
    for c in non_numeric_cols:
        if c == agent_col:
            continue
        # Keep only "small" identity fields; skip huge text blobs if any
        id_cols.append(c)

    merged_identity = pd.DataFrame(index=all_agents)
    for c in id_cols:
        merged_identity[c] = a_idx[c]
        merged_identity[c] = merged_identity[c].where(merged_identity[c].notna(), b_idx[c])

    # Final delta table: agent + identity + numeric deltas
    delta_df = pd.concat([delta.set_index(agent_col, drop=False), merged_identity], axis=1).reset_index(drop=True)

    # Build merged table (optional export)
    a_pref = a_idx.add_prefix(f"{label_a}__")
    b_pref = b_idx.add_prefix(f"{label_b}__")
    merged_df = pd.concat([a_pref, b_pref, delta.set_index(agent_col, drop=False)], axis=1).reset_index(drop=True)

    return delta_df, merged_df


def _default_out_name(label_a: str, label_b: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_a = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label_a)
    safe_b = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label_b)
    return f"diff_{safe_b}_minus_{safe_a}_{ts}.csv"


def _resolve_out_path(out: Optional[str], out_dir: Optional[str], label_a: str, label_b: str) -> str:
    if out:
        return out
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, _default_out_name(label_a, label_b))
    # Default folder if nothing specified
    default_dir = os.path.join("telemetry", "diffs")
    os.makedirs(default_dir, exist_ok=True)
    return os.path.join(default_dir, _default_out_name(label_a, label_b))


def main():
    ap = argparse.ArgumentParser(description="Compare two telemetry summary CSVs (per-agent) and export delta table.")
    ap.add_argument("csv_a", help="Path to summary CSV A (baseline).")
    ap.add_argument("csv_b", help="Path to summary CSV B (variant).")
    ap.add_argument("--label-a", default="A", help="Label for A (used in merged export).")
    ap.add_argument("--label-b", default="B", help="Label for B (used in merged export).")

    # NEW: export controls
    ap.add_argument("--out", default=None, help="Output CSV path for delta table.")
    ap.add_argument("--out-dir", default=None, help="Directory to write output CSV (auto filename).")
    ap.add_argument("--save-merged", action="store_true", help="Also export merged A/B/delta table.")
    ap.add_argument("--merged-out", default=None, help="Explicit output path for merged table CSV.")

    args = ap.parse_args()

    try:
        a = pd.read_csv(args.csv_a)
        b = pd.read_csv(args.csv_b)

        delta_df, merged_df = _build_delta_table(a, b, args.label_a, args.label_b)

        # Print
        print(f"\n=== PER-AGENT DELTAS ({args.label_b} - {args.label_a}) ===\n")
        # Print wide but readable
        with pd.option_context("display.max_columns", 200, "display.width", 200):
            print(delta_df)

        # Export delta CSV
        out_path = _resolve_out_path(args.out, args.out_dir, args.label_a, args.label_b)
        delta_df.to_csv(out_path, index=False)
        print(f"\n[compare_runs] Saved delta CSV -> {out_path}")

        # Optional merged export
        if args.save_merged:
            merged_path = args.merged_out
            if not merged_path:
                base, ext = os.path.splitext(out_path)
                merged_path = f"{base}__merged{ext}"
            merged_df.to_csv(merged_path, index=False)
            print(f"[compare_runs] Saved merged CSV -> {merged_path}")

    except Exception as e:
        print(f"[compare_runs] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
