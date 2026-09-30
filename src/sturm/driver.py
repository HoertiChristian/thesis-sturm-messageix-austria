"""Load STURM ``report_MESSAGE`` outputs.

STURM (R; ``message_ix_buildings/sturm/``) writes one CSV per
sector/scenario in the shape ``node, commodity, level, year, time, value,
unit``, with ``commodity`` = ``{sector}_{end_use}_{fuel}`` (e.g.
``resid_heat_biomass``), ``level = "final"``, ``time = "year"``,
``unit = "GWa"``. This module loads and validates such files; it does **not**
run STURM (that is R — see :mod:`linkage.loop` for the iterative case).
"""

from __future__ import annotations

import csv
import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from common import paths
from common.schemas import STURM_REPORT_COLUMNS, require_columns

log = logging.getLogger(__name__)

#: Default modelled years for an offline reference run (5-year resolution,
#: matching the configured 2025–2040 horizon).
_DEFAULT_YEARS: tuple[int, ...] = (2025, 2030, 2035, 2040)

#: Region labels: the Austria-calibrated clone (``C-AUT``/``AUT``) and the WEU
#: source labels it was cloned from (not part of this repository since the W5.1 prune).
_RB_SRC, _RB_DST = "C-WEU-AUT", "C-AUT"
_RG_SRC, _RG_DST = "WEU", "AUT"


def _read_text(path: Path) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("read", b"", 0, 1, f"cannot decode {path}")


def verify_complete(d: Path) -> list[str]:
    """Return input files that have a source-region row but lack the Austrian clone.

    Such a file silently breaks STURM: ``regions_R61`` maps ``C-AUT → AUT``, so a
    ``region_gea`` file with ``WEU`` rows but no ``AUT`` rows makes the fuel/cost joins
    match zero rows for Austria → "columns don't exist" in the stock pivot. Run after
    any partial sync to catch this.
    """
    bad: list[str] = []
    for path in sorted(d.glob("*.csv")):
        text = _read_text(path)
        lines = [ln for ln in text.split("\n") if ln]
        if not lines:
            continue
        cols = next(csv.reader([lines[0]]))
        if "region_bld" in cols:
            key, src, dst = cols.index("region_bld"), _RB_SRC, _RB_DST
        elif "region_gea" in cols:
            key, src, dst = cols.index("region_gea"), _RG_SRC, _RG_DST
        else:
            continue
        vals = {next(csv.reader([ln]))[key] for ln in lines[1:]}
        if src in vals and dst not in vals:
            bad.append(path.name)
    return bad

def _require_region_complete(sector: str, region_select: Sequence[str] | None) -> None:
    """Fail fast (before launching R) if a requested region cannot run on these inputs.

    Two checks, both producing actionable messages instead of STURM's deep-R
    "columns biomass_solid, coal, … don't exist" (the fuel-share join matched
    nothing and the stock pivot found no fuel columns):

    * every requested ``region_bld`` must exist in the ``geo_data`` mapping
      (``regions_R61.csv``) — since the W5.1 prune only ``C-AUT`` remains; the old
      ``C-WEU-AUT`` WEU fallback is not part of this repository;
    * the region-keyed inputs must not be half-synced (a file with source-region
      rows but no Austrian clone; :func:`verify_complete`).
    """
    if not region_select:
        return

    data_dir = paths.STURM_DATA / f"input_csv_SSP_2023_{sector}"
    geo = data_dir / "regions_R61.csv"
    if geo.exists():
        with geo.open(newline="") as fh:
            known = {row["region_bld"] for row in csv.DictReader(fh)}
        missing = sorted(set(region_select) - known)
        if missing:
            raise RuntimeError(
                f"STURM region(s) {missing} not in {geo.name} (available: {sorted(known)}). "
                "The W5.1 region prune removed all non-Austrian rows — run C-AUT "
                "(Config.sturm_region); other regions are not part of this repository."
            )
    incomplete = verify_complete(data_dir)
    if incomplete:
        raise RuntimeError(
            f"STURM region {list(region_select)} is incomplete in {data_dir.name}: "
            f"{incomplete} carry source-region rows but no Austrian (AUT/C-AUT) clone — a partial "
            f"sync. Re-sync the whole data tree (never file-by-file)."
        )
    _require_no_foreign_rows(data_dir)


