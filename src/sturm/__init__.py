"""The STURM building-stock side (demand).

Vendored third-party model plus its Python interface:

* ``model/*.R`` + ``run_sturm_headless.R`` — the IIASA STURM stock-turnover
  model (R), executed via ``Rscript``; ``data/`` holds its CSV input tree — the
  irreplaceable post-prune Austrian (``C-AUT``) rows included. Both are exempt
  from the Excel-workbook rule (R-native inputs; see ``data/README.md``).
* :mod:`sturm.driver` — launches STURM headless, validates the input tree
  (half-sync guard) and loads the ``report_MESSAGE`` output CSVs.
* :mod:`sturm.macko` — the Macko (2025) digitalization-reduction adapter
  (reads ``data/macko_reduction.xlsx``, a restricted input).
"""
