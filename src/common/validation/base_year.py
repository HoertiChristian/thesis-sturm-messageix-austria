"""Base-year calibration check against Statistik Austria.

The modelled base-year final energy for the building sector must sit within
±3 % of the Statistik Austria reference. A failure points at the calibration
data, not the model.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def tolerance() -> float:
    """Allowed relative deviation of modelled base-year energy from the reference.

    Read from the ``targets`` sheet of ``data/inputs.xlsx`` (``base_year_tolerance``).
    """
    from common import workbook

    return float(workbook.targets_items()["base_year_tolerance"])  # type: ignore[arg-type]


def compare_by_fuel(
    modelled: Mapping[str, float],
    reference: Mapping[str, float],
    *,
    base_year: int,
    tol: float | None = None,
) -> pd.DataFrame:
    """Per-fuel base-year comparison of modelled vs reference final energy.

    Builds one row per fuel present in either input (plus a ``TOTAL`` row), with the
    signed relative deviation and a ``passed`` flag at ``tol``. Missing fuels count
    as zero so a fuel the model omits (or the reference lacks) still surfaces.

    Args:
        modelled: Modelled buildings final energy by fuel (GWa), e.g. the base-year
            slice of :func:`messageix.buildings_final_energy_by_fuel`.
        reference: Statistik Austria final energy by fuel (GWa), from
            :func:`common.reference.reference_by_fuel`.
        base_year: The year being checked (for the output column).
        tol: Relative tolerance for the ``passed`` flag; defaults to
            :func:`tolerance` from the workbook.

    Returns:
        Frame ``[base_year, fuel, modelled_gwa, reference_gwa, rel_deviation, passed]``.
    """
    if tol is None:
        tol = tolerance()
    fuels = sorted(set(modelled) | set(reference))
    rows = []
    for fuel in [*fuels, "TOTAL"]:
        if fuel == "TOTAL":
            m, r = sum(modelled.values()), sum(reference.values())
        else:
            m, r = float(modelled.get(fuel, 0.0)), float(reference.get(fuel, 0.0))
        dev = (m - r) / r if r else float("inf")
        rows.append(
            {
                "base_year": base_year,
                "fuel": fuel,
                "modelled_gwa": round(m, 4),
                "reference_gwa": round(r, 4),
                "rel_deviation": round(dev, 4),
                "passed": abs(dev) <= tol,
            }
        )
    return pd.DataFrame(rows)
