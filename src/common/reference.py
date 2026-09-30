"""Read the curated Austrian buildings final-energy reference (Statistik Austria).

Ground truth for the base-year check (:mod:`common.validation.base_year`) and
the level STURM output is reconciled to. STURM runs on Western-Europe defaults, so its
*magnitudes* are wrong for Austria; this supplies the real Austrian numbers, in GWa,
by MESSAGEix commodity (``rc_therm``/``rc_spec``) and model fuel.

This module only **reads** the curated data — the ``reference_final_energy`` sheet
of ``data/inputs.xlsx``. The sheet was derived once from the raw STATcube export
(see the workbook's ``provenance`` sheet; the raw files remain in
``data/austria_raw/``).
"""

from __future__ import annotations

import pandas as pd

#: Model fuels an rc technology can actually consume (the comparison set).
MODEL_FUELS: tuple[str, ...] = ("gas", "biomass", "coal", "d_heat", "lightoil", "electr")


def load_reference(year: int = 2024) -> pd.DataFrame:
    """Load the curated buildings reference ``[commodity, fuel, value_gwa]`` for ``year``.

    Reads the ``reference_final_energy`` sheet of ``data/inputs.xlsx``; a missing
    workbook or sheet raises via the strict workbook reader.
    """
    from common import workbook

    data = workbook.reference_frame()
    return data[data["year"] == year].drop(columns="year").reset_index(drop=True)


def reference_by_fuel(year: int = 2024) -> pd.Series:
    """Total Austrian buildings final energy by model fuel (GWa), the comparison set.

    Sums ``rc_therm`` + ``rc_spec`` per fuel and restricts to :data:`MODEL_FUELS`
    (drops the ``other`` bucket, which no rc technology represents).
    """
    ref = load_reference(year)
    by_fuel = ref.groupby("fuel")["value_gwa"].sum()
    return by_fuel[by_fuel.index.isin(MODEL_FUELS)].sort_index()


def reference_commodity_total(commodity: str, year: int = 2024) -> float:
    """Total reference final energy (GWa) for one commodity (``rc_therm``/``rc_spec``).

    Restricts to :data:`MODEL_FUELS` (drops the ``other`` bucket) so it is comparable
    with the modelled final energy.
    """
    ref = load_reference(year)
    sub = ref[(ref["commodity"] == commodity) & (ref["fuel"].isin(MODEL_FUELS))]
    return float(sub["value_gwa"].sum())
