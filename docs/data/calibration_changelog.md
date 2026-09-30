---
title: Calibration changelog — what is calibrated, where, and from which source
date: 2026-06-30
covers: the state of base-year calibration baked into the input files (baseline_4.xlsx, inputs.xlsx, STURM CSVs)
repo: sturm-messageix (this repository)
related:
  - docs/data/baseline_4_changelog.md
  - thesis note 2026-06-22_baseyear_calibration_emissions_decisions.md (thesis records, not in this repo)
status: living log — append a section for every calibration change; one source of truth for "what was adjusted and why"
---

# Calibration changelog

> Reader note: entries below cite the author's thesis records (`Thesis/...`,
> `docs/notes/...`, review reports, PDFs). Those are working notes outside this
> repository; the values, sources and decisions themselves are stated in the
> entries.

**Policy.** All base-year / baseline calibration lives in
the **input files**, baked there by the offline `tools/*` scripts. Runtime code
**imports and validates** the calibration (`model/build.py:_assert_baseline_calibrated`)
— it must never mutate calibration parameters (`demand`, `historical_*`, `firstmodelyear`)
in the load path. The **one exception** is the STURM↔MESSAGEix activity-bound anchoring
in `linkage/bounds.py`: it is the per-iteration coupling, not base-year calibration, so it
is recomputed each loop — but it anchors only to reference *levels* that themselves live in
`inputs.xlsx` (see §6).

Every calibration adjustment is recorded below with its **value, rationale, source, and
where it lives in code/data**.

---

## 1. `rc_spec` demand reconciliation → baked into `baseline_4.xlsx`

**Decision.** The guideline baseline's residential/commercial **specific-electricity**
(`rc_spec`) demand is rescaled so the modelled base-year (2025) *final* specific
electricity equals the Statistik Austria reference. The whole `rc_spec` trajectory
(years ≥ base year) is multiplied by one factor; history (< base year) is untouched.

**Why.** The guideline `rc_spec` sits well above the Austrian statistic at the base year,
over-electrifying buildings. STATcube `rc_spec` covers lighting/stationary/electrochemical
only — narrower than the baseline's demand — so the factor is well below 1.

**Basis.** Reference is *final* electricity, `demand` is *useful*; bridged by the `sp_el_RC`
final→useful end-use coefficient (≈ 1.48 at 2025). Target useful demand = `reference_final ÷ coef`,
so modelled final (`demand × coef`) matches the reference.

**Source.** STATcube Nutzenergieanalyse, `calibration_year = 2024`, forward-reconciled to
`base_year = 2025`. Loaded via `reference_commodity_total("rc_spec", 2024)` from
`inputs/reference.py` (pre-refactor path; now `src/common/reference.py`) ← `data/inputs.xlsx` sheet `reference_final_energy`.

**Where.** Baked by `tools/build_baseline_4.py` calling `model/build.reconcile_rc_spec_demand`;
result is the 13 changed `demand` rows in `baseline_4.xlsx` (per `baseline_4_changelog.md`).
**Runtime no longer re-runs this** — `_assert_baseline_calibrated` only checks the baked
result is within `validation/base_year.TOLERANCE` (3%) of the reference.

**Status.** Done, baked, validated.

---

## 2. `firstmodelyear` advance 2020 → 2025 + re-historicize → baked into `baseline_4.xlsx`

**Decision.** Advance the model's first optimised year from 2020 to the 2025 base year;
the folded 2020/2025-pre years become history (`historical_activity`,
`historical_new_capacity`).

**Why.** Base year moved 2020 → 2025 (see related 2026-06-22 note §1); MESSAGEix treats
pre-`firstmodelyear` years as fixed history, so their endogenous levels must be written
as history rather than re-optimised.

**Source.** One baseline solve (GAMS) at bake time produces the levels.

**Where.** Baked by `tools/build_baseline_4.py` calling `model/build.advance_first_model_year`;
result is `cat_year` firstmodelyear advanced + 152 `historical_activity` + 32
`historical_new_capacity` rows in `baseline_4.xlsx`. Runtime no longer solves or advances —
`_assert_baseline_calibrated` checks `firstmodelyear == base_year`.

**Status.** Done, baked. Requires GAMS only at bake time, not at run time.

---

## 3. Statistik Austria buildings reference levels → `data/inputs.xlsx`

**Decision.** Austrian final-energy-by-fuel reference levels are curated into the input
workbook, not hard-coded.

**Source.** STATcube Nutzenergieanalyse export under `data/austria_raw/` (see
`data/austria_raw/SOURCES.md`), mapped to model fuels by `tools/build_reference.py`.

**Where.** `data/inputs.xlsx` sheet `reference_final_energy` (fallback
`data/austria_buildings_reference.xlsx`), read by `inputs/reference.py`. Only unit/fuel
metadata is constant in code (`TJ_PER_GWA`, `MODEL_FUELS`); the GWa values live in the xlsx.

**Status.** Done, file-resident.

---

## 4. STURM Austrian region overrides → baked into the STURM input CSVs

**Decision.** The Austrian (`C-AUT`) rows of the STURM input CSVs are overwritten with
Austrian data offline; STURM's WEU defaults are kept for the fallback region.

**Source / Where.** `inputs/austria_sturm/build.py` (run as a module), drawing on
`inputs/austria_sturm/statcube.py` parsers of `data/austria_raw/*`. Five files:
fuel-heat shares, district-heat fraction, population (Statistik Austria), mean household
size, base-year vintage stock shares.

**Status.** Done, baked into `src/sturm/data/input_csv_SSP_2023_{resid,comm}/`.

---

## 5. `base_hp_share = 0.70` — set from Statistik Austria (was provisional 0.5)

**Decision.** Base-year split of electric building heat between resistive and heat-pump is
**0.70 heat-pump / 0.30 resistive** (useful energy), set from Austrian data (previously a
provisional 50/50).

**Source.** `data/austria_raw/heatpump/08Heizungen2003Bis2024NachBundeslaendernUndVerwendetemEnergietraeger.ods`,
sheet *Österreich*, block **2023/2024** (Statistik Austria, *Mikrozensus Energieeinsatz der
Haushalte 2023/24*, created 14.05.2025). Primary-residence dwellings by primary heating
energy carrier: **Strom** (resistive electric) = **258,086**; **Solar, Wärmepumpen** (heat
pumps) = **591,874**. → `base_hp_share = 591,874 / (591,874 + 258,086) = 591,874 / 849,960 = 0.696 ≈ 0.70`.

**Basis / caveats.** (i) **Dwelling counts**, not useful energy — fine for a base-year split
that does not affect either CO₂ metric (both are electricity, zero on the territorial basis);
it is a realism/narrative parameter. (ii) "Solar, Wärmepumpen" is a combined Statistik Austria
category, but solar as a *primary* heating system is negligible, so it ≈ heat pumps. (iii) The
companion file `02Gesamteinsatz…ods` gives household final energy by carrier but does **not**
split electricity into resistive vs heat-pump, so the 08 file is the source.

**Where.** `Config.base_hp_share` (`config.py`, `config/config.yaml`); applied in the base-year
electric-heat split in `linkage/bounds.py` (`_electric_heat_target_rows`). Lives in the
`inputs.xlsx` config sheet via `Config.load` (regenerate `inputs.xlsx` after editing the yaml).

**Status.** Done — sourced from Statistik Austria 2023/24. Changes only the base-year
`elec_rc`/`hp_el_rc` split, not CO₂; a re-solve refreshes the base-year split in the figures.

---

## 6. STURM→Austria activity-bound anchoring — runtime exception (not pre-baked)

**Decision.** STURM thermal trajectories are anchored to Austrian reference *levels* each
linkage iteration: `target(y) = anchor × F_fuel(y)/F_fuel(anchor)`, with the base year pinned
as an equality (`base_bound_tol = 0.0`) and projection years given a ±`bound_tol` (2%) corridor.

**Why not in a file.** The trajectory `F_fuel(y)` comes from the live per-iteration STURM
solve, so the bound values cannot be static. This is the coupling itself, not base-year
calibration — hence it stays in code by design.

**Source.** Anchor levels = `load_reference(calibration_year)` ← `inputs.xlsx`
`reference_final_energy`; tolerances from `config.py`.

**Where.** `linkage/bounds.py` (`_anchor_level`, `_thermal_target_rows`,
`_electric_heat_target_rows`, `apply_activity_bounds`).

