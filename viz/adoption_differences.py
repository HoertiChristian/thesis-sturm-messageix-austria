"""Adoption-level differences in 2040 buildings CO₂eq (RQ2), both accounting bases.

For each matrix pathway: 2040 emissions at stagnating and accelerated adoption
minus the baseline-adoption cell, on the territorial and the consumption basis;
for the Reference also the "no additional digitalization" cell (unscaled
coefficients) minus baseline. Writes ``results/tables/adoption_differences_2040.csv``
and ``results/figures/rq2_adoption_differences.png``.

Usage:
    python viz/adoption_differences.py [results_dir] [out_table] [out_fig]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DIGI_COLORS, co2_series

PATHWAYS = {"reference": "Reference", "renewables_push": "Renewables Push", "bio_bridge": "Bio-Bridge"}
LEVELS = {"none": "no additional digitalization", "stagnating": "stagnating", "accelerated": "accelerated"}
BASES = {"territorial": "buildings_co2.csv", "consumption": "buildings_co2_consumption.csv"}
YEAR = 2040


def main() -> None:
    results = Path(sys.argv[1] if len(sys.argv) > 1 else "results/runs")
    out_csv = Path(sys.argv[2] if len(sys.argv) > 2 else "results/tables/adoption_differences_2040.csv")
    out_png = Path(sys.argv[3] if len(sys.argv) > 3 else "results/figures/rq2_adoption_differences.png")

    rows = []
    for pid, plabel in PATHWAYS.items():
        for basis, csv in BASES.items():
            base = co2_series(results / f"pathway-{pid}__digi-baseline", (YEAR,), csv)
            if base is None:
                continue
            for lid, llabel in LEVELS.items():
                s = co2_series(results / f"pathway-{pid}__digi-{lid}", (YEAR,), csv)
                if s is None:
                    continue  # the no-additional-digitalization cell exists for the Reference only
                rows.append({
                    "pathway": plabel, "basis": basis, "level": llabel,
                    "co2_2040_kt": round(float(s[YEAR]), 1),
                    "baseline_2040_kt": round(float(base[YEAR]), 1),
                    "difference_to_baseline_kt": round(float(s[YEAR] - base[YEAR]), 1),
                })
    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    plt.rcParams.update({"font.size": 11})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=False)
    colors = {"no additional digitalization": "#444444",
              "stagnating": DIGI_COLORS["stagnating"], "accelerated": DIGI_COLORS["accelerated"]}
    width = 0.26
    for ax, basis in zip(axes, BASES):
        d = df[df["basis"] == basis]
        x = np.arange(len(PATHWAYS))
        for k, (llabel, colour) in enumerate(colors.items()):
            vals = [
                float(d[(d["pathway"] == p) & (d["level"] == llabel)]["difference_to_baseline_kt"].iloc[0])
                if not d[(d["pathway"] == p) & (d["level"] == llabel)].empty else np.nan
                for p in PATHWAYS.values()
            ]
            bars = ax.bar(x + (k - 1) * width, vals, width, color=colour, label=llabel)
            for b, v in zip(bars, vals):
                if not np.isnan(v):
                    ax.annotate(f"{v:+.1f}", (b.get_x() + b.get_width() / 2, v),
                                xytext=(0, 3 if v >= 0 else -9), textcoords="offset points",
                                ha="center", fontsize=8.5)
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(list(PATHWAYS.values()))
        ax.set_title(f"{basis.capitalize()} basis", fontsize=11)
        ax.set_ylabel("Difference to baseline adoption, 2040 (kt CO₂eq)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=9, title="Adoption level", title_fontsize=9)
    fig.suptitle("2040 buildings emissions by adoption level relative to baseline adoption", fontsize=11)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    print(df.to_string(index=False))
    print(f"table -> {out_csv}\nfigure -> {out_png}")


if __name__ == "__main__":
    main()
