"""Validation reporters for linkage runs.

* :mod:`common.validation.base_year` — base-year calibration vs. Statistik
  Austria (tolerance from the workbook's ``targets`` sheet); used by the
  pipeline's per-cell ``base_year_check``.
* :mod:`common.validation.gap_to_target` — RQ1, residual gap to the 2040
  buildings-sector emission targets (analysis helper).
"""