**Status.** Intentional runtime behaviour; documented as the policy exception.

---

## 7. Endogenous buildings CO₂ (`emission_factor`) → baked into the baseline workbook

**Decision.** Attach a `CO2` `emission_factor` to the emitting buildings techs so the model
solves buildings CO₂ in-model (`EMISS`, MtCO₂, territorial basis), instead of only computing
it post-hoc. Adds the `CO2` emission species + the `GHG` `type_emission` category. Techs:
`gas_rc, loil_rc, coal_rc, biomass_rc` (territorial `EF_DIRECT`; `heat_rc`/electric techs = 0,
so none). This aligns the linkage with the standard message_ix idiom (emissions endogenous,
not spreadsheet-reconstructed) and lets a carbon price/cap drive fuel switching.

**Why / basis.** `emission_factor` multiplies *activity*, not fuel input, so the per-activity
factor folds in each tech's final-energy input coefficient (vintage-varying):
`emission_factor = input_coef × EF_DIRECT × 8.76` (tCO₂/kWa). Unit algebra: `ACT` [GWa] ×
`emission_factor` [tCO₂/kWa] = `EMISS` [MtCO₂] (1 GWa = 1e6 kWa). Only the buildings techs
carry a `CO2` factor, so `EMISS[CO2]` *is* the buildings sector. **Territorial basis only** —
`emission_factor` is single-valued, so the consumption-basis number stays the post-hoc
`buildings_co2_consumption.csv` sensitivity.

**Source.** `EF_DIRECT` from `config/emission_factors.yaml` → `inputs.xlsx` `emission_factors`
sheet (UBA REP-0888 2023; see §3-adjacent emission-factor entry), via
`report.emission_factors("direct")`.

**Where.** `model/build.add_buildings_emissions` (+ `_buildings_emission_factor_rows`); baked
by `tools/build_baseline_4.py` (server) and the standalone, no-solve
`tools/add_buildings_emissions.py` (local). **Validation:** `_assert_baseline_calibrated`
*warns* (not fails) if the `CO2` factor is absent — unlike the rc_spec/firstmodelyear
calibration (shipped in `baseline_4`), this addition may post-date the on-disk workbook, and
post-hoc CO₂ still works without it.

**Status.** Code done. **Re-baked 2026-07-04** (`tools/add_buildings_emissions.py local`):
the on-disk `baseline_4.xlsx` now carries the 900 `emission_factor` rows (CO2 on
gas_rc/loil_rc/coal_rc/biomass_rc, e.g. gas_rc ≈ 2.13 tCO2/kWa at 2025) and `CO2` in
the emission set — endogenous `EMISS` and the carbon-policy dials are live on any
fresh import. NB (same date): the earlier ~2× "endogenous vs post-hoc" discrepancy was
a *reporting* bug (EMISS summed over the model node **and** its World parent aggregate),
fixed in `report/emissions.py`; the server-side bake had been correct.

---

## 8. Carbon-policy dials (`tax_emission` / `bound_emission`) — per-pathway runtime lever

**Decision.** A pathway may set `carbon_price` (flat USD/tCO₂) and/or `emission_budget`
(cumulative MtCO₂). `carbon_price` → `tax_emission` on every model year; `emission_budget` →
cumulative `bound_emission`. Both target `type_emission="GHG"`, `type_tec="all"`.

**Why not pre-baked.** This is a *scenario* lever, not a baseline calibration — it differs per
pathway, so it is applied at runtime in `model/pathways.apply_pathway` (the non-activity-constraint
hook). It is *not* an activity bound, so the linkage loop does not overwrite it.

**Source / Where.** `Pathway.carbon_price` / `.emission_budget` from `config/scenarios.yaml`
(→ `inputs.xlsx` `pathways`); applied in `model/pathways._apply_carbon_policy`. No-op with a
warning if the `CO2` emission bake (§7) is absent.

**Status.** Code done; all matrix pathways currently set both to `null` (no carbon policy), so
the Reference/Renewables-Push/Bio-Bridge results are unchanged until a price/budget is set.

---

## 9. sp_el_RC `historical_activity` rescale — the +7.1 % base-year electricity fix

**Problem (diagnosed 2026-07-04).** The base-year check failed for electricity in every
cell (+7.14 %, modelled 3.4024 vs reference 3.1757 GWa final; only TOTAL passed). The
thermal side was exact — the entire deviation came from `sp_el_RC`: the rc_spec demand
re-scoping (§3) scaled demand from the base year onward but left `historical_activity`
(2020 = 1.88 GWa) at the old, broader scope. The baseline's dynamic no-decline
constraint (`growth_activity_lo` −5 %/yr + `initial_activity_lo` 0.016) then floored
base-year activity at `1.88·0.95⁵ − 0.016·(1−0.95⁵)/0.05 = 1.3823` — exactly the solved
ACT — above the reconciled demand of 1.2294, forcing +0.2267 GWa of surplus final
electricity.

**Fix.** `reconcile_rc_spec_demand` now also rescales `sp_el_RC`'s pre-base-year
`historical_activity` by the same factor (scope consistency across the timeline);
the already-baked `baseline_4.xlsx` was patched in place on 2026-07-04 via
`tools/patch_sp_el_history.py` (factor 1.229387/2.584000 = 0.4758; all 7 history
years scaled, 2020 → 0.8944; new 2025 floor 0.62, non-binding).

**Expected effect (verify on the next solve).** Base-year `sp_el_RC` activity binds at
the demand → final electricity 1.2294 × 1.4822 = 1.8222 = reference; the electricity
check passes ≈ 0 % and TOTAL tightens from +2.11 % to ≈ 0. The CO₂ headline (5,598 kt)
is unaffected — electricity is zero-rated on the territorial basis. Coal remains
`passed=False` (modelled 0 vs reference 0.0051 GWa; immaterial).

**Source.** Factor derived from the workbooks (baseline_4 vs baseline_3 base-year
rc_spec demand); constraint arithmetic verified against the solved run outputs.

---

## 10. Emission factors re-sourced to UBA REP-0948 (Datenstand 2024)

**Decision (2026-07-05, user).** The CO₂e factor basis moves from REP-0888 (Datenstand
2023) to its successor **REP-0948** (*Harmonisierte österreichische direkte und
vorgelagerte THG-Emissionsfaktoren*, Datenstand 2024, Wien 2025) — pdf at
`Thesis/docs/literature/to-read/rep0948.pdf`; Tabelle 1 (Raumwärme, p. 9) and
Tabelle 4 (Strom, p. 12).

**Changed values (tCO₂e/MWh):** biomass direct 0.016 → **0.015**; lightoil total
0.344 → **0.342**; d_heat total 0.179 → **0.172**; electr total 0.226 → **0.209**
(Stromaufbringung Österreich 2022, 12.3% net imports, 6% grid losses). Unchanged:
gas 0.201/0.249, lightoil direct 0.271, biomass total 0.024. Coal: REP-0948 also has
no residential-Raumwärme coal row → the IPCC-2006 exception (0.340) stands.

**Impact.** Territorial basis: only the biomass direct factor changes → base-year
buildings CO₂ shifts ≈ −24 kt (5,598 → ≈5,574 kt); every CO₂ series must be
regenerated (post-hoc series at the R6 refresh; endogenous EMISS via the re-baked
workbook). Consumption basis moves more (electricity −17 g/kWh).

**Where.** `config/emission_factors.yaml`, `data/inputs.xlsx` sheet
`emission_factors` (rebuilt), `report/emissions.py` fallbacks, and the baseline_4
`emission_factor` rows **re-baked 2026-07-05** (e.g. biomass_rc 2025: 0.2157 → 0.2022
tCO₂/kWa). Committed run outputs/tables still show REP-0888-based numbers until the
R6 refresh.

---

## 11. Region prune of the STURM input CSVs (W5.1)

**Decision (2026-07-10, user — Mastrucci-feedback scope).** All foreign-region rows are
removed from the two sector input dirs (`input_csv_SSP_2023_{resid,comm}`): 200 files
pruned, ~807k lines deleted; `C-AUT`/`AUT` is the only region left. The additive
"keeps-WEU-runnable" property of the original build ends here; the pre-prune tree is
the parent of this change's commit (git history).

