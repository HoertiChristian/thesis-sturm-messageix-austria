# sturm_messageix

A soft-linkage between a **building-stock model (STURM)** and an **energy-system
model (MESSAGEix-Austria)** to quantify how digitalization of Austria's building
sector affects its path to the 2040 climate-neutrality target.

STURM produces buildings final energy by fuel; the linkage converts it to **useful
energy** with the MESSAGEix technologies' own base-year input coefficients and
imposes the total as the `rc_therm` demand, leaving the fuel mix to the
optimisation (soft coupling, the headline mode since §17; a base-year calibration
pin plus one-sided pathway caps anchor the levels). MESSAGEix-Austria then solves
the whole system, and the two models exchange demand and prices until the imposed
demand vector converges. Digitalization enters as Macko's (2025) final-energy
savings at constant useful energy: an efficiency effect that scales the conversion
technologies' input coefficients per adoption level (`linkage/digital.py`, the r8
channel), crossed with three climate-neutrality pathways — a 3×3 matrix. The
repository contains exactly the code and data that produced the r8 result set
(2026-09-08); the earlier coupling variants (r5 hard linkage, r7 operating-hours
channel) were removed on 2026-09-13 and live in the git history before tag
`pre-prune-2026-09-13`.

## Install

```bash
pip install -e .            # core (loaders, linkage logic, reporting, tests)
pip install -e ".[model]"   # + the IIASA stack (message_ix, ixmp) needed to solve
pip install -e ".[dev]"     # + pytest, ruff, mypy
pip install -e ".[viz]"     # + matplotlib (two of the viz/ table+figure scripts)
```

(or `pip install -e ".[model,dev]"` for everything.) The packages import and the
unit tests run with the **core** install alone. Actually **solving** additionally
needs a full **GAMS** licence and the **R** runtime (`Rscript`) for STURM — see
*Third-party assets* below.

## Run

```bash
# 1. adjust parameters (if needed): edit data/inputs.xlsx
sturm-messageix list                       # 2. the nine scenario ids
sturm-messageix run --pathway reference --digitalization baseline
sturm-messageix run                        # the whole 3×3 matrix
# 3. visualise
Rscript viz/plots.R                        # results/runs → results/figures
python viz/summary_tables.py               # → results/tables
```

On a Jupyter server, **`run.ipynb`** runs the results batch end to end (data-sync
preflight → convergence gate probe → the 3×3 scenario columns → shape sensitivity →
carbon-price probe → automatic re-run of any non-converged cell at stronger price
damping → inspect → visualise → capture; ~1.2–1.8 h). **`diagnostics.ipynb`** holds
the on-demand verification runs (STURM smoke test, once-through diagnostic,
endogenous-vs-post-hoc CO₂ and W5.6 checks, dual-simplex probe).

### Inputs: one workbook is the single source of truth

**Every tunable parameter lives in `data/inputs.xlsx`** — the run config, the
scenario matrix, the Austrian reference, the Macko reductions, the emission
factors, the targets, the pathway constants. Nothing is duplicated in code:
there are **no code defaults and no fallbacks** for workbook values — a missing
workbook, sheet, or key raises immediately (fail-loud contract). One documented
exception: `$SMX_PLATFORM` overrides the workbook's `platform_name` (see below).
The sheet-by-sheet reference is in **`data/README.md`**; values that were baked
into *other* input files (the STURM CSVs, the baseline workbook) are documented
in the workbook's **`provenance`** sheet (narrative: `docs/data/provenance.md`).

The energy-system model itself is the MESSAGEix workbook
**`data/MESSAGEix-AT_baseline_4.xlsx`** (not included; available on request) — the base-year calibration and the
buildings CO₂ emission factors are baked in, so importing it needs no solve
(see `docs/data/baseline_4_changelog.md`).

Outputs are written per cell to `results/runs/<scenario-id>/` (emissions, fuel mix,
activity, a base-year check, and a reproducibility sidecar).

### Solving on a server (GAMS + ixmp notes)

Solving needs a full **GAMS** licence; the IIASA `ixmp` JDBC/HSQLDB store is fragile
across repeated open→reopen cycles in one process. So:

