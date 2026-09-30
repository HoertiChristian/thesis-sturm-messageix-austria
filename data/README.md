# Data

## `inputs.xlsx` — the single source of truth for tunable parameters

Every tunable parameter is read from this workbook at model setup and nowhere
else; a missing sheet, column, or key raises immediately. Edit values here (the
workbook is git-versioned), never in code. Sheets:

| Sheet | Contents | Read by |
|-------|----------|---------|
| `config` | Run options as `key`/`value` rows (base year, horizon, tolerances, damping, linkage/digitalization modes, model/scenario names) | `Config.load()` |
| `pathways` | The 3 climate-neutrality pathways with their dials (fossil-exit year, carbon price, renewable expansion, …) | `common.scenarios.pathways()` |
| `digitalization` | The 3 digitalization levels and their Macko scenario mapping | `common.scenarios.digitalization_levels()` |
| `reference_final_energy` | Statistik Austria buildings final energy `[year, commodity, fuel, value_gwa]` | `common.reference` |
| `emission_factors` | Per-fuel CO₂eq factors `[fuel, ef_direct, ef_total]`, tCO₂eq/MWh (UBA REP-0989) | `messageix.emissions` |
| `targets` | 2040 buildings-sector emission targets (REP-0995 WAM/WEM), UBA inventory anchor + base-year tolerance | `common.validation` |
| `carbon_price_paths` | Legislated CO₂-price time paths `[id, year, usd_per_t, source]` (NEHG 2025 anchor + REP-0995 Tabelle 1) | `messageix.pathways` |
| `pathway_constants` | Fossil-exit leads (Kettner 2026), logistic steepness, gas-power residual, baseline electrification level | `messageix.pathways` |
| `renewable_floors` | EAG solar expansion floors (TWh additional vs 2020) per expansion level and year | `messageix.pathways` |
| `provenance` | Documentation only (never read at runtime): every value baked into the STURM CSVs / baseline workbook by the retired `tools/*` scripts, with source and date | — |
| `notes` | Free-form documentation | — |

Values that are *baked into* other input files (STURM CSVs, the baseline
workbook) are recorded in the `provenance` sheet; the scripts that originally
baked them (pre-refactor `tools/`) are not part of this repository.

## The Austrian buildings reference (`reference_final_energy` sheet)

Austrian buildings final energy by commodity (`rc_therm`/`rc_spec`) × fuel, in
GWa, for the base year. Derived from **Statistik Austria — Nutzenergieanalyse**
(STATcube), residential + commercial (services), with the energy-balance
"Counting" variant. Mapping: `rc_therm` = "Space and water heating" (all fuels);
`rc_spec` = electricity in the lighting/stationary/electrochemical categories;
Traction and Process heat excluded. 1 GWa = 31.536 PJ. The raw STATcube exports it
was parsed from are registered in `data/austria_raw/README.md` (the exports
themselves are not redistributed); the parser (pre-refactor
`tools/build_reference.py`) is not part of this repository.

## Third-party assets and restricted inputs

STURM is bundled under its upstream licence. Two inputs are **not included** in
the public repository, because their originators have not (yet) confirmed
redistribution; both are **available on request** from the author. To run the
pipeline, place them at the paths below (both paths are gitignored). Without
them, the code raises a `FileNotFoundError` that names the missing file; the
result tables in `results/` document the r8 runs reported in the thesis.

| Asset | Path | Source / licence |
|-------|------|------------------|
| **STURM** building-stock model (R) + input data | `src/sturm/` (`model/`, `data/`, `run_sturm_headless.R`) — included | IIASA `message_ix_buildings` (Apache-2.0) |
| **MESSAGEix-Austria baseline** workbook | `data/MESSAGEix-AT_baseline_4.xlsx` — *not included, available on request* (calibration + buildings CO₂ emission factors baked in — see `docs/data/baseline_4_changelog.md`) | derived from the IIASA Austria guideline handover |
| **Macko (2025)** digitalization reduction tables | `data/macko_reduction.xlsx`, sheet `macko_reduction` (long form: `technology`, `sector`, `Year`, `Baseline_Digitalization`, `Accelerated_Digitalization`, `Stagnating_Digitalization`) — *not included, available on request* | Macko (2025) master's thesis outputs |

Only STURM's regeneratable run outputs (`src/sturm/output/`) are gitignored.

Running the linkage end-to-end additionally requires a full **GAMS** licence, the
**R** runtime (`Rscript`), and the `model` extra (`message_ix`, `ixmp`) — these are
environment prerequisites, not repo files. The package imports and `pytest -m "not
slow"` run without GAMS/the IIASA Python stack.