**Tool.** `inputs/austria_sturm/prune.py` (`python -m …austria_sturm.prune`,
idempotent, line-level byte-preserving; `verify_pruned` enforces the invariant).
Untouched by rule: 34 "global" files (no region column), root-level price/U-value
files (iteration-1 defaults, region-join filtered), and `ct_fuel_excluded_reg.csv`
(allowlisted: it has no AUT rows by design — absence *is* the Austrian setting — and
emptying it would change `read_csv` type inference under the F04/F05 joins).

**Why safe.** F01 loads every CSV in full but joins onto the `region_select`-filtered
case set (`fun_build_data_model`); `regions_aggr` from the unfiltered `geo_data` is
dead code. **Gate (passed 2026-07-10):** `report_MESSAGE` output byte-identical
pre/post prune for resid×SSP2, resid×SSP2_DIG_ACCELERATED, comm×SSP2
(`--region_select=C-AUT`, years 2025–2040).

**Consequences.** `build.append_region` returns `no-source` on pruned files (the baked
Austrian rows are the input set); the `C-WEU-AUT` fallback region is gone
(`test_sturm_run.py` fixture moved to `C-AUT`; docs/config comments updated).

---

## 12. Pathway-dependent renovation-rate ceiling (W5.2)

**Decision (2026-07-10, user — Mastrucci Q2).** The renovation-rate corridor becomes a
pathway dial. Mastrucci confirmed `ren_rate_en_min/max` bound STURM's *endogenous*
rate (F05 clips the discrete-choice rate to the corridor), so ambition is expressed
through the ceiling, not a prescribed rate.

**Values.** Default corridor (Reference, Bio-Bridge): unchanged —
`ren_rate_en_max_ssp2` = 1%/yr (2020/2025) → 1.5%/yr (2030+), min 0; consistent with
observed Austrian practice ~1%/yr (thesis §2 renovation-rate disambiguation).
Renewables Push: new `ren_rate_en_max_ssp2_AT_TARGET.csv` = **3%/yr from 2030**
(Austrian policy target; 2020/2025 keep the observed 1%). Minimum untouched (no
forced min≈max — untested upstream per Mastrucci).

**Mechanism.** `tools/build_renovation_variant.py` writes the ceiling file + manifest
columns `SSP2_RENAT`, `SSP2_DIG_{BASELINE,STAGNATING,ACCELERATED}_RENAT` (base-column
cells + `rate_ren_high` override); pathway dial `renovation_ambition: at_target`
(scenarios.yaml → inputs.xlsx, renewables_push) selects the suffix via
`loop.sturm_scenario_name`. `build_digitalization_variant.update_manifest` now
replaces its columns by exact name so composed variants survive a rebuild.

**Verification (2026-07-10, standalone STURM, C-AUT resid).** SSP2_DIG_BASELINE vs
_RENAT: 2025 identical (calibration pin); heat+DHW final energy −6.4% (2030) →
−14.4% (2040); gas −36%, oil −40%, electricity +3% heat / +27% DHW at 2040
(renovation is electrification-coupled), district heat unchanged (frozen until W5.6).
Effect onset exactly at the 2030 ceiling step.

---

## 13. Standalone fuel-switch activation + carbon-price passthrough (W5.3)

**Decision (2026-07-10, user — Mastrucci Q1 + the 2026-07-07 transmission-gap
diagnostic).** Two changes to the price/switch channels:

**(a) Per-fuel Austrian switch rates** (`tools/build_switch_rates.py`): the AUT rows
of `rate_switch_fuel_heat_ssp2.csv` replace the inert `fuel_heat="nsp"` default
(joins nothing → stream empty) with the FFPH-schema per-origin-fuel rows:
**gas 2%/yr, oil 1%/yr**, `bld_age_min=20`, 2020–2100. Grounding: STATcube household
fuel-consumption series (2013/14→2023/24; `table_2026-06-22_22-44-39.csv`) — gas
space-heat energy −4.6%/yr observed, of which renovation (≈1–1.5%/yr corridor) and
turnover explain part → ~2%/yr standalone replacement; oil series noisy (2021/22
stockpiling), so the conservative 1%/yr (= upstream FFPH default; "raus aus Öl" /
Kettner oil-2035 context). Other fuels: no rows (net in-flows; no out-switching).
Only the *rate* is exogenous — destinations come from the F05 discrete choice, so the
new stream is price-sensitive in its destination mix.

**Verification (standalone STURM, SSP2_DIG_BASELINE, C-AUT):** base year identical;
2040 gas −20.7%, oil −13.1%, electricity +20.2%, biomass/d_heat 0.0% — the switch
channel is non-zero (was exactly 0.0% in the W2.2 decomposition).

**(b) Carbon-price passthrough** (`Config.carbon_price_passthrough`, default true):
`loop._add_carbon_price` adds `tax_emission(y) × EF_direct(fuel) × 8.76` ($/kWa) to
the STURM price vector — the tax bites downstream of the final-level duals the loop
reads, so STURM's LCC never saw it (120-USD probe: prices identical to the last
digit). Direct factors only (territorial base): electricity/d_heat untouched.
Plus the GLB-node filter in `_extract_prices` (the stray near-zero lightoil row).
Unit-tested (120 USD → +211.3 $/kWa ≈ +6.7 $/GJ on gas); the tax120 probe re-run
needs a solver → W5.7 server batch.

---

## 14. Fuel-set restructuring: explicit heat pump + district heat as choice (W5.6)

**Decision (2026-07-10, user — Mastrucci Q3/Q4).** `tools/build_fuelset.py` (+ the
two R forks in `sturm_fork_changelog.md` §1–2).

**Explicit HP (`elec_hp`).** Upstream's implicit representation (electricity
`eff_heat` 1.00 legacy / 2.79–3.38 std-low = a HP by eneff class) is made explicit:
`elec_hp` carries the upstream COP values in std/low classes and **2.5 in legacy
classes** (existing air-source units in unrenovated buildings — assumption, no
in-repo source; Mastrucci: conventional HPs perform worse there); `electricity`
(resistive) flattened to eff 1.00 everywhere, excluded from new construction and no
longer a renovation target (X→electricity 1→0; staying allowed) — the
electrification target is `elec_hp`, which inherits the HP-priced upstream
electricity cost rows (8,982.7/8,586.3). Base-year stock share 18.57% electricity →
13.0% `elec_hp` / 5.57% resistive (Mikrozensus 2023/24 dwelling counts, 70/30). DHW
efficiency for `elec_hp` = 0.97 (upstream's electric-DHW value — upstream gave
HP-class homes non-HP DHW; kept, no fabricated DHW COP). Prices: `elec_hp` rows =
`electr` rows in `input_prices_R12.csv` (default) and duplicated by the loop.

**District heat as choice.** `ct_fuel_comb`/`ct_fuel_dhw` `mod_decision` 0→1; cost
rows: investment = the **gas** rows (substation ≈ boiler cost — documented
approximation, no in-repo source), intangibles 0 toward DH / 99999 re-fossilisation
gates from DH; transitions X→district_heat allowed. The 17.3% share file **stays**
(it alone creates base-year DH stock, F02:200-201); the exogenous new-build route is
retired via the F06 fork. Known limitation: no urban-only gate on the DH choice (the
ct tables carry no urt dimension).

**Verification (standalone STURM, SSP2_DIG_BASELINE, C-AUT).** Base year per fuel
preserved (electricity splits 0.391 HP + 0.340 resistive; combined lower than the
implicit 1.124 because 70% of the stock now correctly draws ÷COP — STURM levels are
non-authoritative, the linkage anchors levels to the Austrian reference). 2040 vs
pre-change: d_heat **1.14 → 1.99 GWa (endogenous growth — the double-freeze
signature is gone)**, gas −25%, oil −25%, elec_hp 0 → 0.69, resistive 1.50 → 0.13.
Sector scope: resid only (the comm input dir keeps the upstream fuel set; the
linkage runs resid).

## 15. Price-feedback under-relaxation (W5.8)

**Decision (2026-07-12, coupling-loop fix — no data or STURM-behavior change).**
The first r5 coupled batch (server runlogs 2026-07-10/12) exhausted the
20-iteration budget in **every** cell, settling into exact period-2..4 limit
cycles (L-inf 0.13–2.05 relative, tol 0.005) and finishing on the
oscillation-mean fallback. Mechanism: §13+§14 made STURM genuinely
price-responsive (active switch destinations, DH/HP in the F05 discrete choice)
while the loop fed the `PRICE_COMMODITY` duals back raw. LP duals are
piecewise-constant in the activity bounds — a small bound shift flips the
binding set and the duals jump — and the near-winner-take-all logit
(`lcc^-nu`) turns the jump into a large fuel-mix swing, which flips the bounds
back. Dominant component: `resid_heat_d_heat` 2040 swinging 1.63 ↔ 0.68 GWa.