- run a **batch on one platform** — `run_scenarios([...], cfg, platform=platform)` (or
  `run_matrix`) opens the database **once**; opening a fresh platform per cell can
  corrupt it mid-batch;
- use a **private** ixmp database, not a shared one, and delete + recreate it (absolute
  path!) if a `could not reopen database` error appears. A `Database lock acquisition
  failure` instead means a stale lock from a dead process — shut down any kernel using
  it and `rm <db-dir>/default.lck` (the data is intact). Register one and point every
  entry point (CLI, notebook) at it without editing the workbook:
  ```bash
  ixmp platform add mydb jdbc hsqldb /home/<you>/mydb/default
  export SMX_PLATFORM=mydb        # overrides the config-sheet platform_name everywhere
  ```
- importing the pre-baked **`baseline_4.xlsx`** needs **no solve** (and no GAMS) —
  the calibration/emission bake that produced it was a one-off, recorded in
  `docs/data/` and the workbook's `provenance` sheet (the bake scripts are not
  part of this repository).

The linkage iterates STURM⇄MESSAGEix to convergence (`max_iterations` in the config);
in practice it converges in **2–3 iterations** (price feedback is small), so a tight
budget is fine.

## System requirements

| Component | Requirement | Note |
|---|---|---|
| Python | ≥ 3.10 with `pandas ≥ 2.1`, `click ≥ 8.1`, `openpyxl ≥ 3.1`; `matplotlib` for `viz/shape_sensitivity.py` and `viz/digitalization_band.py` (extra `[viz]`) | core install; enough for the loaders, the linkage logic and `pytest -m "not slow"` |
| IIASA stack | `message_ix ≥ 3.7`, `ixmp ≥ 3.7` (extra `[model]`) + a Java runtime for the ixmp JDBC/HSQLDB backend | needed only to build and solve scenarios |
| GAMS | full licence (the demo licence is too small); the thesis runs used the institute server's GAMS 53.2 with CPLEX (barrier, `epopt 1e-6`, 4 threads, as logged) | the code passes only `solve_model` from the workbook; solver options are the message_ix defaults of the installation |
| R | `Rscript` with `tidyverse` and `readxl` (STURM) and `ggplot2`, `readr`, `dplyr`, `tidyr`, `scales` (`viz/plots.R`) | `Rscript -e 'install.packages(c("tidyverse","readxl","scales"))'` |
| Jupyter | to run `run.ipynb` / `diagnostics.ipynb` | the CLI works without it |

The exact versions of the result-producing environment are recorded with the
run records (`capture_env.sh` writes them); the runs behind the thesis were
solved on the institute server and reproduced there byte-identically on
2026-09-05 (24 solves, all converged at iteration 2).

## Reproducing the thesis tables and figures

1. `run.ipynb` top to bottom → one folder per cell in `results/runs/<scenario-id>/` (emissions, fuel mix, activity, base-year
   check, inventory check, STURM snapshots, `<id>.meta.json` sidecar). The CLI
   (`sturm-messageix run`) solves the 3×3 matrix only; the carbon-price ladder,
   the linear fossil-exit variants, the Wilson demand-band cells and the
   no-digitalization cell are notebook sections (§3c, §3d, §3w, §3n).
2. Tables (`results/tables/`): `python viz/summary_tables.py` (matrix CO₂ by year,
   gap to the 2040 benchmarks, RQ2 spread — territorial + consumption basis);
   `python viz/ladder_table.py` (carbon-price ladder); `python viz/shape_sensitivity.py`
   (logistic vs linear fossil exit + figure); `python viz/convergence_table.py`
   (per-cell convergence from the newest run log in `results/logs/`, written by
   the notebooks and the CLI); `python viz/digitalization_band.py`
   (Wilson demand band table + figure); `python viz/buildings_final_energy.py`
   (buildings final energy by fuel, consumption-basis decomposition, emission-factor
   table); `python viz/adoption_differences.py` (adoption-level differences table +
   figure `rq2_adoption_differences.png`). All of these are also invoked by the last
   cell of `run.ipynb`, which stops on the first failing script.
