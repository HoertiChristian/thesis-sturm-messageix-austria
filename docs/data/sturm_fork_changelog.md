# STURM fork changelog

Every change to the vendored STURM R source (`src/sturm/model/*.R`) is recorded here
— file, lines, rationale, upstream anchor — per the fork policy (in force since
2026-07-10: every edit to the vendored R source is logged here). Before this date the vendored tree was
byte-identical to upstream `iiasa/message-ix-buildings` at the vendoring commit;
region-keyed *data* overrides (`inputs/austria_sturm/`) and the additive headless
runner (`run_sturm_headless.R`) are not forks and are tracked in
`calibration_changelog.md`.

**Upstream drift watch.** Upstream `main` has moved by one commit since vendoring
(`6a9cb8b`, 2026: F06 demolition join — `select(-year)` moved after the `prob_dem`
join). Checked 2026-07-10: our `bld_demolition_distr_long*.csv` has no `year`
column, so the join-key set is identical and the fix is behavior-neutral for our
inputs. Not adopted (byte-diff kept minimal); revisit if demolition inputs gain a
year dimension.

---

## 1. F06 — exogenous district-heat new-build route retired (W5.6, 2026-07-10)

`F06_stock_dyn_complete_rev.R`, 4 one-line changes (2 per `mod_arch` branch), each
marked `# FORK W5.6`: the non-DH new-build volume no longer rescaled by
`(1 - shr_distr_heat)` (F06:130/218), and the hardcoded DH new-build blocks add 0
units (F06:152/240). Rationale: district heat is decision-modelled from 2026-07-10
(`ct_fuel_comb` `mod_decision=1` + cost rows, `tools/build_fuelset.py`), so new DH
comes from the F04 LCC choice; keeping the exogenous route would double-count and
the `(1-shr)` rescale would delete ~17% of new build. The base-year allocation
(F02:200-201) still reads the 17.3% share file and is untouched.

## 2. F10 — district-heat price delivered to STURM (W5.6, 2026-07-10)

`F10_scenario_runs_MESSAGE_2100.R:110`: `filter(commodity != "d_heat")` replaced by
`mutate(fuel = ifelse(commodity == "d_heat", "district_heat", fuel))` (marked
`# FORK W5.6`). Rationale: with DH in the LCC choice set its operating cost needs
the MESSAGE d_heat price; the drop was consistent only with the old exogenous-share
design. A missing fuel price NA-poisons F05 market shares group-wide.