**Fix:** the loop now under-relaxes the price vector fed to STURM
(`_blend_prices`): `p_fed = α·p_new + (1−α)·p_fed_prev`, `Config.price_damping`
default **0.5** (1.0 = the undamped pre-W5.8 behavior; blended *after* the §13
carbon-price adder so the damped signal includes the tax). Standard Gauss–Seidel
under-relaxation for soft-linked model iteration; α=0.5 lands the first blend on
the midpoint of a period-2 cycle. One-sided price rows keep their value (F05
NA-poisoning guard). Applies to both coupling modes (bounds + useful) — the
blend sits at the shared price extraction. Diagnostics: the loop logs the top-3
L-inf contributors per iteration and the damping α; `convergence_evidence.csv`
gains a `price_damping` column. Regression: synthetic period-2 closed-loop tests
(both modes) pin undamped-oscillates / damped-converges and the
oscillation-mean backstop, which stays as the worst-case floor.

**Consequence for results:** the 2026-07-10/12 r5 numbers are oscillation-mean
artifacts and are superseded by the damped re-run (W5.7 gate: one probe cell per
coupling mode, then the full batch).

## 16. Price-vector shape stabilization (W5.8b)

**Decision (2026-07-12, follow-up to §15 after the damped batch).** The damped
r5 batch (runlog `run_20260712T124933Z`) converged **13/20 cells** (RP + linear
4–5 iterations, useful mode 2, Reference baseline/stagnating 7–8) — but
Bio-Bridge ×3 (0.013–0.018), Reference-accelerated (0.049), exogenous-baseline
(0.046) and tax120 (0.32, re-diverged after a 0.008 near-miss at iteration 16)
still exhausted the budget, all with `heat_rc` as top changer and a
"Price blend: 1 rows … single-sided" warning every iteration.

**Cause:** `PRICE_COMMODITY` drops zero-dual rows (sparse GAMS storage) — the
r5 exports have no `d_heat` row at 2030. The flickering row escapes the §15
blend (one-sided keep = alternately raw and stale), leaving the DH price
channel effectively undamped.

**Fix:** `_fill_missing_years` in `_extract_prices` reindexes each commodity to
the union year grid; interior gaps interpolate linearly on the year axis (a
dual gap is a degeneracy artifact, not a zero consumer price), edge gaps take
the nearest value. The blend is then two-sided on every entry. Verified against
the synced r5 export (fills exactly `d_heat/2030`); unit tests cover
interpolation, edge fill, passthrough, and no-one-sided-blend. Also fixed in
the same batch: the §3c notebook comparison read `final_energy_by_fuel.csv`
with a `fuel` column that is actually `commodity` (KeyError after the tax120
run completed).

**Consequence:** re-run the still-open cells (BB column, Reference-accelerated,
exogenous baseline, tax120); `price_damping=0.3` stays the per-cell fallback.

## 17. Headline coupling mode → useful (Mastrucci soft coupling)

**Decision (2026-07-14, coupling-design change — supersedes the bounds-mode
headline).** `linkage_mode` flips `bounds → useful` in the `config` sheet: the
headline coupling is now the Mastrucci-style soft coupling (STURM per-fuel final
energy → useful via the techs' base-year `input` coefficients → `rc_therm`
`demand`; fuel mix optimised by MESSAGE). Bounds mode remains implemented as the
hard-linkage **sensitivity** — run-ids now suffix `__mode-bounds`
(`pipeline._HEADLINE_LINKAGE_MODE`), and the r5 bounds canon is archived
un-renamed as `results/runs_r5_bounds` (sidecars record `linkage_mode: bounds`).

**Diagnosis that shaped the design (the "6.6 Mt anomaly", 2026-07-04 roadmap):**
the archived `__mode-useful` Reference probe showed 2025 buildings CO₂ ≈
**8,888 kt vs the 5,574 kt canon** (gas +78 %, biomass −64 %, electr −28 % vs
the Statistik Austria reference; `base_year_check.csv` failing) and 6,616 kt @
2040. Root cause: `apply_useful_demand` writes only projection-year demand — the
baseline workbook calibrates the per-fuel end-use bounds **only at 2020**, so at
the 2025 base year MESSAGE free-picks a cheapest (fossil-heavy) mix that the
`growth_activity_*` dynamics then propagate forward. The anomaly was therefore
dominated by base-year de-calibration, with the missing fossil-exit caps second.

**Mechanism (new, W6):** a once-per-cell static anchor
(`linkage.targets.useful_anchor_targets` → `pathways.constrain_targets` →
`linkage.bounds.apply_useful_anchor`) written before the loop:
base-year per-fuel **equality pin** at the reference-anchored levels (same
`_anchor_level`/HP-split arithmetic as the bounds path) + the pathway's
**one-sided** projection bounds — fossil techs cap-only on the fuel-specific
logistic exit ramp (same `_fossil_fraction`/`_fossil_exit_lead` machinery, so
`__shape-linear` still works), `biomass_rc` cap-only (`low`) or floor-only
(`high`) at base level (`pathways.useful_bound_sides`). Hygiene reset clears
inherited `bound_activity_*`/relation rows on the fuel techs at `year_act ≥
base_year` (batch cells share one ixmp scenario). The old useful-mode
fossil-exit refusal is removed; a new guard refuses
`digitalization_mode="exogenous"` in useful mode (the Macko multiplier only
exists on the bounds path). `electrification_intensity` is a structural no-op
in useful mode (fuel mix free by construction; logged).

**Consequences for results:** the r5 bounds numbers (Ref 1,890.7 / RP 154.6 /
BB 332.3 / tax 1,692.8 kt @2040) move to sensitivity status; the r6 useful
batch becomes the headline canon (fresh `scenario_name = baseline-2025-r6`).
Interpretation changes: the RQ2 digitalization spread now transmits through the
demand level with an endogenous fuel-mix response (BB's "spread 0 by
construction" no longer holds), and Reference-useful 2040 CO₂ is expected above
the bounds canon (soft coupling transmits no STURM price-driven fuel switching)
— a coupling-family contrast to report, not a bug. Price damping (§15/§16) is
unchanged and applies identically in useful mode.

## 18. Data-edition refresh: REP-0989 emission factors + REP-0995 targets (2026-08-25)

**Emission factors** (`inputs.xlsx` sheet `emission_factors`): basis updated
from UBA REP-0948 (Datenstand 2024) to **UBA REP-0989** (*Harmonisierte
österreichische direkte und vorgelagerte THG-Emissionsfaktoren*, Datenstand
2025, Wien 2025; Tab. 1 Raumwärme p. 9, Tab. 4 Strom p. 12; PDF at
`Thesis/docs/literature/to-read/rep0989.pdf`). Changed values (tCO₂e/MWh):
`ef_total` electr 0.209 → **0.152** (cleaner 2023 generation mix + import
structure), `ef_total` d_heat 0.172 → **0.166**. All other values are
identical in REP-0989 (gas 0.201/0.249, lightoil 0.271/0.342, biomass
0.015/0.024; coal stays the IPCC-2006 exception — REP-0989 has no residential
coal row). **The territorial (direct) basis — the RQ1 headline — is
unchanged**; only the consumption-basis sensitivity series shifts.

**2040 targets** (`inputs.xlsx` sheet `targets`): basis updated from UBA
REP-0951 (NEKP-Szenarien 2024) to **UBA REP-0995** (*Energie- und
Treibhausgas-Szenarien 2025*, WEM 2025/WAM 2025; Tabelle 7, Gebäude row; PDF
at `Thesis/docs/literature/to-read/rep0995.pdf`). `target_2040_wem_kt`
5,100 → **3,400**; `target_2040_wam_kt` **1,300 unchanged**. Narrative
effect: the Reference pathway now lands *below* the WEM (existing-measures)
comparator while remaining clearly short of the WAM target.

Provenance sheet + notes sheet updated accordingly (the notes sheet still
cited REP-0888 — two editions stale — now fixed). Regression pins updated:
`tests/test_emissions.py::test_emission_factors_pinned_rep0989_values`,
`tests/test_workbook_schema.py::test_targets_loaders`.

**tax120 provenance reconciliation:** §16 closed with tax120 on the re-run
list; the r5 final batch (`run_20260714T095612Z`) resolved it — converged in
9 iterations at α=0.5 (`results/tables/convergence_evidence.csv`). The cells
still non-converged after the §3i α=0.3/budget-40 protocol are
bio_bridge-accelerated/-stagnating and reference-accelerated (residual L-∞
0.011–0.017 vs tol 0.005) — reported as the oscillation band, not re-run
further in bounds mode (r5 is the archived sensitivity).

## 19. Vocabulary alignment: uncovered rc_therm carriers (2026-08-25)

**Decision (Christian):** the two models should carry the same fuels/technologies
at the linkage. Audit: 7 carriers map 1:1 (`FUEL_TO_TECH`, incl. the W5.6
`elec_hp`/DH additions); 6 baseline `rc_therm` techs have no STURM carrier and
were previously left free — `solar_rc` (solar thermal, ~0.24 GWa 2020
calibration bound), `foil_rc` (~0.0002), `eth_rc` (0.007), `meth_rc` (0),
`h2_rc`/`h2_fc_RC` (no base bound).

**Change (useful mode only):** the §17 static anchor now holds every uncovered
carrier at its **observed base-year level** — the baseline's latest calibration
bound at or before the base year; zero where none exists — written as flat
one-sided caps over the horizon (`common.vocab.UNCOVERED_RC_TECHS`;
`useful_bound_sides` adds them to `cap_only` for every pathway). Rationale: with
the fuel mix free, the optimisation could route thermal demand through carriers
STURM cannot see; the caps make "re-allocation only among STURM-represented
carriers" an explicit property. The solar level is the baseline's own (the
Statistik Austria `other` row bundles solar with ambient heat and cannot be
attributed cheaply — documented limitation); hydrogen is capped at 0 through
2040 (no buildings hydrogen in REP-0995 WEM/WAM 2025). The **coal** gap needs no
code change in useful mode — the anchor pins `coal_rc` from the reference
(0.0051 GWa), closing the old base-year FAIL row. The bounds path (r5, archived
sensitivity) is untouched; a Reference cell's uncovered caps do **not** trigger
the broad fuel-tech dynamics strip (baseline fuel-mix inertia kept).