#: Files whose foreign-region rows are the correct Austrian setting (W5.1):
#: ct_fuel_excluded_reg.csv lists exclusions FOR foreign regions; no AUT rows
#: is intentional.
_KEEP_FOREIGN: frozenset[str] = frozenset({"ct_fuel_excluded_reg.csv"})
_FOREIGN_CHECKED: set[str] = set()


def _require_no_foreign_rows(data_dir: Path) -> None:
    """Fail fast if the pruned data tree carries foreign-region rows.

    The W5.1 prune left only Austrian (``AUT``/``C-AUT``) rows; a foreign row
    means a partially restored tree, and STURM would then silently report
    WEU-wide energy under node ``R12_WEU`` as if it were Austria (the R side
    aggregates on the region mapping without any own check). Until 2026-08-28
    this check lived only in the ``run.ipynb`` preflight, so the CLI and
    ``run_matrix`` paths were unprotected (robustness review, B6). Scanned
    once per process per directory (cached) — the tree does not change
    mid-batch.
    """
    key = str(data_dir)
    if key in _FOREIGN_CHECKED:
        return
    bad: list[str] = []
    for f in sorted(data_dir.glob("*.csv")):
        if f.name in _KEEP_FOREIGN:
            continue
        with f.open(newline="", encoding="utf-8", errors="replace") as fh:
            rows = csv.DictReader(fh)
            col = next(
                (c for c in ("region_bld", "region_gea") if c in (rows.fieldnames or [])), None
            )
            if col and any(r[col] not in ("C-AUT", "AUT") for r in rows):
                bad.append(f.name)
    if bad:
        raise RuntimeError(
            f"{data_dir.name} carries foreign-region rows in {bad[:5]} — a partial sync "
            "(the W5.1 prune left Austrian rows only). Re-sync the whole data tree."
        )
    _FOREIGN_CHECKED.add(key)


