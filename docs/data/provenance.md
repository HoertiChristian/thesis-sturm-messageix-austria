# Provenance of baked input values

Narrative companion to the **`provenance` sheet of `data/inputs.xlsx`** (the
sheet is the machine-readable record; this file explains each row). It covers
every thesis-authored value that is *baked into* an input artifact — the STURM
input CSVs under `src/sturm/data/` or the baseline workbook
`data/MESSAGEix-AT_baseline_4.xlsx` — rather than read from `inputs.xlsx` at
runtime.

The `tools/` scripts that did the baking were removed on **2026-07-13** in the
workbook-single-source refactor: the baked data is committed, so the scripts are
no longer needed to run the model. They are not part of this repository
(development history; available from the author on request).

## Fuel-switch rates (`fuel_switch_rate_gas`, `fuel_switch_rate_oil`)

Per-year share of the gas-/oil-heated stock allowed to switch heating fuel:
**0.02 /yr for gas, 0.01 /yr for oil** (`bld_age_min = 20`, 2020–2100). Baked
into `src/sturm/data/input_csv_SSP_2023_resid/rate_switch_fuel_heat_ssp2.csv`
(AUT rows) by `tools/build_switch_rates.py`. Source: FFPH convention; W5.3
switch-rate scope (2026-07-10).

## Renovation-rate ceiling (`renovation_rate_ceiling`)

**0.03 /yr from 2030** (2020/2025 keep the observed rate). A ceiling, not a
forcing — STURM chooses renovation up to it. Baked into
`src/sturm/data/input_csv_SSP_2023_resid/ren_rate_en_max_ssp2_AT_TARGET.csv`
plus the manifest variant column (`rate_ren_high`) by
`tools/build_renovation_variant.py`. Source: Austrian renovation-rate policy
target; W5.2 renovation dial (2026-07-10).

## Heat-pump share of electric heat (`hp_share_electric_heat`)

**0.7** — the heat-pump fraction of electric-heated dwellings, used for the
`elec_hp` carrier split across the resid input CSVs
(`src/sturm/data/input_csv_SSP_2023_resid/*.csv`). Baked by
`tools/build_fuelset.py`. Source: Statistik Austria Mikrozensus 2023/24 (W5.6
explicit `elec_hp` fuelset, 2026-07-10).

## Legacy heat-pump COP (`hp_legacy_cop`)

**2.5** — efficiency of existing air-source heat pumps in unrenovated buildings
(legacy building classes `ns`/`s1`/`s2`/`s3`; the new classes
`s51_std`/`s52_low` use STURM defaults). Baked into the resid CSVs (legacy
`elec_hp` efficiency) by `tools/build_fuelset.py`. Source: assumption
(2026-07-10).

## Intangible-cost transition gates (`cost_int_ren_transition_gates`)

**99999 (blocked) / 0 (allowed)** — intangible-cost gates in
`src/sturm/data/input_csv_SSP_2023_resid/cost_int_ren.csv` encoding which
heating-system transitions are legal, including the resistive-heating exclusion
and the district-heat choice. Baked by `tools/build_fuelset.py` (W5.4/W5.6,
2026-07-10).

## Digitalization operating-hours variants (`digitalization_operating_hours`) — removed 2026-09-13

The `SSP2_DIG_{baseline,stagnating,accelerated}` manifest variants
(`heat_operation_hours_dig_*.csv` plus their manifest columns) drove the r7
operating-hours channel. They were built from the Macko (2025)
`Smart_space_heating` × `Residential` reduction factors, re-based to 0 at 2025 and
held flat after 2040 — the same series the r8 efficiency channel reads from the
`macko_reduction` sheet at runtime (`linkage/digital.py`). Removed with the r8-only
prune (changelog §27); being derived from the Macko data, they are not part of this
repository.

## Baseline-4 calibration chain (`baseline4_calibration_chain`)

`data/MESSAGEix-AT_baseline_4.xlsx` differs from the raw IIASA handover by:
`firstmodelyear` → 2025 (2020–24 historicised), the `rc_spec` demand reconciled
to the STATcube reference, the `sp_el_RC` history rescaled, and the buildings
CO₂ `emission_factor` rows added. Applied by `tools/build_baseline_4.py`,
`tools/add_buildings_emissions.py` and `tools/patch_sp_el_history.py`
(2026-06/07). The full per-change record is `docs/data/baseline_4_changelog.md`
+ `docs/data/calibration_changelog.md`. The runtime only *validates* the baked
result (`_assert_baseline_calibrated`); it never mutates the workbook.

## Emission-factor basis (`emission_factor_basis`)

UBA **REP-0989** (Datenstand 2025; direct + total incl. upstream; e.g. biomass
0.015 direct, electricity 0.152 total), adopted 2026-08-25 — superseding
REP-0948 (adopted 2026-07-05, electricity 0.209 total), which superseded
REP-0888. All territorial/direct factors are identical across REP-0948/0989;
only the consumption-basis electr (0.209→0.152) and d_heat (0.172→0.166)
totals moved (`calibration_changelog.md` §18). The sheet was originally written
by `tools/build_inputs_workbook.py` (from the retired
`config/emission_factors.yaml`) and re-baked in place for each edition.

## Macko reduction export (`macko_reduction_export`)

The Macko (2025) master's-thesis digitalization outputs ("Reduction - results",
Google Drive export 2026-05-17) — an upstream input, never edited. The tables
live in `data/macko_reduction.xlsx` (sheet `macko_reduction`; originally written to
`inputs.xlsx` by `tools/build_inputs_workbook.py`; restricted, available on request); the raw CSV tree was removed from the repo
with the refactor and is not part of this repository (development history).

## Reference final energy export (`reference_final_energy_export`)

The Statistik Austria **Nutzenergieanalyse** STATcube export, parsed into the
`reference_final_energy` sheet of `inputs.xlsx` by `tools/build_reference.py`
(2026-06). The raw exports remain in `data/austria_raw/` (see `SOURCES.md`
there).

## EAG wind target (`eag_wind_target`)

The EAG **+10 TWh wind** floor is **not imposed** — only solar floors are in the
`renewable_floors` sheet. 2026-07-05 probes showed the wind floor is infeasible
in the received baseline: its VRE-integration layer caps absorbable wind at
≈ 7.8 TWh (a downscaling artifact, not an Austrian resource limit). Documented
limitation — the Renewables Push pathway under-delivers the EAG renewables total
for a model-structural reason.

### Check 2026-09-13 — commercial columns of the Macko export

Compared the raw 2026-05-17 export (git history, `src/Macko-analysis/Reduction - results/…`)
sector by sector: `Smart_space_heating`, `Smart_cooling` and `AI_DESI` are byte-identical
between the Commercial and Residential files; `Smart_lighting` and `Smart_appliances`
differ. The identity therefore originates in Macko's own export, not in the workbook
conversion (the `macko_reduction` sheet reproduces the files). Consequence for the thesis:
a "commercial series" for space heating does not exist in the tables received, although
Macko (2025) Table 7 gives 20 % (residential) vs 10 % (commercial) reduction potentials.
No workbook change (the commercial columns are not read at runtime); recorded as a
limitation and an outlook item in the thesis.