## 20. Provenance audit — REP-0995 drift fixes + assumption register (2026-08-27)

Full-repo provenance audit (register: Thesis
`docs/notes/2026-08-27_data_provenance_audit.md`). No model value changed;
documentation and post-processing only.

**Stale-drift fixes** (the 2026-08-25 REP-0989/0995 adoption had only reached
the workbook and §18):

- `viz/plots.R`: `NEKP_WEM_KT` **5,100 → 3,400** (REP-0995 WEM 2025) — the R
  figures had contradicted `viz/summary_tables.py`/`viz/build_deck.py`, which
  read the workbook. Header comment re-based to REP-0995 Tabelle 7; the two
  hline labels now read "~3,400 kt (UBA 2025, WEM)" / "(UBA 2025, WAM)".
- Docstrings re-based REP-0948→REP-0989 and REP-0951→REP-0995:
  `src/messageix/emissions.py`, `src/common/validation/gap_to_target.py`,
  `viz/summary_tables.py`; docs likewise (`architecture.md`, `glossary.md`,
  `pipeline.md`, `docs/data/provenance.md` — the latter also corrected the
  stale example "electricity 0.209 total" → 0.152).
- `run.ipynb` preflight cell: labels "= REP-0948" → REP-0989 (checked values
  unchanged — 0.015 biomass direct, ~0.2022 biomass_rc bake).

**Workbook `notes` sheet**: the five rows still pointing at files retired in
the 2026-07-13 refactor (`config/*.yaml`, `austria_buildings_reference.xlsx`,
`src/Macko-analysis/…`) now state the current provenance (workbook-native,
origin tools in git history, raw exports in `data/austria_raw/`).

**Workbook `provenance` sheet**: +10 rows making previously invisible
assumptions explicit (no value changes): STURM renovation discount rates
(0.07/0.10 own, 0.35/0.40 rent — UNSOURCED, ask Mastrucci), LCC heterogeneity
ν=8 (UNSOURCED), the WEU-inherited defaults block (efficiencies, costs,
lifetimes, Weibull, tenure, intangibles), the DH/resistive investment-cost
approximations, the logistic mid-window inflection (0.5), the 2030 supply-dial
anchor year, the 120 USD/tCO₂ probe, the §3i recovery policy (α=0.3/40), the
STURM fan-energy divisor (25) and cement content (0.15). Also filled the two
empty `note` cells (`emission_factor_basis`, `reference_final_energy_export`).

**Verified non-issues**: the suspected DHW unit inconsistency F02 vs F06 is a
false alarm (residential `/1e3` GJ→TJ and commercial `/1e6*3.6` kWh→TJ lines
are identical in both files); R's `u_EJ_GWa = 31.71` is a rounded duplicate of
Python's exact 31,536 TJ/GWa (0.0006 % apart, upstream convention — left
as-is). `src/messageix/pathways.py`'s REP-0951 mentions cite that report's WAM
*narrative* as the historical source of the gas-residual reasoning and stay.

## 21. Useful mode: min-liquids relation strip (r6 §2b infeasibility, 2026-08-27)

The first r6 server attempt failed the §2b probe gate: Renewables Push ×
baseline was **presolve-infeasible** at
`COMMODITY_BALANCE_GT(Austria,rc_therm,useful,2035)`. Offline diagnosis (full
local reproduction of the scenario build — no solver needed):

**Cause.** The received baseline carries the relation **`min-liquids_res-com`**
(all years 1990–2110): `15·(loil_rc + eth_rc + meth_rc) − 1·(other rc techs)
≥ 0`, i.e. liquids ≥ 1/16 of total rc heating activity — a downscaling inertia
artifact, not an Austrian policy statement. Under a fossil-exit pathway the
Kettner oil ban caps `loil_rc` at 0 by 2035 and the §19 vocabulary caps hold
`eth_rc ≤ 0.0074` / `meth_rc = 0`, so the relation caps *total* rc supply at
≈0.12 GWa against the imposed useful demand of 5.79 GWa (RENAT) → infeasible,
exactly as CPLEX presolve reported. Bio-Bridge would fail identically.

**r5 implication (documented limitation of the bounds canon).** The same
relation was satisfied in every r5 cell by **phantom `eth_rc`/`meth_rc`
activity** — provable from the harvested CSVs plus the constraint algebra:
RP/BB cells carried ≥0.48–0.51 GWa and Reference ≥0.21–0.30 GWa of invisible
liquids heat at 2035/2040 (those techs are excluded from `activity_rc.csv`, so
this never appeared in any table). The old "assumed ~0 activity (verify)" note
on the excluded techs is hereby verified: **not** ~0. No direct CO₂ impact
(eth/meth carry no emission factor), but ~3–7 % of rc_therm energy accounting.
This is the exact phantom-carrier problem the vocabulary alignment (§19)
exists to prevent — the caps worked and exposed it.

**Change** (`src/linkage/bounds.py: _strip_min_liquids_floor`, called from
`apply_useful_anchor`; name in `common/vocab.py: MIN_LIQUIDS_RELATION`): in
every useful-mode cell the anchor removes the relation's `relation_lower` rows
at `year_rel > base_year` — projection floor disabled, base-year row kept (the
calibration pin satisfies it), accounting coefficients left in place. Applied
to **all** useful cells, Reference included (an artifact liquids floor in one
pathway but not another would distort the RQ1 comparison; Reference's oil
inertia is already carried by the kept baseline growth dynamics — without the
strip, Reference-useful would be *forced* to keep ≥1/16 liquids through 2040,
≈0.35+ GWa forced oil ≈ ~1,000 kt CO₂, material vs the WAM 1,300 kt target).
Bounds mode (archived r5 sensitivity) deliberately untouched — frozen
behaviour, phantom documented above instead.

