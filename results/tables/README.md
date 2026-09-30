# `results/tables/` — the r8 result tables

Result set **r8** (efficiency channel; 22 cells; server run `run_20260908T183848Z`,
2026-09-08; `scenario_name = baseline-2025-r8`). Regenerated from `results/runs/` by the
`viz/` scripts (`summary_tables.py`, `ladder_table.py`, `shape_sensitivity.py`,
`convergence_table.py`, `digitalization_band.py`); `tests/test_reference_tables.py`
(working repository) checks that the regeneration is byte-identical.

Hand-assembled from the run folders (snippets in the thesis harvest note of 2026-09-08):
`appendix_cells.csv`, `mix_reference_vs_tax0_2040.csv`, `inventory_check.csv`.

**Archived data, not regenerable from this code** (kept because the thesis cites it,
Appendix C): `mode_contrast_reference.csv` (column `bounds_mode_r5_kt` from the archived
hard-linkage result set of 2026-07-14, a coupling mode removed on 2026-09-13).

**Reproduction 2026-09-13:** the server rerun on the pruned code (log
`results/logs/run_20260913T103439Z.log`) reproduced all 22 cells byte for byte; the tables
above regenerate identically from its folders (changelog §28).
