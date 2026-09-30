"""Logistic vs linear fossil-exit shape — the W2.3 sensitivity comparison.

Compares the Renewables Push cells solved with the default logistic phase-out
against the ``*__shape-linear`` variant folders: buildings CO₂ per year, the
2040 endpoint (identical by construction — both shapes hit the ban years) and
the cumulative 2025–2040 emissions (5-year step weights). Writes
``results/tables/shape_sensitivity.csv`` and
``results/figures/shape_sensitivity.png``.

Usage:
    python viz/shape_sensitivity.py [results_dir] [out_table] [out_fig]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DIGI_COLORS, MILESTONE_YEARS, co2_series

DIGI = ("stagnating", "baseline", "accelerated")
YEARS = list(MILESTONE_YEARS)
#: Period weight for cumulative emissions on the 5-year grid (kt·yr).
STEP = 5.0


def _series(run_dir: Path) -> pd.Series:
    return co2_series(run_dir, YEARS)


def main() -> None:
    results = Path(sys.argv[1] if len(sys.argv) > 1 else "results/runs")
    out_csv = Path(sys.argv[2] if len(sys.argv) > 2 else "results/tables/shape_sensitivity.csv")
    out_png = Path(sys.argv[3] if len(sys.argv) > 3 else "results/figures/shape_sensitivity.png")

    rows = []
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = DIGI_COLORS  # one colour map across R and Python (viz/_common.py)
    for d in DIGI:
        log_s = _series(results / f"pathway-renewables_push__digi-{d}")
        lin_dir = results / f"pathway-renewables_push__digi-{d}__shape-linear"
        if not lin_dir.exists():
            print(f"(no linear variant for {d} — skipped)")
            continue
        lin_s = _series(lin_dir)
        cum_log = float((log_s * STEP).sum())
        cum_lin = float((lin_s * STEP).sum())
        rows.append({
            "digitalization": d,
            "co2_2030_logistic_kt": round(float(log_s[2030]), 1),
            "co2_2030_linear_kt": round(float(lin_s[2030]), 1),
            "co2_2035_logistic_kt": round(float(log_s[2035]), 1),
            "co2_2035_linear_kt": round(float(lin_s[2035]), 1),
            "co2_2040_kt_both": round(float(log_s[2040]), 1),
            "cumulative_logistic_kt_yr": round(cum_log, 0),
            "cumulative_linear_kt_yr": round(cum_lin, 0),
            "cumulative_diff_pct": round(100 * (cum_lin - cum_log) / cum_log, 2),
        })
        ax.plot(YEARS, log_s, "-o", color=colors[d], label=f"{d} (logistic)")
        ax.plot(YEARS, lin_s, "--s", color=colors[d], alpha=0.6, label=f"{d} (linear)")

    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    ax.set_xlabel("Year")
    ax.set_ylabel("Buildings CO₂eq, territorial (kt)")
    ax.set_title("Renewables Push: logistic versus linear fossil exit")
    ax.set_xticks(YEARS)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    print(f"wrote {out_csv} and {out_png}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