**Verification.** Unit test
(`tests/test_useful_mode.py::test_apply_useful_anchor_strips_min_liquids_floor`);
suite 109 passed. Full local rebuild of the RP scenario (fresh scratch
platform, pathway + anchor + RENAT demand): relation floor absent 2030+,
present ≤2025; per-year presolve arithmetic now leaves `heat_rc`/`elec_rc`/
`hp_el_rc` unbounded against demand 6.39/5.79/5.39 GWa (r5 demonstrated those
three delivering 6.6 GWa under the same supply system). Server re-probe (§2 +
§2b) scheduled 2026-08-28 before the batch.

## 22. r7: review-driven rework — demand closure, carbon price, uniform rule (2026-09-01)

The 2026-08-28 independent reviews (Thesis `docs/notes/reviews/`) and the author's
Part-B decisions (2026-08-29/09-01, bench artifact + verification guide) produced
one bundled rework. Scenario name bumped to **baseline-2025-r7**. No r7 batch has
run yet — staged for the next server session.

**a. rc_therm demand reconciliation (B1).** All 20 `rc_therm` rows of
`data/MESSAGEix-AT_baseline_4.xlsx!demand` scaled by **×1.148350**, anchored so
demand(2025) = the base-year pin sum 8.383296 GWa (7 fuel pins 8.136066 from
reference-final ÷ input coefficients + uncovered carriers 0.247230). Key values:
2020 7.4100→8.5093, 2025 7.3003→**8.3833**, 2030 7.6987→8.8408, 2035
7.7553→8.9058, 2040 7.6993→8.8415, 2050 8.4775→9.7351. This closes review
blocker A1 (the +14.7% base-year over-supply whose release inflated the
2025→2030 decline by ~30–40%): supply == demand at the pin, verified to
−0.0000% on a fresh local import. Mirrors the §9 `rc_spec` reconciliation.
External cross-check pending: the 2026-09-01 STATcube download
(`Thesis/data/raw/Nutzenergieanalyse_260901.xlsx`) turned out to be the
**final-energy** ("Consumption") variant — it reproduces the reference sheet
per fuel to 3 decimals (residential space+water heating 7.801 GWa, res+com
9.682) but the **"Useful energy"** Values-variant of the same cube still needs
pulling to compare Austria's official useful energy against the model-implied
8.38 (the difference, if any, is the MESSAGE-coefficient approximation and goes
in the limitations).

**b. Legislated carbon price + ladder (B2).** New workbook sheet
`carbon_price_paths` [id, year, usd_per_t, source]; the Reference row now
carries `carbon_price_path = nehg_ets2` (new `pathways` column). The path ships
with 2025 = 55 (NEHG fixed price for 2025; **entered EUR-as-USD — confirm the
currency treatment**) and **2030/2035/2040 deliberately blank**: the loader and
the `run.ipynb` preflight fail loudly until they are filled from the UBA
REP-0995 scenario assumptions (Christian, with citation). Machinery:
`Pathway.carbon_price_path`, `workbook.carbon_price_path()`,
`_resolve_carbon_prices` (step-wise carry-forward; flat+path together raises).
`run.ipynb` §3c is now a **flat-price ladder** (0/40/55/80/120 USD, five cells,
tax0 = the pre-r7 zero-price Reference kept as the ladder origin) to locate the
gas→HP switching threshold.

**c. Uniform dynamic-constraint rule (B3).** `apply_useful_anchor` now applies
one strip rule in every pathway: **up-side** dynamics
(growth/initial_activity_up) removed on all fuel techs + all frame techs over
projection years; **lo-side** decline floors kept everywhere except on
`floor_strip` techs (`pathways.floor_strip_techs` = the fossil-exit set, whose
caps decline to zero below any floor). The pre-r7 asymmetry — Reference under
full baseline inertia, capped pathways under none (review A3/7e: pathways were
not ceteris paribus) — is retired. Verified locally: under RP, biomass/elec/
heat/hp keep their decline floors, gas/loil/coal lose theirs, no up-side rows
remain. Expected result changes: RP 2040 becomes a floor-paced residual
(~155 kt, biomass at −5%/yr) instead of 0.0-by-construction; Reference gas
growth is no longer inertia-limited but is countered by the carbon price.