3. Figures (`results/figures/`): `Rscript viz/plots.R results/runs results/figures`
   (base-year check, emission trajectories on both bases, heating transition,
   RQ2 spread).
4. The thesis copies the CSVs and PNGs from `results/tables` and `results/figures`
   unchanged. **`results/` is tracked**: `results/runs/` holds the 22 solved cells of
   the r8 result set (server run `run_20260908T183848Z`, 2026-09-08), `results/tables/`
   the exact CSVs behind the thesis, `results/figures/` the figures, and
   `results/logs/` the r8 run log. Three tables are archived data that this code no
   longer regenerates (see `results/tables/README.md`). To check a rerun, point
   `SMX_RUNS` at its run folder and run `pytest tests/test_reference_tables.py`
   (working repository only; the public release ships without `tests/`).

## Layout

| Path | What it holds |
|------|---------------|
| `src/sturm/` | **Demand side** — the vendored STURM R model (`model/`, `data/`, `run_sturm_headless.R`) plus its Python interface: `driver.py` (run head-lessly, load/parse the report) and `macko.py` (the Macko 2025 reduction adapter). |
| `src/messageix/` | **Supply side** — `build.py` (load + validate the baseline), `pathways.py` (pathway dials), `report.py`, `emissions.py`, `ixmp_utils.py`. |
| `src/linkage/` | **The coupling + orchestration** — `targets.py`, `bounds.py`, `loop.py`, `convergence.py`, `pipeline.py`, `cli.py`, `runlog.py`. |
| `src/common/` | **Shared infra** — `paths.py`, `config.py`, `scenarios.py`, `units.py`, `workbook.py` (the one strict Excel reader), `reference.py`, `schemas.py`, `vocab.py`, `validation/`. |
| `data/` | `inputs.xlsx` (every tunable parameter); restricted, not included: `MESSAGEix-AT_baseline_4.xlsx` (the pre-baked MESSAGEix scenario) and `macko_reduction.xlsx` (Macko 2025 reduction tables), `austria_raw/README.md` (register of the raw statistical sources; the raw exports themselves are not redistributed), `README.md`. |
| `viz/` | Figures (`plots.R`), summary tables, convergence/sensitivity/ladder tables (see `viz/README.md`). |
| `run.ipynb` | The **results batch** notebook — the easiest way to run on a Jupyter server. |
| `diagnostics.ipynb` | On-demand verification & comparison runs (not needed for the results). |
| *(tests)* | Not part of the public release; the working repository carries the pytest suite (the r8 tables are checked by regenerating them from `results/runs/`, see below). |
| `docs/data/` | Provenance narrative and the calibration / baseline / STURM-fork changelogs (every baked input value with its source). |
| `results/` | The r8 result set — tracked: `runs/` (22 cells), `tables/`, `figures/`, `logs/` (the r8 log). Scratch (`sturm/`, executed notebooks) is not tracked. |

Install from a clone with `pip install -e .`: the code resolves `data/` and the
STURM tree relative to the repository root, so a non-editable (wheel) install is
not supported.

Where to start: `run.ipynb` is the end-to-end results batch (each cell documents
its step); the module docstrings in `src/` describe the coupling, and
`docs/data/provenance.md` explains where every input number comes from.

## Third-party assets and restricted inputs

STURM (R, under `src/sturm/`) is bundled under its upstream Apache-2.0 licence
(`src/sturm/LICENSE-APACHE`). Two third-party inputs are **not included** in this
repository and are **available on request**: the MESSAGEix-Austria baseline
workbook (`data/MESSAGEix-AT_baseline_4.xlsx`) and the Macko (2025) reduction
tables (`data/macko_reduction.xlsx`). With both files in place the pipeline runs
as documented; without them it stops with a message naming the missing file,
while the result tables in `results/` document the runs reported in the thesis.
See **`data/README.md`**.

## Licence

The project's own code is released under the **MIT License** (`LICENSE`); the
bundled third-party assets listed above are excluded and keep their own terms
(scope statement at the end of `LICENSE`). Please cite the software via
`CITATION.cff` together with the accompanying thesis.
