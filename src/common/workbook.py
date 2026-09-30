"""Strict reader for the input workbook ``data/inputs.xlsx``.

The workbook is the single source of truth for every tunable parameter; this
module is the one place that knows its sheet layout. It exposes the curated
inputs — run config, scenario matrix, Austrian reference, emission factors, targets, pathway constants — to the typed loaders, plus the Macko reductions
from their separate workbook ``data/macko_reduction.xlsx``.

Fail-loud contract: a missing workbook raises :class:`FileNotFoundError`, a
missing sheet raises :class:`ValueError` naming it — never a silent fallback.
Sheet reads are cached so the workbook is opened once per process (edits made
mid-process are invisible; the workbook is read at setup only).
"""

from __future__ import annotations

from functools import cache

import pandas as pd

from common import paths

#: Sheet names in ``inputs.xlsx`` (documented in ``data/README.md``).
CONFIG_SHEET = "config"
PATHWAYS_SHEET = "pathways"
DIGITALIZATION_SHEET = "digitalization"
REFERENCE_SHEET = "reference_final_energy"
MACKO_SHEET = "macko_reduction"
EMISSION_FACTORS_SHEET = "emission_factors"
TARGETS_SHEET = "targets"
PATHWAY_CONSTANTS_SHEET = "pathway_constants"
RENEWABLE_FLOORS_SHEET = "renewable_floors"
CARBON_PRICE_PATHS_SHEET = "carbon_price_paths"


@cache  # open the workbook once per process
def _sheet(name: str) -> pd.DataFrame:
    """Read one sheet (cached), failing loudly on a missing workbook or sheet."""
    if not paths.INPUTS_XLSX.exists():
        raise FileNotFoundError(
            f"{paths.INPUTS_XLSX} not found — the workbook is the only input source "
            f"(no YAML/code fallbacks); restore it from the repository."
        )
    try:
        return pd.read_excel(paths.INPUTS_XLSX, sheet_name=name)
    except ValueError as exc:
        raise ValueError(
            f"sheet {name!r} missing from {paths.INPUTS_XLSX} — see data/README.md "
            f"for the required sheet layout"
        ) from exc


@cache
def _macko_sheet() -> pd.DataFrame:
    """The long ``macko_reduction`` sheet of :data:`common.paths.MACKO_XLSX` (cached)."""
    path = paths.require_restricted(paths.MACKO_XLSX, "Macko (2025) reduction tables")
    return pd.read_excel(path, sheet_name=MACKO_SHEET)


def config_items() -> dict[str, object]:
    """The ``config`` sheet as a ``{key: value}`` dict (blanks → ``None``)."""
    return _kv(_sheet(CONFIG_SHEET))


def targets_items() -> dict[str, object]:
    """The ``targets`` sheet (2040 emission targets, validation tolerances)."""
    return _kv(_sheet(TARGETS_SHEET))


def pathway_constant_items() -> dict[str, object]:
    """The ``pathway_constants`` sheet (fossil-exit leads, logistic k, …)."""
    return _kv(_sheet(PATHWAY_CONSTANTS_SHEET))


def renewable_floors() -> pd.DataFrame:
    """The ``renewable_floors`` sheet ``[expansion_level, family, year, twh_additional]``."""
    return _sheet(RENEWABLE_FLOORS_SHEET).copy()


def carbon_price_path(path_id: str) -> dict[int, float]:
    """A carbon-price time path ``{year: USD/tCO₂}`` from the ``carbon_price_paths`` sheet.

    Referenced by a pathway's ``carbon_price_path`` id (r7, decision B2: the
    legislated NEHG/ETS2 path on the Reference). Fail-loud on every gap: an
    unknown id raises, and a row whose ``usd_per_t`` is blank raises with the
    fill-me instruction — the sheet ships with the 2030–2040 values empty until
    they are taken from a citable basis (UBA REP-0995 scenario assumptions).

    Raises:
        KeyError: If no rows carry ``path_id``.
        ValueError: If any matching row has a blank/non-numeric ``usd_per_t``.
    """
    df = _sheet(CARBON_PRICE_PATHS_SHEET)
    sub = df[df["id"] == path_id]
    if sub.empty:
        known = sorted(set(df["id"].astype(str)))
        raise KeyError(
            f"carbon price path {path_id!r} not in {paths.INPUTS_XLSX} "
            f"sheet {CARBON_PRICE_PATHS_SHEET!r} (known: {known})"
        )
    blank = sub[pd.isna(sub["usd_per_t"])]
    if not blank.empty:
        years = sorted(int(y) for y in blank["year"])
        raise ValueError(
            f"carbon price path {path_id!r} has blank usd_per_t at years {years} — "
            "fill them in the workbook from a citable basis (see the rows' source "
            "column; UBA REP-0995 scenario assumptions) before running."
        )
    return {int(y): float(v) for y, v in zip(sub["year"], sub["usd_per_t"])}


def _kv(df: pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, val in zip(df["key"], df["value"], strict=False):
        out[str(key)] = None if pd.isna(val) else val
    return out


def pathway_records() -> list[dict]:
    """The ``pathways`` sheet as a list of row dicts (blanks → ``None``)."""
    return _records(_sheet(PATHWAYS_SHEET))


def digitalization_records() -> list[dict]:
    """The ``digitalization`` sheet as a list of row dicts."""
    return _records(_sheet(DIGITALIZATION_SHEET))


def _records(df: pd.DataFrame) -> list[dict]:
    return [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def reference_frame() -> pd.DataFrame:
    """The Austrian reference ``[year, commodity, fuel, value_gwa]``."""
    return _sheet(REFERENCE_SHEET).copy()


def emission_factors() -> pd.DataFrame:
    """Per-fuel CO₂ emission factors ``[fuel, ef_direct, ef_total]`` (tCO₂eq/MWh)."""
    return _sheet(EMISSION_FACTORS_SHEET).copy()


def macko_reduction(technology: str, sector: str) -> pd.DataFrame:
    """One Macko reduction table (``Year`` + the three scenario columns).

    Selects ``technology`` × ``sector`` from the long ``macko_reduction`` sheet of
    ``data/macko_reduction.xlsx`` (a restricted input, see ``data/README.md``) and
    returns it in the same shape the per-file CSV loader produced.

    Raises:
        KeyError: If no rows match the requested technology/sector.
    """
    df = _macko_sheet()
    sub = df[(df["technology"] == technology) & (df["sector"] == sector)]
    if sub.empty:
        raise KeyError(f"No Macko reduction for {technology!r} × {sector!r} in {paths.MACKO_XLSX}")
    return sub.drop(columns=["technology", "sector"]).reset_index(drop=True)
