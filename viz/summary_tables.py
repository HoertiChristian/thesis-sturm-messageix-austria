"""Extract presentation-ready summary tables from the solved run folders.

Mirrors ``viz/plots.R``: auto-discovers every ``results/runs/pathway-*__digi-*``
folder (no manifest) and reads each cell's ``buildings_co2.csv`` (territorial
buildings CO2, kt). Writes three tables to ``results/tables/``:

* ``buildings_co2_by_year.csv`` — long: pathway, digitalization, year, co2_kt
  (for the key milestone years).
* ``gap_to_target_2040.csv`` — per cell: 2040 CO2, gap to the REP-0995 WAM
  target of 1,300 kt (negative = below target) and % of it, plus the gap to
  the WEM existing-measures benchmark of 3,400 kt.
* ``rq2_spread.csv`` — per pathway: the 2040 spread across digitalization levels
  (max − min, absolute kt and % of the pathway mean) — the RQ2 effect size.

Usage:
    python viz/summary_tables.py [results_dir=results/runs] [out_dir=results/tables]

Imports the target loaders and id parsing from the package (the
``sys.path`` shim below makes that work without an install, as in ``run.ipynb``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from common.scenarios import parse_scenario_id
from common.validation.gap_to_target import wam_target_kt, wem_target_kt

#: Milestone years to tabulate (model grid).
MILESTONE_YEARS: tuple[int, ...] = (2025, 2030, 2035, 2040)

_PATHWAY_LABELS = {
    "reference": "Reference",
    "renewables_push": "Renewables Push",
    "bio_bridge": "Bio-Bridge",
}
_DIGI_LABELS = {
    "baseline": "Baseline",
    "stagnating": "Stagnating",
    "accelerated": "Accelerated",
}


def collect(results_dir: Path, csv_name: str = "buildings_co2.csv") -> pd.DataFrame:
    """Long frame of buildings CO2 at the milestone years across all run folders.

    ``csv_name`` selects the accounting basis: the default territorial series or
    ``buildings_co2_consumption.csv`` (r7 B4 — both bases reported everywhere).
    """
    rows: list[dict[str, object]] = []
    for sub in sorted(results_dir.iterdir()):
        if not sub.is_dir():
            continue
        ids = parse_scenario_id(sub.name)
        csv = sub / csv_name
        if ids is None or not csv.exists():
            continue
        p, d = ids
        # Matrix cells only — drop ad-hoc probes (pathway-ref_tax120) and variant
        # runs (…__shape-linear parses to an unknown digi id) so they don't
        # contaminate the tables; mirrors the plots.R filter.
        if p not in _PATHWAY_LABELS or d not in _DIGI_LABELS:
            print(f"Skipping non-matrix run folder: {sub.name}")
            continue
        df = pd.read_csv(csv)
        df = df[df["year"].isin(MILESTONE_YEARS)]
        for _, r in df.iterrows():
            rows.append({
                "pathway": _PATHWAY_LABELS.get(p, p),
                "pathway_id": p,
                "digitalization": _DIGI_LABELS.get(d, d),
                "digi_id": d,
                "year": int(r["year"]),
                "co2_kt": round(float(r["value"]), 1),
            })
    return pd.DataFrame(rows)


def main() -> None:
    results_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "results/runs")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "results/tables")
    if not results_dir.is_dir():
        raise SystemExit(
            f"No results directory {results_dir} — solve the scenarios first (run.ipynb or "
            "`sturm-messageix run`), or pass the run folder as the first argument."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    long = collect(results_dir)
    if long.empty:
        print(f"No run folders with buildings_co2.csv under {results_dir}")
        return

    long.sort_values(["pathway_id", "digi_id", "year"]).to_csv(
        out_dir / "buildings_co2_by_year.csv", index=False
    )

    y2040 = long[long["year"] == 2040].copy()
    y2040["gap_to_wam_kt"] = (y2040["co2_kt"] - wam_target_kt()).round(1)
    y2040["pct_of_wam"] = (100 * y2040["co2_kt"] / wam_target_kt()).round(1)
    y2040["gap_to_wem_kt"] = (y2040["co2_kt"] - wem_target_kt()).round(1)
    y2040[["pathway", "digitalization", "co2_kt",
           "gap_to_wam_kt", "pct_of_wam", "gap_to_wem_kt"]] \
        .sort_values(["pathway", "digitalization"]) \
        .to_csv(out_dir / "gap_to_target_2040.csv", index=False)

    spread = (
        y2040.groupby(["pathway", "pathway_id"])["co2_kt"]
        .agg(min_kt="min", max_kt="max", mean_kt="mean")
        .reset_index()
    )
    spread["spread_kt"] = (spread["max_kt"] - spread["min_kt"]).round(1)
    spread["spread_pct"] = (100 * spread["spread_kt"] / spread["mean_kt"]).round(2)
    spread[["pathway", "min_kt", "max_kt", "spread_kt", "spread_pct"]] \
        .to_csv(out_dir / "rq2_spread.csv", index=False)

    # Consumption-basis twins (r7 B4): the territorial zeros of the capped
    # pathways are an accounting boundary; the consumption basis carries the
    # non-degenerate RQ2 content there (2026-08-28 meaningfulness review §2-4).
    cons = collect(results_dir, "buildings_co2_consumption.csv")
    n_extra = 0
    if not cons.empty:
        cons.sort_values(["pathway_id", "digi_id", "year"]).to_csv(
            out_dir / "buildings_co2_by_year_consumption.csv", index=False
        )
        c2040 = cons[cons["year"] == 2040]
        cspread = (
            c2040.groupby(["pathway", "pathway_id"])["co2_kt"]
            .agg(min_kt="min", max_kt="max", mean_kt="mean")
            .reset_index()
        )
        cspread["spread_kt"] = (cspread["max_kt"] - cspread["min_kt"]).round(1)
        cspread["spread_pct"] = (100 * cspread["spread_kt"] / cspread["mean_kt"]).round(2)
        cspread[["pathway", "min_kt", "max_kt", "spread_kt", "spread_pct"]] \
            .to_csv(out_dir / "rq2_spread_consumption.csv", index=False)
        n_extra = 2

    print(f"Wrote {3 + n_extra} tables to {out_dir} from "
          f"{long['pathway_id'].nunique()} pathway(s), {len(y2040)} cells.")


if __name__ == "__main__":
    main()