def _require_scenario_column(sector: str, scenario: str) -> None:
    """Fail fast (before launching R) if the manifest lacks the scenario column.

    F10 subsets the input manifest by the scenario column name; a column (e.g.
    ``SSP2_RENAT``) missing after a partial sync dies in R with "Can't subset
    columns that don't exist". Catch it here.
    """
    manifest = paths.STURM_DATA / f"input_list_{sector}_SSP_2023.csv"
    with manifest.open(encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    if scenario not in header:
        raise RuntimeError(
            f"STURM scenario column {scenario!r} not in {manifest.name} "
            f"(has: {header[1:]})."
        )


def run_offline(
    *,
    sector: str = "resid",
    scenario: str = "SSP2",
    years: Sequence[int] = _DEFAULT_YEARS,
    region_select: Sequence[str] | None = None,
    geo_level_report: str = "R12",
    prices_csv: Path | None = None,
    mod_new: str = "endogenous",
    mod_ren: str = "endogenous",
    out: Path | None = None,
) -> Path:
    """Run the vendored STURM model headlessly via ``Rscript`` and return the report path.

    Invokes :data:`common.paths.STURM_RUNNER` (``run_sturm_headless.R``), which
    sources STURM's ``F10`` wrapper and writes a single ``report_MESSAGE`` CSV.
    This is the once-through offline call; the iterative price-feedback case is
    :func:`linkage.loop.run_sturm`, which builds on this.

    Args:
        sector: ``resid`` or ``comm``.
        scenario: STURM scenario / SSP variant, e.g. ``SSP2``.
        years: Modelled years (5-year steps).
        region_select: ``region_bld`` codes to subset to (``["C-AUT"]`` for
            Austria — the only region left after the W5.1 input prune).
        geo_level_report: Reporting aggregation level (``R12`` upstream default).
        prices_csv: Commodity-price CSV in STURM's schema; ``None`` uses the
            vendored ``input_prices_R12.csv``.
        mod_new: Construction module — ``endogenous`` (price-sensitive) or
            ``external``.
        mod_ren: Renovation module — ``endogenous`` or ``external``.
        out: Output CSV path; defaults to
            ``results/sturm/report_MESSAGE_{sector}_{scenario}.csv``.

    Returns:
        Path to the written ``report_MESSAGE`` CSV (validated by :func:`load_report`).

    Raises:
        RuntimeError: If ``Rscript`` exits non-zero; the message carries STURM's
            captured ``stderr``.
    """
    _require_region_complete(sector, region_select)
    _require_scenario_column(sector, scenario)

    out = out or paths.STURM_OUTPUT / f"report_MESSAGE_{sector}_{scenario}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "Rscript",
        str(paths.STURM_RUNNER),
        f"--sector={sector}",
        f"--scenario={scenario}",
        f"--years={','.join(str(y) for y in years)}",
        f"--geo_level_report={geo_level_report}",
        f"--mod_new={mod_new}",
        f"--mod_ren={mod_ren}",
        f"--model_dir={paths.STURM_MODEL}",
        f"--data_dir={paths.STURM_DATA}",
        f"--out={out}",
    ]
    if region_select:
        cmd.append(f"--region_select={','.join(region_select)}")
    if prices_csv is not None:
        cmd.append(f"--prices={prices_csv}")

    if shutil.which(cmd[0]) is None:
        raise RuntimeError(
            f"{cmd[0]!r} not found on PATH — STURM needs R with the packages tidyverse and "
            "readxl (viz/plots.R additionally ggplot2, readr, dplyr, tidyr, scales)."
        )
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Always persist STURM's console output next to the report — even on success,
    # so the run is diagnosable offline (e.g. why a year is missing) without the
    # notebook. Guarded so a logging hiccup never masks the run result.
    log_path = out.with_name(out.stem + ".log")
    try:
        log_path.write_text(
            f"$ {' '.join(cmd)}\n\n=== stdout ===\n{proc.stdout}\n"
            f"=== stderr ===\n{proc.stderr}\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    if proc.returncode != 0:
        raise RuntimeError(
            f"STURM run failed (exit {proc.returncode}); see {log_path}.\n"
            f"command: {' '.join(cmd)}\n"
            f"stderr:\n{proc.stderr}"
        )

    # One-line summary so the run log records what STURM actually produced — the
    # final-energy years are the key diagnostic (a 2020-only report means the
    # trajectory is missing).
    try:
        df = pd.read_csv(out)
        years = sorted(df.loc[df.get("level").eq("final"), "year"].dropna().unique())
        log.info(
            "STURM %s/%s: %d rows, final-energy years=%s -> %s",
            sector, scenario, len(df), [int(y) for y in years], out,
        )
    except Exception:
        log.info("STURM %s/%s -> %s (summary unavailable)", sector, scenario, out)

    return out


def load_report(path: Path) -> pd.DataFrame:
    """Load and validate a STURM ``report_MESSAGE_*.csv`` file.

    Args:
        path: Path to the CSV file.

    Returns:
        The report as a data frame with columns :data:`STURM_REPORT_COLUMNS`.

    Raises:
        SchemaError: If the file does not match the STURM report contract.
    """
    df = pd.read_csv(path)
    require_columns(df, STURM_REPORT_COLUMNS, source=f"STURM report {path.name}")
    return df


def split_commodity(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``sector``, ``end_use`` and ``fuel`` columns parsed from ``commodity``.

    STURM encodes ``commodity`` as ``{sector}_{end_use}_{fuel}``. The split is
    needed to subset end-uses (this package scopes to heating and cooling).

    Args:
        df: A STURM report frame.

    Returns:
        A copy of ``df`` with the three parsed columns appended.
    """
    parts = df["commodity"].str.split("_", n=2, expand=True)
    out = df.copy()
    out["sector"], out["end_use"], out["fuel"] = parts[0], parts[1], parts[2]
    return out