**d. Per-year input coefficients (B7).** `sturm_to_useful_demand` converts each
(fuel, year) with the technology's coefficient at that year instead of freezing
the anchor-year value. Residual limitation, documented: the received baseline
itself keeps `hp_el_rc` at 0.40 (COP 2.5) for every year_act, so the heat-pump
conversion only improves if that row set is re-baked (a possible follow-up
decision — e.g. STURM's own stock-average COP path — NOT taken here).

**e. Endogenous Wilson band (B8) + no-DIG counterfactual (B6).**
`Pathway.demand_modifier` scales the imposed useful demand by `1 + m·ramp`
(linear 2025→2050, `loop._wilson_factor`); `run.ipynb` §3w solves four
Reference cells (m = −0.22/−0.05/+0.03/+0.09) and
`viz/digitalization_band.py` now prefers those solved cells over the ex-post
multiplication (kept only as a labelled fallback). §3n adds the
`pathway-reference__digi-none` cell on the plain SSP2 operating-hours column
(digitalization id "none" → `sturm_scenario_name` returns "SSP2"), so RQ2 can
report digitalization-vs-none.

**f. Validation rework (B5) + both-bases reporting (B4).** New
`inventory_check.csv` per cell (`common/validation/inventory.py`): modelled
base-year buildings CO₂ vs the UBA Gebäude inventory anchor (new `targets`
rows: 7,400 kt @2022, REP-0951 Tabelle 3 — REP-0995 update optional), reported
with vintage/source context. The circular `base_year_check` is relabelled
**pin integrity** everywhere (pipeline docstring, plots.R figure title) and no
longer claimed as validation. `viz/summary_tables.py` additionally writes
`buildings_co2_by_year_consumption.csv` + `rq2_spread_consumption.csv`.

**g. Staging.** run.ipynb: r7 asserts, preflight checks (demand bake marker,
carbon-path completeness), §3c/§3w/§3n cells all §3i-registered (24 solves,
~45–60 min); diagnostics.ipynb: §4x degeneracy probe (RP baseline re-solved
with dual simplex under `renewables_push_lpprobe`; B10). Suite: 117 passed.
Pre-bake workbook copies in the session scratchpad; originals recoverable from
git (`fde2fae`).

### §22a addendum (2026-09-01, evening): the B1 external check closes as "not available"

The planned external validation of the reconciled `rc_therm` useful demand — a
STATcube pull of the Nutzenergieanalyse's *useful-energy* values — is not
possible: the cube's field list offers only the two "Consumption in TJ" facts
(final energy by useful-energy category; screenshot evidence 2026-09-01), and
*Energieeinsatz der Haushalte* is also a final-energy survey. Consequence for
the thesis: **useful energy is model-defined** — final energy (validated
exactly against STATcube, §22a confirms per-fuel to 3 decimals) divided by the
documented MESSAGE input coefficients — which is the standard convention and is
stated as a limitation rather than left as a pending check. The §22 demand
reconciliation stands unchanged; the only remaining pre-run gate is the
carbon-price path fill.

## 23. Post-r7 external-review adoption (2026-09-04) — results-invariant

An external release-engineering review (evaluated in
`Thesis/docs/notes/2026-09-03_simplification_review.md`, triage section) led to
six adoptions. **None changes any r7 number**: the removed dial was inert in
useful mode, the new guards reject states the r7 batch never produced, and the
sidecar/status additions are purely additive. The r7 tag
(`r7-results-2026-09-01`, `7900623`) remains the results-producing state.

**a. Currency sign-off (freeze gate #1) recorded in the workbook.** The
`carbon_price_paths` source strings now carry the decision: EUR values (NEHG
55 €/t 2025, REP-1042 p. 245; effort-sharing WEM 100 €/t 2030–2040, REP-0995
Tabelle 1) entered 1:1 as USD — a documented ≤10 % approximation that is
results-invariant because the model's response is a step with threshold
< 40 USD/t (r7 ladder).

**b. `electrification_intensity` removed.** The dial was dead code on the
headline path (useful mode imposes demand; the dial only relaxed bounds-mode
projections). Removed from `common.scenarios.Pathway`,
`messageix.pathways` (`_baseline_electrification`, `_set_electrification`,
`_has_activity_dials` clause), the `loop` no-op log, the workbook (`pathways`
column, `pathway_constants` row; provenance row `electrification_intensity_retired`
records the retirement), tests and notebook prose. Ch. 3's pathway table no
longer lists it.

**c. Convergence contract.** `convergence.relative_changes` now aligns the two
boundary vectors over the **union** of their indices (an entry appearing or
disappearing between iterations scores as a real change; the old inner join
silently dropped exactly those) and raises on duplicate index labels or
non-finite values. `loop.run` returns `(scenario, ConvergenceStatus)` —
converged flag, iteration count, final L∞, oscillation-correction flag.

**d. Sidecar manifest.** `*.meta.json` gains `convergence` (the status above),
`git` (commit + dirty flag) and `input_hashes` (sha256 prefixes of
`inputs.xlsx` / `baseline_4.xlsx`) — a result folder authenticates itself
without the runlog.

**e. Make-loud fallbacks.** `targets._input_coef`: a tech with input rows but
none operating in the requested year now raises instead of averaging across
all vintages. `targets.sturm_to_useful_demand`: a target year missing from the
STURM output now raises instead of flat-filling with the anchor value
(post-horizon `extra_years` flat-fill is unchanged and deliberate). Neither
path is exercised by the r7 baseline/STURM output.

**f. Reference regression test.** `test_reference_apply_touches_only_documented_params`
pins the mutation contract: the workbook Reference may add only `tax_emission`,
and may remove only carbon-policy rows and dial-owned supply rows
(fossil-power `bound_activity_up` with `year_act ≥ 2030`, renewable
relations); calibration rows and all unrelated baseline parameters pass
through untouched. Plus union/guard tests in `test_convergence.py` and the two
make-loud tests. Suite: **122 passed**.

License: decision recorded as "keep restricted for now" (no LICENSE change);
revisit at publication. Structural refactors from the same review (bounds-mode
quarantine, hygiene layer, `loop.run` split, Ruff/mypy pass) stay on the
post-submission list.

## 24. Upstream audit — documentation gaps closed (2026-09-05, docs only)

A three-way comparison against the public reference copies
(`message-ix-buildings` @34bac3c parent / @6a9cb8b, and
`message_ix_models/model/buildings` as the Python-coupling reference; full
report: `Thesis/docs/notes/2026-09-05_upstream_audit.md`) confirmed that both
FORK-marked R edits (§14) are the only R-source changes and found the
following **data changes that were live but undocumented** — recorded here;
no data, code, or workbook edits (the r7 tag stands):

- **Urban/rural differentiation collapsed** in the Austrian bake:
  `bld_share_fuel_heat_resid.csv` and `bld_shr_district_heat_resid.csv` carry
  identical `urb`/`rur` values (upstream WEU differentiated: DH 0.130 urb /
  0 rur; biomass 0 urb / 0.229 rur), and the rural DH share moved 0 → 0.1735.
  A behavioural simplification of the fork, now stated as a limitation
  change-spec for the thesis.
- Resistive `electricity` heating efficiency flattened 2.65–3.53 → 1.00 in
  `eff_heat_ssp2.csv` (the implicit-HP COPs moved to the explicit `elec_hp`
  carrier) — the recalibration half of the W5.6 fuelset split.
- `eff_hotwater_resid.csv`: `elec_hp` DHW efficiency 0.97 (upstream's
  electric-DHW value, reused).
- `ct_fuel_comb.csv`/`ct_fuel_dhw.csv`: `district_heat` `mod_decision` 0 → 1
  (the data half of the F06 FORK edit).
- `ct_fuel_excluded_new.csv`: resistive excluded from `s51_std`/`s52_low`
  new build.
- `input_prices_R12.csv`: +168 `elec_hp` rows = copy of `electr` (the only
  root-level price-file edit).
- `input_list_resid_SSP_2023.csv`: the four `*_RENAT` combination columns
  were never enumerated anywhere (7 → 14 columns total).
- The **comm** tree also carries the Austrian population override
  (`R61_pop_ssp2_2026-01-29.csv`) — §14's "comm keeps the upstream fuel set"
  is correct but incomplete.
- Provenance sheet row 6 path typo: `cost_int_ren.csv` should read
  `cost_int_ren_heat.csv` (fix at next legitimate workbook edit, not now).
- `baseline_4_changelog.md` is stale: it predates the §22 rc_therm ×1.148350
  reconciliation and the §7 emission-factor rows (both tracked in the
  workbook provenance sheet and this changelog; the per-file baseline
  changelog was never regenerated — regenerate post-submission or leave with
  this pointer).

**Upstream-drift watch** (behaviour-neutral today): fix `6a9cb8b`
(`select(-year)` in F06) not adopted — verified neutral while demolition
inputs carry no `year` column; `run_sturm_headless.R` filters
`grepl("_v_no_heat")` (broader than upstream's exact two-commodity filter)
and defaults to a 2020–2030 horizon (the driver always passes `--years`).

Verification-side outcomes recorded in the Thesis note: Kettner ban years
confirmed from the PDF (scenario assumption, not legislation), the
Wilson/Zakeri band PDF was in hand all along under the filename
`Co2_electricity_paper_wilson.pdf`, and the reference Python coupling already
iterates to convergence (the fork's genuine deltas: L-infinity boundary
criterion, damping, carbon-price passthrough, Wilson modifier, status
contract).

## 25. Audit reconciliation — fixes and golden fixtures (2026-09-05)

Reconciling the two independent upstream audits (`Thesis/docs/notes/
2026-09-05_upstream_audit.md` + `docs/upstream_reference_audit.md`, external).
The audits agree on every overlapping finding. Actions taken (all
results-invariant; r7 tag untouched):

**a. Golden regression fixtures** (`tests/golden/` + `test_golden_sturm.py`,
3 slow tests, ~30 s): matched resid SSP2 2020–2040 runs for reference
code×data, fork code×reference data, fork code×fork data — same headless
harness for all three, byte-stable across repeated runs. Reproduces the
external audit's matched-run experiment exactly: code effect on reference
data max 0.042 GWa; fork vs reference max 3.437 GWa (2040 resid gas
2.174→0.380) — **the Austrian input changes dominate; the R-code changes are
small**. Reference-based tests skip when the upstream checkout is absent.

**b. Join-warning verdict**: with `options(warn=1)`, the fork run emits 40
warnings vs upstream's 36; the delta is exactly one callsite ×4 model years —
`left_join(., ms_sw_i)`, the standalone fuel-switching join that is dead
upstream (the `nsp` placeholder never matches) and live in the fork (§14).
The many-to-many fan-out (one origin stock row → several target fuels) is the
intended relationship; report keys verified unique (asserted in the golden
test). Benign.

**c. `baseline_4_changelog.md` regenerated** as a full parameter-level diff
against the git-recovered handover workbook: 8 sheets differ (firstmodelyear,
demand 13+20 rows, +80 emission-factor rows on the four combusting rc techs,
GHG sets, +152/+32 historical rows, sp_el history ×0.4758); **92 of 100
sheets byte-equal to the handover** — no techno-economic parameter of the
received scenario was altered.

**d. Small fixes**: `loop.run` return annotation corrected to
`tuple[Scenario, ConvergenceStatus]` (missed in §23); stale bounds-mode
framing in `docs/code_walkthrough.md` corrected to the useful-mode headline;
`--sector=comm` declared an auxiliary interface (runner header +
`src/sturm/README.md`) — its defaults do not reproduce upstream's commercial
runner and the linkage never invokes it.

**Deferred** (triage in the Thesis reconciliation note): server-env version
capture + optional sidecar refresh + optional tax0×digi cell at the next
server visit; non-convergence fail-by-default, transactional outputs,
viz-collector guards, scenario-ownership cleanup, input-domain validation,
Ruff/mypy → post-submission. **Rejected**: full matrix re-run as a validity
precondition (tag + byte-identical verification + §23 invariance checks carry
provenance; the local-env GAMS/Java mismatch is the documented laptop
constraint, results were produced on the institute server).

## 26. Digitalization as an efficiency effect — `digitalization_mode = efficiency` (r8, 2026-09-08)

**What changed.** The headline digitalization channel no longer reduces STURM's
heating *operating hours*. Macko (2025) defines her savings as *final-energy*
reductions at constant useful energy (thesis pp. 38, 44: "useful energy is
assumed to be constant"); reducing hours instead reduces the heating *service*
— a different physical mechanism (thesis change specification CH-14; decision
Christian 2026-09-08: correct the transformation and rerun). In the new mode
(`linkage/digital.py`):

- STURM runs the plain `SSP2` operating hours for **every** adoption level
  (`SSP2_RENAT` for Renewables Push); the useful demand handed to MESSAGEix is
  therefore adoption-invariant. The `SSP2_DIG_*` hours variants stay in the CSV
  tree for the archived `sturm` mode (§17, r7).
- The Macko reduction `r(y)` — `Smart_space_heating × Residential`
  (`macko_reduction` sheet), re-based to 0 at the base year 2025 and held flat
  after 2040, i.e. the same series the retired hours bake used (provenance row
  `digitalization_operating_hours`) — scales the `input` coefficient of the seven
  STURM-covered `rc_therm` technologies (`gas_rc`, `biomass_rc`, `coal_rc`,
  `heat_rc`, `loil_rc`, `elec_rc`, `hp_el_rc`) by `1 − r(y)` in every projection
  year, all vintages alike. Applied to the combined residential+commercial
  commodity — a documented simplification (the residential series is the only
  executed channel, as in r7).
- The baked `CO2` `emission_factor` rows of the combusting techs (§7:
  `ef_direct × input × 8.76` per unit activity) are scaled by the same factor, so
  the endogenous emissions and the carbon tax stay consistent with the post-hoc
  `ACT × input × EF` accounting.
- The STURM→useful conversion uses the coefficients **snapshotted before** the
  scaling (`sturm_to_useful_demand(..., coefficients=...)`), so the imposed
  demand is the calibrated service demand, not one inflated by the efficiency
  gain.
- Run-folder convention: `efficiency` is the headline (plain matrix ids);
  `sturm` and `exogenous` get a `__digi-<mode>` suffix. `linkage_mode=bounds`
  refuses the efficiency channel (frozen r5 sensitivity).

**Workbook.** `config`: `digitalization_mode` sturm → **efficiency**;
`scenario_name` baseline-2025-r7 → **baseline-2025-r8**. `provenance`: row
`digitalization_efficiency_channel` (runtime, not a bake).

**Expected result changes (to be verified on the server):** the demand vector
is identical across adoption levels; the territorial spread is no longer
structurally zero — fossil emissions fall with the efficiency factor even on
the decline floors (activity floors × smaller input coefficient); the
consumption-basis effect remains. The r7 result set (hours channel) is archived
as `results/runs_r7_sturm` on the laptop; the `final-results` tag stays on the
r7 state until r8 is harvested.

**Tests.** `tests/test_digital_efficiency.py` (factors re-based/flat/none;
input + CO2-factor scaled alike; identity writes nothing; conversion invariant
under the snapshot; scenario-name and run-id conventions; bounds refusal;
real-workbook monotonicity). Existing suite adjusted for the new headline mode.

**Solved and harvested 2026-09-08 (r8 = the final result set).** Server run
`run_20260908T183848Z` (18:38–19:32 UTC), 24/24 solves converged at log iteration
index 2, all 22 cells fresh (`baseline-2025-r8`; `inputs.xlsx` sha256 prefix
`4c9ddb53c689aea4`). Territorial 2040 (kt, baseline adoption): Reference **905.2**
(stagnating 921.5, accelerated 890.7, no-DIG 947.7), Renewables Push **54.5**
(55.5/53.6), Bio-Bridge **317.4** (323.1/312.3), Reference-tax0 **7,122.9**; ladder
≥ 40 USD identical to the Reference. Mechanism as expected: gas/biomass stay on
their activity floors (0.4401/0.2954 GWa) and floor-bound emissions scale with
the efficiency factor (947.7 × 0.9552 = 905.2), so the territorial adoption
spread is ≈ 3.4 % of the residual in every pathway. One expectation did **not**
hold: useful demand is not identical across adoption levels (2040: 7.156 /
7.141 / 7.126 / 7.128 GWa) — the scaled `heat_rc` coefficient changes the
district-heat dual (293.8 → 250.3 → 223.8 USD) and STURM's heating choice
responds; ≤ 0.4 %, price-feedback residue only. Consumption basis: Reference
no-DIG → accelerated 358.0 kt (3.57 %). The once-through and dual-simplex
diagnostics (§3f/§4x) were not rerun and remain r7. Reference tables replaced
(`tests/reference_tables/`, riders documented as r7); tags
`r8-results-2026-09-08` and `final-results` on the harvest commit. Harvest
record: `Thesis/docs/notes/2026-09-08_r8_harvest.md`.

## 27. r8-only prune — archived coupling modes and their data removed (2026-09-13)

**Decision (Christian, 2026-09-13):** the published code contains exactly what produces
the final r8 result set. Removed: the r5 hard-linkage mode (`linkage_mode="bounds"`:
`apply_activity_bounds`, `sturm_to_activity_targets`, `cap_only_techs`, the loop's
bounds branches and oscillation mean, the `1.0` coefficient fallbacks), the r7
operating-hours channel and the exogenous multiplier (`digitalization_mode="sturm"` /
`"exogenous"`: `scale_by_macko`, the `SSP2_DIG_*` manifest columns and
`heat_operation_hours_dig_*.csv`), the `__mode-`/`__digi-` run-id suffixes, the
config keys `linkage_mode`, `digitalization_mode`, `bound_lower` (workbook `config`
sheet: three rows deleted; `inputs.xlsx` sha256 prefix `4c9ddb53c689aea4` →
`408903056be97de8`), the commercial STURM tree (never run), the 74 residential CSVs no
`SSP2`/`SSP2_RENAT` manifest column references (SSP1/3/4/5, LED, ELEC, FUELSWT, BLDC,
FLRD, REN_H variants and other unreferenced files; the manifest now carries only
`SSP2` and `SSP2_RENAT`), `input_prices.csv` (never read), `diagnostics.ipynb` §2b/§3h/§3e,
`tests/test_bounds.py`, and `tests/reference_tables/` (superseded by the tracked
`results/tables/`). The archived result trees (`runs_r7_sturm`, `runs_r5_bounds`,
`runs_stale_synced_2026-09-08`, old logs, scratch) were moved out of the repository to
`~/workspace/archive/sturm-messageix-results-2026-09-13/`. The STURM R sources are
untouched (fork policy).

**Results unaffected — verified:** STURM reruns on the pruned tree reproduce the r8
snapshots byte for byte (`SSP2` with the Reference cell's fed prices, `SSP2_RENAT`
with the Renewables Push cell's); the five `viz/` generators reproduce every committed
`results/tables/*.csv` byte for byte from `results/runs/`; `pytest -m "not slow"`:
122 passed. The efficiency channel is now unconditional in `loop.run`; `Config` has
no mode fields. Results are tracked from this change on (`results/runs`, `tables`,
`figures`, the r8 log); `mode_contrast_reference.csv` and the two `rider_*.csv` stay as
archived data (`results/tables/README.md`). Version 2.0.0 (config keys removed).
Starting state tagged `pre-prune-2026-09-13`.

## 28. Reproduction of r8 on the pruned code — server rerun 2026-09-13

Christian reran the public export (tag `v2.0.0-r8-only` state) on the institute server:
log `results/logs/run_20260913T103439Z.log` (10:35–11:18 UTC), 24 solves (22 cells + the
two probe-gate repeats), fresh import of `MESSAGEix-AT_baseline_4.xlsx` per cell, all
converged at log index 2; sidecars record `inputs.xlsx` sha256 `408903056be97de8` (the
pruned workbook) and `baseline_4.xlsx` `2fd992d8556bc1c5`. **Every per-cell CSV of all 22
cells is byte-identical to the r8 harvest of 2026-09-08**; only the sidecars differ
(timestamp, workbook hash). The five summary tables, ladder, shape, band and adoption
tables regenerated from the rerun folders equal the committed `results/tables/`.

One defect surfaced: `inventory_check.csv` failed to export in every cell
(`int(str(2022.0))` — the `targets` sheet's value column is float-typed by pandas), fixed
here (`common/validation/inventory.py`, `int(float(...))`; regression test in
`tests/test_reference.py`). The rerun predates the `buildings_final_energy_by_fuel.csv`
exporter (§27 addendum), so that file is absent from its folders. The r7 diagnostic riders
were not part of the rerun. The tracked `results/runs` keep the r8 harvest sidecars as the
result-set identity; the rerun log is tracked beside the r8 log as the reproduction
evidence. Version 2.0.2.
