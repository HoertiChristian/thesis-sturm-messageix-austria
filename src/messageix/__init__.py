"""The MESSAGEix-Austria energy-system side (supply).

:mod:`messageix.build` loads and validates the pre-calibrated baseline
workbook; :mod:`messageix.pathways` applies the per-pathway climate-neutrality
constraints; :mod:`messageix.report` / :mod:`messageix.emissions` report energy
and CO₂ from solved scenarios (re-exported below).
"""

from common.units import MWH_PER_GWA
from messageix.emissions import (
    buildings_co2,
    buildings_co2_by_fuel,
    buildings_co2_endogenous,
    emission_factors,
    emission_price,
    system_co2,
)
from messageix.report import (
    activity_by_tech,
    buildings_final_energy_by_fuel,
    final_energy_by_fuel,
)

__all__ = [
    "MWH_PER_GWA",
    "activity_by_tech",
    "buildings_co2",
    "buildings_co2_by_fuel",
    "buildings_co2_endogenous",
    "buildings_final_energy_by_fuel",
    "emission_factors",
    "emission_price",
    "final_energy_by_fuel",
    "system_co2",
]
