# Visualisations (R / ggplot2) + summary tables (Python)

`plots.R` reads the run outputs in `results/runs/<scenario-id>/*.csv` and renders
the figures below (PNG @ 300 dpi + a combined `figures.pdf`) into an output
directory. The Python scripts extract the tables and sensitivity artifacts to
`results/tables/` (+ two matplotlib figures). One colour map is shared across R
and Python (Okabe–Ito; `PATH_COL`/`DIGI_COL` in `plots.R` are the canon).

## Run

```bash
Rscript viz/plots.R [results_dir] [out_dir]
# defaults: results/runs   results/figures
python viz/summary_tables.py [results_dir] [out_dir]
# defaults: results/runs   results/tables
```

| Script | Writes | When |
|---|---|---|
| `summary_tables.py` | `buildings_co2_by_year{,_consumption}.csv`, `gap_to_target_2040.csv`, `rq2_spread{,_consumption}.csv` | every harvest |
| `convergence_table.py` | `convergence_evidence.csv` (from the newest runlog) | every harvest |
| `digitalization_band.py` | Wilson band table + figure (prefers the solved `ref_wilson_*` cells) | every harvest |
| `shape_sensitivity.py` | fossil-exit shape table + figure | every harvest |
| `ladder_table.py` | `carbon_price_ladder.csv` (threshold finding) | every harvest |
| `buildings_final_energy.py` | `buildings_final_energy_by_fuel.csv`, `consumption_decomposition_2040.csv`, `emission_factors.csv` | every harvest; needs the restricted `data/macko_reduction.xlsx` (see `data/README.md`) — the committed outputs cover the thesis runs |

All scripts except `buildings_final_energy.py` run from the committed `results/`
alone, without the restricted inputs.

(The former `build_deck.py` pptx generator was retired 2026-09-04 and is not
part of this repository.)

Both `plots.R` and `summary_tables.py` auto-discover every `pathway-*__digi-*`
run directory but keep only the matrix pathways (Reference, Renewables Push,
Bio-Bridge) — ad-hoc probe runs such as `pathway-ref_tax120__digi-*` are dropped.
A run directory missing a CSV (e.g. an older run without `buildings_co2.csv`) is
skipped per-figure, not fatal.

## Figures

2040 target lines use the UBA REP-0995 (2025) basis: WAM 1,300 kt (target path)
and WEM 3,400 kt (existing-measures benchmark; REP-0951's 5,100 kt is superseded). The legacy LTRS ~3,900 kt
milestone is footnote-only and not plotted.

| File | Source CSV | Shows |
|------|-----------|-------|
| `emissions_trajectory_territorial.png` | `buildings_co2.csv` | Buildings CO₂eq 2025–2040 per scenario, territorial basis, vs the WAM/WEM target lines (RQ1). |
| `emissions_trajectory_consumption.png` | `buildings_co2_consumption.csv` | Consumption-basis trajectory (incl. electricity & district heat) — sensitivity. |
| `gap_to_target.png` | `buildings_co2.csv` | RQ1 — 2040 CO₂ per pathway vs the WAM/WEM targets. |
| `rq2_digitalization.png` / `rq2_digitalization_bars.png` | `buildings_co2.csv` | RQ2 — CO₂ spread across digitalization levels. |
| `buildings_fuel_mix.png` | `activity_rc.csv` | Buildings end-use activity by technology, stacked (RQ2). |
| `heating_transition.png` / `heating_transition_gwa.png` | `activity_rc.csv` | Heat-pump takeover — share of heating / absolute GWa. |
| `buildings_co2_by_source.png` | `buildings_co2_by_fuel.csv` | CO₂ decomposition by fuel. |
| `base_year_validation.png` | `base_year_check.csv` | Modelled 2025 vs Statistik-Austria 2024 final energy by fuel. |
| `system_final_energy.png` | `final_energy_by_fuel.csv` | Whole-system final energy by carrier (context). |

Colours are fixed per fuel/technology (Okabe–Ito, colour-blind safe) so figures are
comparable across scenarios and runs.

Two standalone scripts complement the set: `convergence_table.py` (the
convergence-evidence table from the newest run log) and `shape_sensitivity.py`
(logistic-vs-linear fossil-exit comparison of the Renewables Push runs against
their `*__shape-linear` variant folders → `results/tables/shape_sensitivity.csv`
+ `results/figures/shape_sensitivity.png`).

## Requirements

R with `ggplot2`, `readr`, `dplyr`, `tidyr`, `scales`. R is already needed for STURM;
install the plotting packages with e.g.
`Rscript -e 'install.packages(c("ggplot2","readr","dplyr","tidyr","scales"))'`.
