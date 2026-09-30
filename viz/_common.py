"""Shared viz constants and helpers (simplification review 2.1, light form).

One colour map across R and Python: `plots.R`'s ``PATH_COL``/``DIGI_COL``
(Okabe–Ito) are the canon; the dicts here mirror them and the drift risk is
one file instead of three. Argv handling stays per-script (each has its own
positional contract documented in its docstring).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

#: Model grid years reported by the summary artifacts.
MILESTONE_YEARS: tuple[int, ...] = (2025, 2030, 2035, 2040)

#: Pathway colours — mirror plots.R ``PATH_COL`` exactly.
PATH_COLORS: dict[str, str] = {
    "reference": "#999999",
    "renewables_push": "#0072B2",
    "bio_bridge": "#009E73",
}

#: Digitalization colours — mirror plots.R ``DIGI_COL`` exactly.
DIGI_COLORS: dict[str, str] = {
    "stagnating": "#D55E00",
    "baseline": "#999999",
    "accelerated": "#009E73",
}


def co2_series(
    run_dir: Path,
    years: tuple[int, ...] | list[int] = MILESTONE_YEARS,
    csv: str = "buildings_co2.csv",
) -> pd.Series | None:
    """One cell's buildings-CO₂ series indexed by year, or ``None`` if absent."""
    path = run_dir / csv
    if not path.exists():
        return None
    return pd.read_csv(path).set_index("year")["value"].reindex(list(years))
