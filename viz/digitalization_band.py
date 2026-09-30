"""Digitalization uncertainty band from Wilson et al. (2026) — W5.5 post-processing.

Mastrucci (2026-07-07, Q5): the global digitalization study (Wilson, Krey, …, Zakeri,
Mastrucci et al. 2026, Research Square 10.21203/rs.3.rs-8941019/v1) found buildings
digitalization can move energy demand **in both directions** vs the SSP2 reference —
Enable −5% (Cautious) to −22% (Extreme), Undermine (rebound/induced demand) +3% to
+9% by 2050 — and recommended applying such modifiers as post-processing for
flexibility. This tool wraps that range around each pathway's headline cell
(baseline digitalization) as an ex-post band on buildings CO₂:

    CO₂_band(y) = CO₂(y) × (1 + m × ramp(y)),   ramp(y) = (y − 2025) / (2050 − 2025)

with m ∈ {−0.05, −0.22, +0.03, +0.09} phased in linearly from the 2025 base year to
the study's 2050 endpoints. Modifiers scale buildings final energy uniformly across
fuels, so territorial CO₂ (Σ FE_fuel × EF_direct) scales by the same factor — the
per-fuel granularity of the preprint's SI can refine this once available.

Caveats (also for the thesis text): (i) global-study modifiers transferred to
Austria; (ii) ex-post — no system feedback, so under *binding* pathways
(Renewables Push, Bio-Bridge fossil caps) the band overstates what the constrained
system would emit; it is most meaningful for the unconstrained Reference, where the
2040 Undermine-Extreme band (+5.4%) exceeds the whole Macko RQ2 spread; (iii) the
Macko baseline-digitalization effect stays embedded in the headline — the band is
read as "if buildings digitalization landed anywhere in the globally observed range".

Writes ``results/tables/digitalization_uncertainty_band.csv`` and
``results/figures/digitalization_uncertainty_band.png``.

Usage:
    python viz/digitalization_band.py [results_dir] [out_table] [out_fig]
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
from _common import MILESTONE_YEARS, PATH_COLORS, co2_series

PATHWAYS = ("reference", "renewables_push", "bio_bridge")
YEARS = list(MILESTONE_YEARS)
BASE_YEAR, STUDY_YEAR = 2025, 2050

#: Wilson et al. (2026) buildings energy-demand modifiers vs SSP2 at 2050.
MODIFIERS = {
    "enable_extreme": -0.22,
    "enable_cautious": -0.05,
    "undermine_cautious": +0.03,
    "undermine_extreme": +0.09,
}

COLORS = PATH_COLORS  # one colour map across R and Python (viz/_common.py)


def _ramp(year: int) -> float:
    return max(0.0, min(1.0, (year - BASE_YEAR) / (STUDY_YEAR - BASE_YEAR)))


def _headline(results: Path, pathway: str) -> pd.Series | None:
    return co2_series(results / f"pathway-{pathway}__digi-baseline", YEARS)


def _solved_band(results: Path) -> dict[str, pd.Series]:
    """Endogenous Wilson cells (r7 B8), keyed by modifier name — empty if not run.

    The `ref_wilson_<name>` cells solve the Reference with the demand scaled by
    the ramped modifier, so their CO₂ carries the model's true demand→emissions
    elasticity (~2.5 in r6, vs the ex-post assumption of 1.0) and the band is
    directly comparable to the RQ2 spread. When all four exist the ex-post
    multiplication is skipped for the Reference; the capped pathways keep the
    ex-post band with its documented overstatement caveat.
    """
    out: dict[str, pd.Series] = {}
    for name in MODIFIERS:
        series = co2_series(results / f"pathway-ref_wilson_{name}__digi-baseline", YEARS)
        if series is not None:
            out[name] = series
    return out


def main() -> None:
    results = Path(sys.argv[1] if len(sys.argv) > 1 else "results/runs")
    out_csv = Path(
        sys.argv[2] if len(sys.argv) > 2 else "results/tables/digitalization_uncertainty_band.csv"
    )
    out_png = Path(
        sys.argv[3] if len(sys.argv) > 3 else "results/figures/digitalization_uncertainty_band.png"
    )

    solved = _solved_band(results)
    if solved and len(solved) < len(MODIFIERS):
        print(f"(only {sorted(solved)} solved — Reference band mixes solved and ex-post)")

    rows = []
    fig, (ax_ref, ax_ex) = plt.subplots(1, 2, figsize=(10.5, 4.6))
    plt.rcParams.update({"font.size": 11})
    labels = {"reference": "Reference", "renewables_push": "Renewables Push", "bio_bridge": "Bio-Bridge"}
    mod_label = {n: f"{m:+.0%}".replace("%", " %") for n, m in MODIFIERS.items()}
    for pathway in PATHWAYS:
        headline = _headline(results, pathway)
        if headline is None:
            print(f"(no baseline cell for {pathway} — skipped)")
            continue
        is_solved = pathway == "reference" and len(solved) == len(MODIFIERS)
        band = {
            name: (
                [float(solved[name][y]) for y in YEARS]
                if pathway == "reference" and name in solved
                else [float(headline[y]) * (1.0 + m * _ramp(y)) for y in YEARS]
            )
            for name, m in MODIFIERS.items()
        }
        if pathway == "reference" and solved:
            print(f"(reference band: {len(solved)}/4 endpoints from solved ref_wilson cells)")
        for i, y in enumerate(YEARS):
            values = [band[n][i] for n in MODIFIERS]
            rows.append(
                {
                    "pathway": pathway,
                    "year": y,
                    "headline_kt": float(headline[y]),
                    **{f"{n}_kt": band[n][i] for n in MODIFIERS},
                    "band_min_kt": min(values),
                    "band_max_kt": max(values),
                }
            )
        c = COLORS[pathway]
        lo = [min(band[n][i] for n in MODIFIERS) for i in range(len(YEARS))]
        hi = [max(band[n][i] for n in MODIFIERS) for i in range(len(YEARS))]
        if is_solved:
            # The territorial band of the solved Reference cells has width zero (the
            # emitting activities sit on their floors), so the left panel shows the
            # solved cells on the CONSUMPTION basis, where the demand change is visible,
            # and states the territorial identity as text.
            ax = ax_ref
            cons_head = co2_series(results / "pathway-reference__digi-baseline", YEARS,
                                   csv="buildings_co2_consumption.csv")
            cons = {
                name: co2_series(results / f"pathway-ref_wilson_{name}__digi-baseline", YEARS,
                                 csv="buildings_co2_consumption.csv")
                for name in MODIFIERS
            }
            c_lo = [min(float(cons[n][y]) for n in MODIFIERS) for y in YEARS]
            c_hi = [max(float(cons[n][y]) for n in MODIFIERS) for y in YEARS]
            ax.fill_between(YEARS, c_lo, c_hi, color=c, alpha=0.18, linewidth=0,
                            label="band of the four solved cells")
            for name in MODIFIERS:
                ax.plot(YEARS, [float(cons[name][y]) for y in YEARS], "-", color=c,
                        alpha=0.6, linewidth=0.9)
                ax.annotate(mod_label[name], (YEARS[-1], float(cons[name][YEARS[-1]])),
                            xytext=(4, 0), textcoords="offset points", fontsize=8.5,
                            color=c, va="center")
            ax.plot(YEARS, [float(cons_head[y]) for y in YEARS], "-o", color=c,
                    label="baseline adoption (headline)")
            ax.text(0.02, 0.04,
                    f"Territorial basis: all four cells equal the headline\n"
                    f"({float(headline[YEARS[-1]]):,.1f} kt in 2040) — the emitting\n"
                    f"activities sit on their floors.",
                    transform=ax.transAxes, fontsize=8.5, color="0.25", va="bottom")
        else:
            ax = ax_ex
            ax.fill_between(YEARS, lo, hi, facecolor="none", edgecolor=c, hatch="//",
                            linewidth=0.6, linestyle="--", alpha=0.8,
                            label=f"{labels[pathway]}: ex-post transfer")
            ax.plot(YEARS, headline, "-o", color=c, label=f"{labels[pathway]}: headline")

    ax_ref.set_title("Reference: solved demand-band cells (consumption basis)", fontsize=11)
    ax_ex.set_title("Renewables Push, Bio-Bridge: ex-post transfer (territorial basis)", fontsize=11)
    ax_ref.set_ylabel("Buildings CO₂eq, consumption basis (kt)")
    ax_ex.set_ylabel("Buildings CO₂eq, territorial (kt)")
    for ax in (ax_ref, ax_ex):
        ax.set_xlabel("Year")
        ax.set_xticks(YEARS)
        ax.set_xlim(YEARS[0] - 0.5, YEARS[-1] + 2.2)
        ax.legend(frameon=False, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Digitalization demand band (Wilson et al. 2026 modifiers, −22 % to +9 % at 2050, ramped from 2025)",
                 fontsize=11)
    fig.tight_layout()

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    fig.savefig(out_png, dpi=200)

    df = pd.DataFrame(rows)
    if df.empty:
        print("no band rows — no headline cells found under the results directory")
        return
    at_2040 = df[df["year"] == 2040]
    for _, r in at_2040.iterrows():
        print(
            f"{r['pathway']:>16} 2040: {r['headline_kt']:8.1f} kt, band "
            f"[{r['band_min_kt']:8.1f}, {r['band_max_kt']:8.1f}] "
            f"(+{r['band_max_kt'] - r['headline_kt']:.1f} / "
            f"−{r['headline_kt'] - r['band_min_kt']:.1f} kt)"
        )
    print(f"table -> {out_csv}\nfigure -> {out_png}")


if __name__ == "__main__":
    main()
