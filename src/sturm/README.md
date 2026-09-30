# `src/sturm/` — demand side: vendored STURM model + Python driver

This package holds a **local, vendored copy** of the IIASA STURM stock-turnover
model (R) — the demand side of the thesis soft-linkage — plus its Python
interface. The whole tree is **committed** so the repo runs standalone (the R
model and its data are third-party; see `data/README.md` for licence caveats).
Only regeneratable run outputs (`output/`) are gitignored.

## Provenance

Copied from the public IIASA buildings package:

```
https://github.com/iiasa/message-ix-buildings — message_ix_buildings/sturm/ at commit 34bac3c
```

Vendored for a CSV-mode run; upstream content not needed for
`input_mode = "csv"` was excluded (`output/`, `data/input_RData/`), and the
2026-07 refactor removed the unused legacy runners (`run_STURM_offline_*.R`)
and report modules (`R00`/`R02`/`R03` — `report_type` is MESSAGE-only; `R05`
stays because `F10` sources it unconditionally). Thesis-side changes to the
R sources are logged in `docs/data/sturm_fork_changelog.md`.

**`data/` is precious.** Since the W5.1 region prune (2026-07-10) the baked
Austrian (`C-AUT`/`AUT`) rows are the only input set — the WEU source rows they
were cloned from are not part of this repository. The values baked in by the
retired builder scripts (switch rates, renovation ceiling, heat-pump fuelset,
digitalization operating hours — the r7 channel, superseded by the efficiency
channel of `linkage/digital.py` since r8) are documented in the `provenance` sheet of
`data/inputs.xlsx` and `docs/data/provenance.md`.

## Contents

- `model/*.R` — the STURM model chain (`B00`, `F01`–`F06`, `F10`) and the
  MESSAGE reporter (`R01`, plus `R05`, see above).
- `data/` — the residential CSV input tree (`input_csv_SSP_2023_resid/`, the 63 files the `SSP2` and `SSP2_RENAT` columns reference),
  manifests, prices, U-values.
- `run_sturm_headless.R` — non-RStudio entry point. Sources
  `model/F10_scenario_runs_MESSAGE_2100.R`, takes `--key=value` arguments, and
  writes one `report_MESSAGE` CSV.
- `driver.py` — Python interface: `run_offline` (launches `Rscript`, with the
  half-sync guard `verify_complete`), `load_report`, `split_commodity`.
- `macko.py` — Macko (2025) digitalization-reduction adapter (reads the
  `macko_reduction` sheet of `data/macko_reduction.xlsx`, a restricted input
  available on request — see `data/README.md`).

## Running

```bash
Rscript src/sturm/run_sturm_headless.R \
  --sector=resid --scenario=SSP2 --years=2025,2030,2035,2040 \
  --region_select=C-AUT \
  --out=results/sturm/report_MESSAGE_resid_SSP2.csv
```

Outputs are written under `results/sturm/` (regeneratable; not the vendored
tree). The Austria run uses `region_bld = C-AUT` (the Austria-calibrated
region), reported under the `R12_WEU` node.


## Sector support

The linkage runs **residential only**, and only the residential input tree ships (the commercial tree was removed on 2026-09-13: upstream's commercial mode carries no price feedback, and the linkage never ran it). `run_sturm_headless.R --sector=comm` remains as an argument but has no data behind it.